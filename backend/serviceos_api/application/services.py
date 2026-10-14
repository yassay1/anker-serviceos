import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import and_, or_, select, true
from sqlalchemy.orm import Session

from serviceos_api.application.contracts import (
    CaseRead, DeskCaseSummary, DeviceRead, EventPage, EventRead, MessagePage, MessageRead, MessageReceipt, ProposalRead,
    SummaryFact, TaskRead, UIActionResult, UIDocumentRead, VerifiedDeviceFact,
)
from serviceos_api.application.auth import Principal
from serviceos_api.application.errors import ServiceError
from serviceos_api.application.ui_catalog import CATALOG_VERSION, SCHEMA_VERSION, safe_text, validate_components
from serviceos_api.persistence.models import (
    AgentProposal, AgentRun, CaseAction, CaseConversation, CaseDevice, CaseEvidence, Conversation, ConversationEvent, Customer, DeviceFact,
    DevicePassport, Message, MessageJob, OutboxEvent, ServiceCase, ServiceTask, TaskAssignment,
    UIActionInvocation, UIDocument,
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


class ConversationService(BusinessService):
    """Only application entry for publishing and reading user-visible messages."""

    @staticmethod
    def record_agent_progress(session, tenant_id: UUID, conversation_id: UUID,
                              run_id: UUID, lease_token: UUID, step: str):
        """Persist only real, fixed system transitions under an active generation lease.

        The caller owns the transaction. This is not an Agent text publication API;
        no arbitrary stage, summary, tool argument or inferred waiting state is accepted.
        """
        from uuid import uuid5

        from serviceos_api.application.agent_services import AgentProgress, PROGRESS_STEPS, validate_agent_execution

        if step not in PROGRESS_STEPS:
            raise ValueError("progress_step_not_allowed")
        statuses = ("COMPLETED",) if step == "worker_completed" else ("FAILED",) if step == "worker_failed" else ("RUNNING",)
        run, _, conversation, _ = validate_agent_execution(
            session, tenant_id, conversation_id, run_id, lease_token, statuses=statuses)
        event_id = uuid5(run.id, f"agent.progress:{lease_token}:{step}")
        existing = session.scalar(select(OutboxEvent).where(
            OutboxEvent.id == event_id, OutboxEvent.tenant_id == tenant_id,
            OutboxEvent.conversation_id == conversation_id,
        ))
        if existing is not None:
            return existing
        stage, summary = PROGRESS_STEPS[step]
        payload = AgentProgress(run_id=str(run.id), stage=stage, summary=summary)
        visibility = "PUBLIC" if (conversation.collaboration_mode == "AI_LEAD"
                                   and conversation.reply_policy == "AI_AUTO") else "INTERNAL"
        event = OutboxEvent(id=event_id, tenant_id=tenant_id, conversation_id=conversation_id,
                            type="agent.progress", visibility=visibility, data=payload.model_dump(),
                            created_at=datetime.now(timezone.utc))
        session.add(event)
        session.flush()
        return event

    @staticmethod
    def dispatch_outbox_event(session, event: OutboxEvent):
        conversation = session.scalar(select(Conversation).where(
            Conversation.id == event.conversation_id, Conversation.tenant_id == event.tenant_id,
        ).with_for_update().execution_options(populate_existing=True))
        if conversation is None:
            raise ServiceError(409, "事件所属会话不可用。")
        if event.visibility == "PUBLIC" and event.type not in (
            "message.created", "conversations.created", "collaboration.mode_changed",
            "ui.document.published", "ui.action.accepted",
            "evidence.received", "evidence.inspected", "action.state_changed", "verification.recorded",
            "follow_up.consented", "agent.progress",
        ):
            raise ServiceError(422, "公开事件类型未获授权。")
        visibility = event.visibility
        data = event.data
        if event.type == "agent.progress":
            from serviceos_api.application.agent_services import AgentProgress

            try:
                data = AgentProgress.model_validate(data).model_dump()
            except (ValidationError, ValueError):
                raise ServiceError(422, "进度事件字段或摘要未获授权。") from None
            run = session.scalar(select(AgentRun.id).where(
                AgentRun.id == UUID(data["run_id"]), AgentRun.tenant_id == event.tenant_id,
                AgentRun.conversation_id == conversation.id,
            ))
            if run is None:
                raise ServiceError(422, "进度事件运行引用无效。")
            # Never promote INTERNAL events. Recheck after a mode change during dispatch delay.
            if (conversation.status != "ACTIVE" or conversation.collaboration_mode != "AI_LEAD"
                    or conversation.reply_policy != "AI_AUTO"):
                visibility = "INTERNAL"
        if event.id is not None:
            existing = session.scalar(select(ConversationEvent).where(
                ConversationEvent.id == event.id, ConversationEvent.tenant_id == event.tenant_id,
                ConversationEvent.conversation_id == conversation.id,
            ))
            if existing is not None:
                return existing
        current = session.scalar(select(ConversationEvent.sequence).where(
            ConversationEvent.tenant_id == event.tenant_id,
            ConversationEvent.conversation_id == conversation.id,
        ).order_by(ConversationEvent.sequence.desc()).limit(1)) or 0
        row = ConversationEvent(id=event.id, tenant_id=event.tenant_id, conversation_id=conversation.id,
                                sequence=current + 1, type=event.type,
                                visibility=visibility, data=data)
        if event.type == "agent.progress" and event.created_at is not None:
            row.created_at = event.created_at
        session.add(row)
        return row

    def events(self, conversation_id, after=0, limit=100):
        conversation = self.resource(Conversation, conversation_id)
        query = select(ConversationEvent).where(
            ConversationEvent.tenant_id == self.actor.tenant_id,
            ConversationEvent.conversation_id == conversation.id,
            ConversationEvent.sequence > after,
        )
        if self.actor.kind == "CUSTOMER":
            query = query.where(ConversationEvent.visibility == "PUBLIC")
        rows = self.session.scalars(query.order_by(ConversationEvent.sequence).limit(limit)).all()
        return EventPage(items=[EventRead.model_validate(row) for row in rows],
                         next_after=rows[-1].sequence if rows else after)

    def transition_mode(self, conversation_id, request):
        if self.actor.kind != "STAFF":
            raise ServiceError(403, "只有客服可切换协作策略。")
        conversation = self.resource(Conversation, conversation_id, lock=True)
        if conversation.status != "ACTIVE":
            raise ServiceError(409, "会话已归档。")
        if conversation.version != request.expected_version:
            raise ServiceError(409, "会话版本已更新，请刷新后重试。")
        if request.target_mode == "HUMAN_LEAD" and request.reply_policy != "HUMAN_ONLY":
            raise ServiceError(422, "人工主导时 Agent 不能公开发言。")
        if request.target_mode == "CO_SERVICE" and request.reply_policy == "AI_AUTO" and self.actor.role not in ("SUPERVISOR", "ADMIN"):
            raise ServiceError(403, "同时服务时允许 Agent 自动发言需要主管授权。")
        conversation.collaboration_mode = request.target_mode
        conversation.reply_policy = request.reply_policy
        conversation.version += 1
        self.record_event("collaboration.mode_changed", {
            "mode": conversation.collaboration_mode, "reply_policy": conversation.reply_policy,
            "version": conversation.version,
        }, conversation_id=conversation.id)
        self.session.commit()
        return conversation

    def request_assistance(self, conversation_id, request, *, commit=True):
        conversation = self.resource(Conversation, conversation_id, lock=True)
        if conversation.status != "ACTIVE":
            raise ServiceError(409, "会话已归档。")
        if request.case_id:
            case = self.resource(ServiceCase, request.case_id)
            if case.customer_id != conversation.customer_id or self.session.get(CaseConversation, (case.id, conversation.id)) is None:
                raise ServiceError(409, "案例未关联到当前会话。")
        task = ServiceTask(tenant_id=self.actor.tenant_id, conversation_id=conversation.id,
                           case_id=request.case_id,
                           requester_customer_id=self.actor.actor_id if self.actor.kind == "CUSTOMER" else None,
                           reason=request.reason)
        self.session.add(task)
        self.session.flush()
        self.record_event("assistance.requested", {"task_id": str(task.id)},
                          visibility="INTERNAL", conversation_id=conversation.id)
        if commit:
            self.session.commit()
        return self._task_read(task)

    def publish_ui_projection(self, conversation_id):
        conversation = self.resource(Conversation, conversation_id, lock=True)
        audience = "CUSTOMER" if self.actor.kind == "CUSTOMER" else "STAFF"
        visibility = "PUBLIC" if audience == "CUSTOMER" else "INTERNAL"
        if conversation.status != "ACTIVE":
            raise ServiceError(409, "会话已归档，不能发布新的 UI。")
        source = {"kind": "CONVERSATION_VIEW", "resource_id": str(conversation.id),
                  "resource_version": conversation.version, "binding": "assistance"}
        refs = {("CONVERSATION_VIEW", conversation.id): conversation.version}
        components = []
        source_run_id = None
        if audience == "CUSTOMER":
            components.append({"id": "request-assistance", "type": "ActionBar",
                               "props": {"title": "需要真人协助？", "body": "请求会创建人工任务；你仍可继续发送文字消息。"},
                               "data_source": source,
                               "actions": [{"action_id": "request-human-assistance", "intent": "REQUEST_ASSISTANCE",
                                            "input_schema_ref": "serviceos://ui-inputs/assistance-request/v1"}],
                               "children": []})
            if conversation.collaboration_mode == "AI_LEAD" and conversation.reply_policy == "AI_AUTO":
                # Only answer questions that are still open: an agent card belongs to a turn
                # that came after the customer's latest message. Without this, a run whose
                # proposal was unusable made the projection resurrect the previous question,
                # asking the customer the same thing again and again.
                latest_customer_turn = self.session.scalar(select(Message.created_at).where(
                    Message.tenant_id == self.actor.tenant_id,
                    Message.conversation_id == conversation.id,
                    Message.author_kind == "CUSTOMER",
                    Message.visibility == "PUBLIC",
                ).order_by(Message.created_at.desc(), Message.id.desc()).limit(1))
                runs = self.session.scalars(select(AgentRun).where(
                    AgentRun.tenant_id == self.actor.tenant_id,
                    AgentRun.conversation_id == conversation.id,
                    AgentRun.status == "COMPLETED",
                    AgentRun.created_at > latest_customer_turn if latest_customer_turn else true(),
                ).order_by(AgentRun.created_at.desc()).limit(5)).all()
                for run in runs:
                    proposal = (run.result_payload or {}).get("ui_proposal")
                    public_message = self.session.scalar(select(Message.id).where(
                        Message.tenant_id == self.actor.tenant_id,
                        Message.conversation_id == conversation.id,
                        Message.client_message_id == run.id,
                        Message.visibility == "PUBLIC",
                    ))
                    if proposal and proposal.get("audience") == "CUSTOMER" and public_message:
                        refs[("AGENT_RUN_VIEW", run.id)] = 1
                        options = proposal.get("options") or []
                        kind = "ChoiceGroup" if len(options) >= 2 else "QuestionForm"
                        components.append({"id": "agent-choice" if kind == "ChoiceGroup" else "agent-question",
                                           "type": kind,
                                           "props": {"title": "下一步需要的信息", "body": proposal["purpose"]},
                                           "data_source": {"kind": "AGENT_RUN_VIEW", "resource_id": str(run.id),
                                                           "resource_version": 1, "binding": "question"},
                                           "actions": [], "children": [], "options": options})
                        source_run_id = run.id
                        break
        else:
            summaries = self.desk_case_summaries(conversation.id)
            for summary in summaries[:5]:
                case = summary.case
                refs[("CASE_VIEW", case.id)] = case.version
                components.append({"id": f"case-{str(case.id)[:8]}", "type": "CaseSummaryCard",
                                   "props": {"title": "案例摘要", "body": case.problem_text[:500],
                                             "status": case.status, "source": "case:customer_or_staff_statement",
                                             "verification": "CANDIDATE"},
                                   "data_source": {"kind": "CASE_VIEW", "resource_id": str(case.id),
                                                   "resource_version": case.version, "binding": "summary"},
                                   "actions": [], "children": []})
                for index, fact in enumerate(summary.facts[1:3]):
                    components.append({"id": f"evidence-{str(case.id)[:8]}-{index}", "type": "EvidenceSummary",
                                       "props": {"title": fact.label[:100], "body": fact.value[:500],
                                                 "source": fact.source[:240], "verification": fact.verification},
                                       "data_source": {"kind": "CASE_VIEW", "resource_id": str(case.id),
                                                       "resource_version": case.version, "binding": "evidence"},
                                       "actions": [], "children": []})
            tasks = self.tasks(conversation.id)
            for task in tasks[-3:]:
                refs[("TASK_VIEW", task.id)] = task.version
                components.append({"id": f"task-{str(task.id)[:8]}", "type": "HandoffSummary",
                                   "props": {"title": "人工任务", "body": task.reason[:500], "status": task.status},
                                   "data_source": {"kind": "TASK_VIEW", "resource_id": str(task.id),
                                                   "resource_version": task.version, "binding": "handoff"},
                                   "actions": [], "children": []})
            if not components:
                components.append({"id": "conversation-progress", "type": "ProgressTimeline",
                                   "props": {"title": "会话状态", "body": "会话已建立；尚无关联案例或人工任务。",
                                             "status": conversation.status},
                                   "data_source": {"kind": "CONVERSATION_VIEW", "resource_id": str(conversation.id),
                                                   "resource_version": conversation.version, "binding": "overview"},
                                   "actions": [], "children": []})
        components = validate_components(components[:12], audience, refs)
        fallback = safe_text("交互卡暂不可用，请继续使用文字消息。")
        signature = hashlib.sha256(json.dumps({"components": components, "mode": conversation.collaboration_mode,
                                               "policy": conversation.reply_policy}, sort_keys=True,
                                              ensure_ascii=False).encode()).hexdigest()
        active = self.session.scalar(select(UIDocument).where(
            UIDocument.tenant_id == self.actor.tenant_id,
            UIDocument.conversation_id == conversation.id,
            UIDocument.audience == audience, UIDocument.status == "ACTIVE",
        ).with_for_update())
        now = datetime.now(timezone.utc)
        if active and active.context_signature == signature and (active.expires_at is None or active.expires_at > now):
            return UIDocumentRead.model_validate(active)
        if active:
            active.status = "SUPERSEDED"
            ui_id, revision = active.ui_id, active.revision + 1
            self.session.flush()
        else:
            ui_id, revision = uuid4(), 1
        document = UIDocument(tenant_id=self.actor.tenant_id, conversation_id=conversation.id,
                              ui_id=ui_id, revision=revision, schema_version=SCHEMA_VERSION,
                              catalog_version=CATALOG_VERSION,
                              surface="SUPPORT_INLINE" if audience == "CUSTOMER" else "DESK_PANEL",
                              audience=audience, visibility=visibility, source_agent_run_id=source_run_id,
                              context_signature=signature, components=components, fallback_text=fallback,
                              expires_at=now + timedelta(hours=24))
        self.session.add(document)
        self.session.flush()
        self.record_event("ui.document.published", {"ui_id": str(ui_id), "revision": revision},
                          visibility=visibility, conversation_id=conversation.id)
        self.session.commit()
        return UIDocumentRead.model_validate(document)

    def current_ui(self, conversation_id):
        conversation = self.resource(Conversation, conversation_id)
        audience = "CUSTOMER" if self.actor.kind == "CUSTOMER" else "STAFF"
        active = self.session.scalar(select(UIDocument).where(
            UIDocument.tenant_id == self.actor.tenant_id,
            UIDocument.conversation_id == conversation.id,
            UIDocument.audience == audience, UIDocument.status == "ACTIVE",
        ))
        if active and active.expires_at and active.expires_at <= datetime.now(timezone.utc):
            return None
        if active and active.source_agent_run_id and not (
            conversation.collaboration_mode == "AI_LEAD" and conversation.reply_policy == "AI_AUTO"
        ):
            return None
        return UIDocumentRead.model_validate(active) if active else None

    def invoke_ui_action(self, conversation_id, request):
        if self.actor.kind != "CUSTOMER":
            raise ServiceError(403, "此低风险动作仅供当前客户使用。")
        conversation = self.resource(Conversation, conversation_id, lock=True)
        fingerprint = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        existing = self.session.scalar(select(UIActionInvocation).where(
            UIActionInvocation.tenant_id == self.actor.tenant_id,
            UIActionInvocation.actor_kind == self.actor.kind,
            UIActionInvocation.actor_id == self.actor.actor_id,
            UIActionInvocation.client_action_id == request.client_action_id,
        ))
        if existing:
            if existing.request_hash != fingerprint or existing.ui_document_id not in self.session.scalars(select(UIDocument.id).where(
                UIDocument.tenant_id == self.actor.tenant_id, UIDocument.conversation_id == conversation.id,
            )).all():
                raise ServiceError(409, "同一动作标识已用于不同请求。")
            return UIActionResult(client_action_id=request.client_action_id, status="ACCEPTED",
                                  task_id=existing.task_id, replayed=True)
        document = self.session.scalar(select(UIDocument).where(
            UIDocument.tenant_id == self.actor.tenant_id,
            UIDocument.conversation_id == conversation.id,
            UIDocument.audience == "CUSTOMER", UIDocument.status == "ACTIVE",
        ).with_for_update())
        if document is None or document.ui_id != request.ui_id or document.revision != request.revision:
            raise ServiceError(409, "UI 版本已更新，请刷新卡片后重试。")
        if document.expires_at and document.expires_at <= datetime.now(timezone.utc):
            raise ServiceError(409, "UI 卡片已过期，请刷新后重试。")
        if conversation.version != request.expected_conversation_version:
            raise ServiceError(409, "会话版本已更新，请刷新后重试。")
        if not any(component["type"] == "ActionBar" and any(
            action["action_id"] == request.action_id and action["intent"] == "REQUEST_ASSISTANCE"
            for action in component["actions"]
        ) for component in document.components):
            raise ServiceError(403, "UI 动作不在当前受信目录中。")
        if set(request.input) != {"reason"}:
            raise ServiceError(422, "请求人工协助只接受原因。")
        from serviceos_api.application.contracts import AssistanceRequest
        try:
            reason = AssistanceRequest.model_validate(request.input).reason
        except ValidationError:
            raise ServiceError(422, "请求人工协助原因无效。") from None
        task = self.request_assistance(conversation.id, AssistanceRequest(reason=reason), commit=False)
        self.session.add(UIActionInvocation(tenant_id=self.actor.tenant_id,
                                            ui_document_id=document.id, client_action_id=request.client_action_id,
                                            actor_kind=self.actor.kind, actor_id=self.actor.actor_id,
                                            request_hash=fingerprint, action_id=request.action_id,
                                            status="ACCEPTED", task_id=task.id,
                                            result={"task_id": str(task.id)}))
        self.record_event("ui.action.accepted", {"ui_id": str(document.ui_id), "revision": document.revision,
                                                 "task_id": str(task.id)}, visibility="PUBLIC",
                          conversation_id=conversation.id)
        self.session.commit()
        return UIActionResult(client_action_id=request.client_action_id, status="ACCEPTED",
                              task_id=task.id, replayed=False)

    def _task_read(self, task):
        assignment = self.session.scalar(select(TaskAssignment).where(
            TaskAssignment.tenant_id == task.tenant_id, TaskAssignment.task_id == task.id,
            TaskAssignment.ended_at.is_(None),
        ))
        return TaskRead.model_validate(task).model_copy(update={"assignee_id": assignment.staff_user_id if assignment else None})

    def tasks(self, conversation_id):
        if self.actor.kind != "STAFF":
            raise ServiceError(403, "只有客服可查看人工任务。")
        conversation = self.resource(Conversation, conversation_id)
        rows = self.session.scalars(select(ServiceTask).where(
            ServiceTask.tenant_id == self.actor.tenant_id,
            ServiceTask.conversation_id == conversation.id,
        ).order_by(ServiceTask.created_at, ServiceTask.id)).all()
        return [self._task_read(row) for row in rows]

    def claim_task(self, task_id, request):
        if self.actor.kind != "STAFF":
            raise ServiceError(403, "只有客服可接管任务。")
        task = self.session.scalar(select(ServiceTask).where(
            ServiceTask.id == task_id, ServiceTask.tenant_id == self.actor.tenant_id,
        ).with_for_update())
        if task is None:
            raise ServiceError(404, "任务不存在或无权访问。")
        if task.version != request.expected_version or task.status != "OPEN":
            raise ServiceError(409, "任务已被接管或版本已更新。")
        task.status = "ASSIGNED"
        task.version += 1
        self.session.add(TaskAssignment(tenant_id=self.actor.tenant_id, task_id=task.id,
                                        staff_user_id=self.actor.actor_id))
        self.record_event("assistance.assigned", {"task_id": str(task.id), "version": task.version},
                          visibility="INTERNAL", conversation_id=task.conversation_id)
        self.session.commit()
        return self._task_read(task)

    def proposals(self, conversation_id):
        if self.actor.kind != "STAFF":
            raise ServiceError(403, "只有客服可查看内部草稿。")
        conversation = self.resource(Conversation, conversation_id)
        rows = self.session.scalars(select(AgentProposal).where(
            AgentProposal.tenant_id == self.actor.tenant_id,
            AgentProposal.conversation_id == conversation.id,
        ).order_by(AgentProposal.created_at, AgentProposal.id)).all()
        return [ProposalRead.model_validate(row) for row in rows]

    def decide_proposal(self, proposal_id, request):
        if self.actor.kind != "STAFF":
            raise ServiceError(403, "只有客服可审阅内部草稿。")
        proposal = self.session.scalar(select(AgentProposal).where(
            AgentProposal.id == proposal_id, AgentProposal.tenant_id == self.actor.tenant_id,
        ).with_for_update())
        if proposal is None:
            raise ServiceError(404, "草稿不存在或无权访问。")
        digest = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        if proposal.decision_key is not None:
            if proposal.decision_key != request.decision_id or proposal.decision_hash != digest:
                raise ServiceError(409, "草稿已经决定，不能重复或改变审阅结果。")
            return ProposalRead.model_validate(proposal)
        if proposal.proposal_type == "REPLY" and request.decision == "APPROVED":
            self._publish_reviewed_reply(proposal)
        proposal.status = request.decision
        proposal.decision_key = request.decision_id
        proposal.decision_hash = digest
        proposal.decided_by = self.actor.actor_id
        proposal.decision_reason = request.reason
        self.record_event("approval.decided", {"proposal_id": str(proposal.id), "decision": proposal.status},
                          visibility="INTERNAL", conversation_id=proposal.conversation_id)
        self.session.commit()
        return ProposalRead.model_validate(proposal)

    def _publish_reviewed_reply(self, proposal):
        conversation = self.session.scalar(select(Conversation).where(
            Conversation.id == proposal.conversation_id,
            Conversation.tenant_id == proposal.tenant_id,
        ).with_for_update())
        if conversation is None or conversation.status != "ACTIVE" or (
            conversation.collaboration_mode == "HUMAN_LEAD" or conversation.reply_policy == "HUMAN_ONLY"
        ):
            raise ServiceError(409, "当前发言策略禁止 Agent 公开回复。")
        try:
            source_id = UUID(proposal.payload["source_message_id"])
        except (KeyError, ValueError, TypeError):
            raise ServiceError(409, "回复草稿缺少有效来源。") from None
        draft = self.session.scalar(select(Message).where(
            Message.id == source_id, Message.tenant_id == proposal.tenant_id,
            Message.conversation_id == conversation.id,
            Message.author_kind == "AGENT", Message.visibility == "INTERNAL",
            Message.client_message_id == proposal.agent_run_id,
        ))
        if draft is None:
            raise ServiceError(409, "内部回复草稿不可用。")
        fingerprint = hashlib.sha256(json.dumps({"proposal_id": str(proposal.id),
                                                  "content": draft.content}, sort_keys=True,
                                                 ensure_ascii=False).encode()).hexdigest()
        published = Message(tenant_id=proposal.tenant_id, conversation_id=conversation.id,
                            author_kind="AGENT", visibility="PUBLIC", content=draft.content,
                            related_case_id=draft.related_case_id,
                            client_message_id=proposal.id, request_hash=fingerprint)
        self.session.add(published)
        self.session.flush()
        self.record_event("message.created", {"message_id": str(published.id),
                                              "conversation_id": str(conversation.id)},
                          visibility="PUBLIC", conversation_id=conversation.id)

    def desk_case_summaries(self, conversation_id: UUID) -> list[DeskCaseSummary]:
        if self.actor.kind != "STAFF":
            raise ServiceError(403, "只有已授权客服可查看案例摘要。")
        conversation = self.resource(Conversation, conversation_id)
        cases = self.session.scalars(select(ServiceCase).join(
            CaseConversation, and_(CaseConversation.case_id == ServiceCase.id,
                                   CaseConversation.tenant_id == ServiceCase.tenant_id),
        ).where(ServiceCase.tenant_id == self.actor.tenant_id,
                CaseConversation.conversation_id == conversation.id,
                ServiceCase.customer_id == conversation.customer_id,
                ServiceCase.archived_at.is_(None)).order_by(ServiceCase.created_at, ServiceCase.id)).all()
        summaries = []
        for case in cases:
            facts = [SummaryFact(label="问题陈述", value=case.problem_text,
                                 source="case:customer_or_staff_statement", verification="CANDIDATE")]
            evidence = self.session.scalars(select(CaseEvidence).where(
                CaseEvidence.tenant_id == self.actor.tenant_id, CaseEvidence.case_id == case.id,
            ).order_by(CaseEvidence.observed_at, CaseEvidence.id)).all()
            facts.extend(SummaryFact(label=row.claim_type, value=row.summary,
                                     source=row.source, verification=row.validity) for row in evidence)
            links = self.session.scalars(select(CaseDevice).where(
                CaseDevice.tenant_id == self.actor.tenant_id, CaseDevice.case_id == case.id,
            ).order_by(CaseDevice.device_id)).all()
            device_ids = []
            for link in links:
                device = self.session.scalar(select(DevicePassport).where(
                    DevicePassport.tenant_id == self.actor.tenant_id,
                    DevicePassport.id == link.device_id,
                    DevicePassport.customer_id == case.customer_id,
                    DevicePassport.archived_at.is_(None),
                ))
                if device is None:
                    continue
                device_ids.append(device.id)
                if device.model:
                    facts.append(SummaryFact(label="设备型号", value=device.model,
                                             source=device.identity_source,
                                             verification=device.identity_status))
                device_facts = self.session.scalars(select(DeviceFact).where(
                    DeviceFact.tenant_id == self.actor.tenant_id,
                    DeviceFact.device_id == device.id,
                    DeviceFact.validity != "RETRACTED",
                ).order_by(DeviceFact.created_at, DeviceFact.id)).all()
                facts.extend(SummaryFact(label=row.fact_key,
                                         value=json.dumps(row.value, ensure_ascii=False),
                                         source=row.source, verification=row.validity)
                             for row in device_facts)
            summaries.append(DeskCaseSummary(case=CaseRead.model_validate(case), facts=facts,
                                             device_ids=device_ids))
        return summaries

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
        if visibility == "INTERNAL":
            self.session.add(AgentProposal(
                tenant_id=tenant_id, agent_run_id=run.id, conversation_id=conversation.id,
                proposal_type="REPLY", idempotency_key="reply-draft",
                payload={"summary": text, "source_message_id": str(message.id)},
            ))
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
