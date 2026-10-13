import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from serviceos_api.application.contracts import (
    DeviceRead, MessagePage, MessageRead, MessageReceipt, VerifiedDeviceFact,
)
from serviceos_api.application.auth import Principal
from serviceos_api.application.errors import ServiceError
from serviceos_api.persistence.models import (
    AgentRun, CaseConversation, CaseDevice, Conversation, Customer, DeviceFact, DevicePassport,
    Message, MessageJob, OutboxEvent, ServiceCase,
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
        ).order_by(DeviceFact.verified_at.desc(), DeviceFact.id)).all()
        snapshot = DeviceRead.model_validate(dev)
        snapshot.verified_facts = [VerifiedDeviceFact.model_validate(row) for row in verified]
        return snapshot

    def create_candidate_fact(self, device_id, request):
        dev = self.resource(DevicePassport, device_id, lock=True)
        if dev.revision != request.expected_device_revision:
            raise ServiceError(409, "设备资料版本已更新，请刷新后重试。")
        fact = DeviceFact(
            tenant_id=self.actor.tenant_id, device_id=dev.id,
            fact_key=request.fact_key, value=request.value,
            source_kind="USER" if self.actor.kind == "CUSTOMER" else "HUMAN",
            source=f"{self.actor.kind.lower()}:{self.actor.actor_id}", validity="CANDIDATE",
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


class ConversationService(BusinessService):
    """Only application entry for publishing and reading user-visible messages."""

    def send_message(self, conversation_id, request):
        conversation = self.resource(Conversation, conversation_id, lock=True)
        if conversation.status != "ACTIVE":
            raise ServiceError(409, "会话已归档。")
        if self.actor.kind == "CUSTOMER" and request.visibility != "PUBLIC":
            raise ServiceError(403, "客户不能发布内部备注。")
        if request.related_case_id:
            self.resource(ServiceCase, request.related_case_id)
            if self.session.get(CaseConversation, (request.related_case_id, conversation.id)) is None:
                raise ServiceError(409, "请先把案例关联到当前会话。")
        payload = request.model_dump(mode="json") | {"actor_id": str(self.actor.actor_id), "actor_kind": self.actor.kind}
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        existing = self.session.scalar(select(Message).where(
            Message.tenant_id == self.actor.tenant_id, Message.conversation_id == conversation.id,
            Message.client_message_id == request.client_message_id,
        ))
        if existing:
            if existing.request_hash != fingerprint:
                raise ServiceError(409, "同一消息标识已用于不同内容。")
            self.session.commit()
            return MessageReceipt(message=MessageRead.model_validate(existing), replayed=True,
                                  processing_state="QUEUED" if existing.author_kind == "CUSTOMER" else "NOT_SCHEDULED")
        identity = {"author_customer_id" if self.actor.kind == "CUSTOMER" else "author_staff_id": self.actor.actor_id}
        message = Message(tenant_id=self.actor.tenant_id, conversation_id=conversation.id,
                          author_kind=self.actor.kind, visibility=request.visibility,
                          content=[part.model_dump() for part in request.content],
                          related_case_id=request.related_case_id, client_message_id=request.client_message_id,
                          request_hash=fingerprint, **identity)
        self.session.add(message)
        self.session.flush()
        if self.actor.kind == "CUSTOMER":
            self.session.add(MessageJob(tenant_id=self.actor.tenant_id, message_id=message.id, conversation_id=conversation.id))
        self.record_event("message.created", {"message_id": str(message.id), "conversation_id": str(conversation.id)},
                          visibility=message.visibility, conversation_id=conversation.id)
        # Return the receipt only after message + job + Outbox commit together.
        self.session.commit()
        return MessageReceipt(message=MessageRead.model_validate(message), replayed=False,
                              processing_state="QUEUED" if self.actor.kind == "CUSTOMER" else "NOT_SCHEDULED")

    def publish_agent_response(self, tenant_id: UUID, conversation_id: UUID, agent_run_id: UUID, lease_token: UUID,
                               text: str, related_case_id: UUID | None = None):
        """Re-check latest conversation policy and persist an Agent result idempotently."""
        text = text.strip()
        if not text or len(text) > 8000:
            raise ServiceError(422, "Agent 回复为空或超出长度限制。")
        conversation = self.session.scalar(select(Conversation).where(
            Conversation.id == conversation_id, Conversation.tenant_id == tenant_id,
        ).with_for_update())
        if conversation is None or conversation.status != "ACTIVE":
            raise ServiceError(409, "会话不可用，Agent 结果未发布。")
        run = self.session.scalar(select(AgentRun).where(
            AgentRun.id == agent_run_id, AgentRun.tenant_id == tenant_id,
            AgentRun.conversation_id == conversation.id,
        ).with_for_update())
        if run is None or run.status != "RUNNING" or run.lease_token != lease_token:
            raise ServiceError(409, "Agent 运行记录已变化，结果未发布。")
        if related_case_id is not None:
            case = self.session.scalar(select(ServiceCase).where(
                ServiceCase.id == related_case_id, ServiceCase.tenant_id == tenant_id,
                ServiceCase.customer_id == conversation.customer_id,
                ServiceCase.archived_at.is_(None),
            ))
            linked = self.session.get(CaseConversation, (related_case_id, conversation.id))
            if case is None or linked is None:
                raise ServiceError(409, "案例未关联到当前会话，Agent 结果未发布。")

        visibility = "PUBLIC" if (
            conversation.collaboration_mode == "AI_LEAD"
            and conversation.reply_policy == "AI_AUTO"
        ) else "INTERNAL"
        content = [{"type": "text", "text": text}]
        fingerprint = hashlib.sha256(json.dumps({
            "agent_run_id": str(run.id), "conversation_id": str(conversation.id),
            "content": content, "related_case_id": str(related_case_id) if related_case_id else None,
            "visibility": visibility,
        }, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        existing = self.session.scalar(select(Message).where(
            Message.tenant_id == tenant_id, Message.conversation_id == conversation.id,
            Message.client_message_id == run.id,
        ))
        if existing is not None:
            if existing.request_hash != fingerprint:
                raise ServiceError(409, "此 AgentRun 已提交不同结果，拒绝重复写入。")
            return existing
        message = Message(
            tenant_id=tenant_id, conversation_id=conversation.id, author_kind="AGENT",
            visibility=visibility, content=content, related_case_id=related_case_id,
            client_message_id=run.id, request_hash=fingerprint,
        )
        self.session.add(message)
        self.session.flush()
        self.session.add(OutboxEvent(
            tenant_id=tenant_id, conversation_id=conversation.id,
            type="message.created", visibility=visibility,
            data={"message_id": str(message.id), "conversation_id": str(conversation.id)},
        ))
        run.status = "COMPLETED"
        run.completed_at = datetime.now(timezone.utc)
        self.session.commit()
        return message

    def messages(self, conversation_id, cursor=None, limit=50):
        conversation = self.resource(Conversation, conversation_id)
        query = select(Message).where(Message.tenant_id == self.actor.tenant_id, Message.conversation_id == conversation.id)
        if self.actor.kind == "CUSTOMER":
            query = query.where(Message.visibility == "PUBLIC")
        if cursor:
            previous = self.session.scalar(query.where(Message.id == cursor))
            if previous is None:
                raise ServiceError(422, "分页标识不属于可读取的当前会话。")
            query = query.where(or_(Message.created_at > previous.created_at,
                                    and_(Message.created_at == previous.created_at, Message.id > previous.id)))
        rows = self.session.scalars(query.order_by(Message.created_at, Message.id).limit(limit + 1)).all()
        return MessagePage(items=[MessageRead.model_validate(row) for row in rows[:limit]],
                           next_cursor=rows[limit - 1].id if len(rows) > limit else None)
