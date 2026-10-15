"""Ownership, case and device application operations shared by service endpoints."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from serviceos_api.application.auth import Principal
from serviceos_api.application.contracts import DeviceRead, VerifiedDeviceFact
from serviceos_api.application.errors import ServiceError
from serviceos_api.persistence.models import (
    CaseAction, CaseConversation, CaseDevice, Conversation, Customer, DeviceFact,
    DevicePassport, OutboxEvent, ServiceCase,
)


class BusinessService:
    def __init__(self, session: Session, actor: Principal):
        self.session = session
        self.actor = actor

    def owner_query(self, model):
        query = select(model).where(model.tenant_id == self.actor.tenant_id)
        if self.actor.kind == "CUSTOMER":
            query = query.where(model.customer_id == self.actor.actor_id)
        if model in (ServiceCase, DevicePassport):
            query = query.where(model.archived_at.is_(None))
        return query

    def resource(self, model, id_: UUID, lock=False):
        query = self.owner_query(model).where(model.id == id_)
        if lock:
            query = query.with_for_update()
        record = self.session.scalar(query)
        if record is None:
            raise ServiceError(404, "记录不存在或当前账号无权访问。")
        return record

    def owner_for_create(self, requested: UUID | None):
        if self.actor.kind == "CUSTOMER":
            if requested and requested != self.actor.actor_id:
                raise ServiceError(403, "不能为其他客户创建记录。")
            return self.actor.actor_id
        if requested is None:
            raise ServiceError(422, "客服创建记录需要指定客户。")
        owner = self.session.scalar(select(Customer).where(
            Customer.id == requested, Customer.tenant_id == self.actor.tenant_id,
        ))
        if owner is None:
            raise ServiceError(404, "客户不存在。")
        return owner.id

    def record_event(self, type_: str, data: dict, visibility="PUBLIC", conversation_id=None):
        self.session.add(OutboxEvent(tenant_id=self.actor.tenant_id, type=type_, data=data,
                                     visibility=visibility, conversation_id=conversation_id))

    def create(self, model, request):
        fields = request.model_dump(exclude={"customer_id"})
        if model is DevicePassport:
            fields["identity_source"] = "staff_statement" if self.actor.kind == "STAFF" else "user_statement"
        record = model(tenant_id=self.actor.tenant_id, customer_id=self.owner_for_create(request.customer_id), **fields)
        self.session.add(record)
        self.session.flush()
        self.record_event(f"{model.__tablename__}.created", {"id": str(record.id)},
                          conversation_id=record.id if model is Conversation else None)
        self.session.commit()
        return record

    def list_resources(self, model, limit=50):
        return self.session.scalars(self.owner_query(model).order_by(model.created_at.desc(), model.id).limit(limit)).all()

    def update_case(self, id_, request):
        case = self.resource(ServiceCase, id_, lock=True)
        if case.version != request.expected_version:
            raise ServiceError(409, "案例版本已更新，请刷新后重试。")
        if case.status == "CLOSED":
            raise ServiceError(409, "已关闭案例的历史内容不能直接改写。")
        for key, value in request.model_dump(exclude={"expected_version"}, exclude_unset=True).items():
            if key == "problem_text" and value is None:
                raise ServiceError(422, "问题描述不能为空。")
            setattr(case, key, value)
        case.version += 1
        self.record_event("case.updated", {"case_id": str(case.id), "version": case.version})
        self.session.commit()
        return case

    def transition_case(self, id_, request):
        if self.actor.kind != "STAFF":
            raise ServiceError(403, "只有已授权客服可以改变案例状态。")
        case = self.resource(ServiceCase, id_, lock=True)
        if case.version != request.expected_version:
            raise ServiceError(409, "案例版本已更新，请刷新后重试。")
        next_states = {
            "OPEN": {"IN_PROGRESS"},
            "IN_PROGRESS": {"WAITING_CUSTOMER", "WAITING_EXTERNAL", "RESOLVED"},
            "WAITING_CUSTOMER": {"IN_PROGRESS"},
            "WAITING_EXTERNAL": {"IN_PROGRESS"},
            "RESOLVED": {"CLOSED", "IN_PROGRESS"},
            "CLOSED": {"IN_PROGRESS"},
        }
        if request.target_status not in next_states[case.status]:
            raise ServiceError(409, "不允许从当前案例状态直接转到目标状态。")
        if request.target_status in ("RESOLVED", "CLOSED"):
            active_action = self.session.scalar(select(CaseAction.id).where(
                CaseAction.tenant_id == case.tenant_id, CaseAction.case_id == case.id,
                CaseAction.status.in_(("WAITING_APPROVAL", "APPROVED", "EXECUTING", "UNKNOWN")),
            ).limit(1))
            if active_action is not None:
                raise ServiceError(409, "案例仍有待审批、执行或对账的售后动作。", code="ACTION_UNSETTLED")
        if request.target_status == "RESOLVED":
            recorded_action = self.session.scalar(select(CaseAction.id).where(
                CaseAction.tenant_id == case.tenant_id, CaseAction.case_id == case.id,
            ).limit(1))
            if recorded_action is not None:
                raise ServiceError(409, "售后动作已有记录，但问题结果尚未经核验；不能直接标为已解决。",
                                   code="VERIFICATION_REQUIRED")
        previous = case.status
        case.status = request.target_status
        case.version += 1
        now = datetime.now(timezone.utc)
        if case.status == "RESOLVED":
            case.resolved_at = now
        if case.status == "CLOSED":
            case.closed_at = now
        self.record_event("case.status_changed", {
            "case_id": str(case.id), "from": previous, "to": case.status,
            "reason": request.reason, "actor_id": str(self.actor.actor_id), "version": case.version,
        }, visibility="INTERNAL")
        self.session.commit()
        return case

    def update_device(self, id_, request):
        dev = self.resource(DevicePassport, id_, lock=True)
        if dev.revision != request.expected_revision:
            raise ServiceError(409, "设备资料版本已更新，请刷新后重试。")
        if dev.identity_status == "VERIFIED":
            raise ServiceError(409, "已核验身份需要通过带证据的核验流程变更。")
        for key, value in request.model_dump(exclude={"expected_revision"}, exclude_unset=True).items():
            setattr(dev, key, value)
        if not (dev.model and dev.model.strip()) and not (dev.serial_number and dev.serial_number.strip()):
            raise ServiceError(422, "设备需保留有效身份材料。")
        dev.revision += 1
        self.record_event("device.updated", {"device_id": str(dev.id), "revision": dev.revision})
        self.session.commit()
        return dev

    def archive(self, model, id_):
        record = self.resource(model, id_, lock=True)
        if model is ServiceCase:
            if record.status != "CLOSED":
                raise ServiceError(409, "只有已关闭案例可归档；归档不代表问题解决。")
            record.version += 1
        else:
            open_case = self.session.scalar(select(ServiceCase.id).join(
                CaseDevice, and_(CaseDevice.case_id == ServiceCase.id, CaseDevice.tenant_id == ServiceCase.tenant_id),
            ).where(CaseDevice.device_id == record.id, ServiceCase.status != "CLOSED"))
            if open_case:
                raise ServiceError(409, "设备仍关联未关闭案例，不能归档。")
            record.revision += 1
        record.archived_at = datetime.now(timezone.utc)
        self.record_event(f"{model.__tablename__}.archived", {"id": str(record.id)})
        self.session.commit()

    def attach(self, case_id, request, model):
        case = self.resource(ServiceCase, case_id, lock=True)
        if case.version != request.expected_version:
            raise ServiceError(409, "案例版本已更新，请刷新后重试。")
        if case.status == "CLOSED":
            raise ServiceError(409, "已关闭案例不能改变关联。")
        is_device = model is DevicePassport
        target_id = request.device_id if is_device else request.conversation_id
        target = self.resource(model, target_id)
        if target.customer_id != case.customer_id:
            raise ServiceError(403, "案例与关联资源必须属于同一客户。")
        association = CaseDevice if is_device else CaseConversation
        key = (case.id, target.id)
        link = self.session.get(association, key)
        if link is None:
            values = {"device_id" if is_device else "conversation_id": target.id}
            if is_device:
                values.update(role=request.role, is_primary=request.is_primary)
            self.session.add(association(tenant_id=case.tenant_id, case_id=case.id, **values))
            case.version += 1
            self.record_event("case.updated", {"case_id": str(case.id), "version": case.version})
        elif is_device and (link.role != request.role or link.is_primary != request.is_primary):
            raise ServiceError(409, "设备已关联，变更关联角色需要独立的版本化操作。")
        self.session.commit()
        return case

    def device_cases(self, device_id):
        dev = self.resource(DevicePassport, device_id)
        return self.session.scalars(self.owner_query(ServiceCase).join(
            CaseDevice, and_(CaseDevice.case_id == ServiceCase.id, CaseDevice.tenant_id == ServiceCase.tenant_id),
        ).where(CaseDevice.device_id == dev.id).order_by(ServiceCase.created_at.desc())).all()

    def device_read(self, dev):
        verified = self.session.scalars(select(DeviceFact).where(
            DeviceFact.tenant_id == self.actor.tenant_id,
            DeviceFact.device_id == dev.id,
            DeviceFact.validity == "VERIFIED",
            or_(DeviceFact.source_case_id.is_(None), DeviceFact.archived_at.is_not(None)),
        ).order_by(DeviceFact.verified_at.desc(), DeviceFact.id)).all()
        snapshot = DeviceRead.model_validate(dev)
        snapshot.verified_facts = [VerifiedDeviceFact.model_validate(row).model_copy(update={
            "source": "客户陈述" if row.source_kind == "USER" else "客服记录",
            "verified_by": "客服核验" if row.verifier_kind == "HUMAN" else "受信工具核验",
        }) if self.actor.kind == "CUSTOMER" else VerifiedDeviceFact.model_validate(row) for row in verified]
        return snapshot

    def create_candidate_fact(self, device_id, request):
        dev = self.resource(DevicePassport, device_id, lock=True)
        source = f"{self.actor.kind.lower()}:{self.actor.actor_id}"
        if request.client_fact_id is not None:
            previous = self.session.scalar(select(DeviceFact).where(
                DeviceFact.tenant_id == dev.tenant_id,
                DeviceFact.device_id == dev.id,
                DeviceFact.client_fact_id == request.client_fact_id,
            ).with_for_update())
            if previous is not None:
                if previous.fact_key != request.fact_key or previous.value != request.value \
                        or previous.source_case_id != request.source_case_id or previous.source != source:
                    raise ServiceError(409, "同一事实编号已用于其他内容。", code="IDEMPOTENCY_CONFLICT")
                return previous
        if dev.revision != request.expected_device_revision:
            raise ServiceError(409, "设备资料版本已更新，请刷新后重试。")
        if request.source_case_id is not None:
            case = self.resource(ServiceCase, request.source_case_id)
            if case.customer_id != dev.customer_id:
                raise ServiceError(403, "事实来源案例与设备不属于同一客户。")
            linked = self.session.scalar(select(CaseDevice).where(
                CaseDevice.tenant_id == dev.tenant_id, CaseDevice.case_id == case.id,
                CaseDevice.device_id == dev.id,
            ))
            if linked is None:
                raise ServiceError(409, "来源案例必须已关联此设备。")
        fact = DeviceFact(
            tenant_id=self.actor.tenant_id, device_id=dev.id,
            client_fact_id=request.client_fact_id,
            fact_key=request.fact_key, value=request.value,
            source_case_id=request.source_case_id,
            source_kind="USER" if self.actor.kind == "CUSTOMER" else "HUMAN",
            source=source, validity="CANDIDATE",
        )
        self.session.add(fact)
        self.session.flush()
        dev.revision += 1
        self.record_event("device.fact_candidate", {"device_id": str(dev.id), "fact_id": str(fact.id)},
                          visibility="INTERNAL")
        self.session.commit()
        return fact

    def candidate_facts(self, device_id):
        dev = self.resource(DevicePassport, device_id)
        if self.actor.kind != "STAFF":
            raise ServiceError(403, "只有已授权客服可查看待核验设备事实。")
        return self.session.scalars(select(DeviceFact).where(
            DeviceFact.tenant_id == self.actor.tenant_id,
            DeviceFact.device_id == dev.id,
            DeviceFact.validity == "CANDIDATE",
        ).order_by(DeviceFact.created_at, DeviceFact.id)).all()

    def case_fact_review(self, device_id):
        dev = self.resource(DevicePassport, device_id)
        if self.actor.kind != "STAFF":
            raise ServiceError(403, "只有已授权客服可查看案例来源的待归档事实。")
        return self.session.scalars(select(DeviceFact).where(
            DeviceFact.tenant_id == self.actor.tenant_id,
            DeviceFact.device_id == dev.id,
            DeviceFact.source_case_id.is_not(None),
            or_(DeviceFact.validity == "CANDIDATE",
                and_(DeviceFact.validity == "VERIFIED", DeviceFact.archived_at.is_(None))),
        ).order_by(DeviceFact.created_at, DeviceFact.id)).all()

    def archive_case_fact(self, case_id, device_id, fact_id, request):
        if self.actor.kind != "STAFF":
            raise ServiceError(403, "只有已授权客服可归档设备事实。")
        case = self.resource(ServiceCase, case_id, lock=True)
        dev = self.resource(DevicePassport, device_id, lock=True)
        if case.customer_id != dev.customer_id:
            raise ServiceError(403, "案例与设备不属于同一客户。")
        linked = self.session.scalar(select(CaseDevice).where(
            CaseDevice.tenant_id == case.tenant_id, CaseDevice.case_id == case.id,
            CaseDevice.device_id == dev.id,
        ))
        if linked is None:
            raise ServiceError(404, "案例未关联此设备。")
        fact = self.session.scalar(select(DeviceFact).where(
            DeviceFact.tenant_id == case.tenant_id, DeviceFact.id == fact_id,
            DeviceFact.device_id == dev.id, DeviceFact.source_case_id == case.id,
        ).with_for_update())
        if fact is None:
            raise ServiceError(404, "事实不存在或来源不属于此案例。")
        if fact.archived_at is not None and fact.validity == "VERIFIED":
            return fact
        if case.version != request.expected_case_version or dev.revision != request.expected_device_revision \
                or fact.revision != request.expected_fact_revision:
            raise ServiceError(409, "案例、设备或事实版本已更新，请刷新后重试。")
        if case.status != "RESOLVED":
            raise ServiceError(409, "案例尚未经核验解决，不能归档长期设备事实。")
        if fact.validity != "VERIFIED" or fact.verified_by is None or fact.verified_at is None:
            raise ServiceError(409, "只有已由客服核验的事实可以归档。")
        fact.archived_at = datetime.now(timezone.utc)
        fact.archived_by = self.actor.actor_id
        fact.revision += 1
        dev.revision += 1
        self.record_event("device.fact_archived", {
            "case_id": str(case.id), "device_id": str(dev.id), "fact_id": str(fact.id),
            "actor_id": str(self.actor.actor_id),
        }, visibility="INTERNAL")
        self.session.commit()
        return fact

    def decide_fact(self, device_id, fact_id, request, retract=False):
        if self.actor.kind != "STAFF":
            raise ServiceError(403, "只有已授权客服可以核验或撤销设备事实。")
        dev = self.resource(DevicePassport, device_id, lock=True)
        if dev.revision != request.expected_device_revision:
            raise ServiceError(409, "设备资料版本已更新，请刷新后重试。")
        fact = self.session.scalar(select(DeviceFact).where(
            DeviceFact.tenant_id == self.actor.tenant_id,
            DeviceFact.device_id == dev.id, DeviceFact.id == fact_id,
        ).with_for_update())
        if fact is None:
            raise ServiceError(404, "设备事实不存在或当前账号无权访问。")
        if fact.revision != request.expected_fact_revision:
            raise ServiceError(409, "设备事实版本已更新，请刷新后重试。")
        expected = "VERIFIED" if retract else "CANDIDATE"
        if fact.validity != expected:
            raise ServiceError(409, "设备事实当前状态不允许此操作。")
        now = datetime.now(timezone.utc)
        if retract:
            fact.validity = "RETRACTED"
            fact.retracted_at = now
            fact.retraction_reason = request.reason
        else:
            fact.validity = "VERIFIED"
            fact.verifier_kind = "HUMAN"
            fact.verified_by = f"staff:{self.actor.actor_id}"
            fact.verified_at = now
        fact.revision += 1
        dev.revision += 1
        self.record_event("device.fact_retracted" if retract else "device.fact_verified", {
            "device_id": str(dev.id), "fact_id": str(fact.id), "reason": request.reason,
            "actor_id": str(self.actor.actor_id),
        }, visibility="INTERNAL")
        self.session.commit()
        return fact
