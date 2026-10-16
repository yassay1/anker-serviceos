import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import and_, or_, select, true

from serviceos_api.application.contracts import (
    CaseRead, DeskCaseSummary, EventPage, EventRead, MessagePage, MessageRead, MessageReceipt, ProposalRead,
    SummaryFact, TaskRead, UIActionResult, UIDocumentRead,
)
from serviceos_api.application.diagnostic_contracts import DiagnosticQuestion
from serviceos_api.application.business import BusinessService
from serviceos_api.application.errors import ServiceError
from serviceos_api.application.ui_catalog import CATALOG_VERSION, SCHEMA_VERSION, safe_text, validate_components
from serviceos_api.application.ui_visualizations import (
    case_process_flow, customer_case_progress, knowledge_metric_chart, knowledge_source_used_in_run,
)
from serviceos_api.persistence.models import (
    AgentProposal, AgentRun, CaseAction, CaseConversation, CaseDevice, CaseEvidence, CaseVerification, Conversation, ConversationEvent, DeviceFact,
    DevicePassport, DiagnosticAnswer, DiagnosticTask, Message, MessageJob, OutboxEvent, ServiceCase, ServiceTask, TaskAssignment,
    UIActionInvocation, UIDocument,
)


class ConversationService(BusinessService):
    """Only application entry for publishing and reading user-visible messages."""

    def __init__(self, session, actor, settings=None):
        super().__init__(session, actor)
        from serviceos_api.settings import Settings

        self.settings = settings or Settings.from_environment()

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
    def record_specialist_event(session, tenant_id: UUID, conversation_id: UUID, run_id: UUID,
                                lease_token: UUID, task_id: UUID, specialist_run_id: UUID, stage: str,
                                summary: str | None = None):
        """Persist a fixed specialist activity projection behind the parent run lease."""
        from uuid import uuid5

        from serviceos_api.application.agent_services import validate_agent_execution
        from serviceos_api.application.diagnostic_contracts import SpecialistEvent
        from serviceos_api.persistence.models import DiagnosticTask, SpecialistRun

        _, _, conversation, _ = validate_agent_execution(
            session, tenant_id, conversation_id, run_id, lease_token)
        task = session.scalar(select(DiagnosticTask).where(
            DiagnosticTask.id == task_id, DiagnosticTask.tenant_id == tenant_id,
            DiagnosticTask.conversation_id == conversation_id,
            DiagnosticTask.parent_agent_run_id == run_id,
        ).with_for_update())
        specialist = session.scalar(select(SpecialistRun).where(
            SpecialistRun.id == specialist_run_id, SpecialistRun.tenant_id == tenant_id,
            SpecialistRun.diagnostic_task_id == task_id,
            SpecialistRun.parent_agent_run_id == run_id,
            SpecialistRun.lease_token == lease_token,
        ).with_for_update())
        if task is None or specialist is None:
            raise ValueError("specialist_event_reference_invalid")
        stage_status = {"STARTED": "RUNNING", "LOOKUP": "RUNNING", "RESULT_READY": "COMPLETED",
                        "WAITING_CUSTOMER": "COMPLETED", "WAITING_STAFF": "COMPLETED", "FAILED": "FAILED"}
        task_status_ok = (task.status == "WAITING_CUSTOMER" if stage == "WAITING_CUSTOMER" else
                          task.status == "WAITING_STAFF" if stage == "WAITING_STAFF" else
                          task.status in ("COMPLETED", "WAITING_CUSTOMER", "WAITING_STAFF") if stage == "RESULT_READY" else
                          task.status == stage_status.get(stage))
        if stage not in stage_status or not task_status_ok or specialist.status != stage_status[stage]:
            raise ValueError("specialist_event_status_invalid")
        fixed = {
            "STARTED": "诊断专家已开始分析当前问题。",
            "LOOKUP": "诊断专家正在查阅已批准的售后资料。",
            "WAITING_CUSTOMER": "诊断专家需要补充一项信息。",
            "WAITING_STAFF": "诊断结果需要客服进一步核实。",
            "FAILED": "诊断专家本次分析未完成，服务助手将继续处理。",
        }
        payload = SpecialistEvent(
            task_id=task.id, specialist_run_id=specialist.id, stage=stage,
            summary=(summary if stage == "RESULT_READY" else fixed.get(stage, "")),
            certainty="HYPOTHESIS" if stage == "RESULT_READY" else "NONE",
        )
        event_id = uuid5(specialist.id, f"specialist:{stage}")
        existing = session.scalar(select(OutboxEvent).where(
            OutboxEvent.id == event_id, OutboxEvent.tenant_id == tenant_id,
            OutboxEvent.conversation_id == conversation_id,
        ))
        if existing is not None:
            return existing
        visibility = "PUBLIC" if (conversation.collaboration_mode == "AI_LEAD"
                                   and conversation.reply_policy == "AI_AUTO") else "INTERNAL"
        event = OutboxEvent(id=event_id, tenant_id=tenant_id, conversation_id=conversation_id,
                            type="specialist.activity", visibility=visibility, data=payload.model_dump(mode="json"),
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
            "follow_up.consented", "agent.progress", "specialist.activity",
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
        elif event.type == "specialist.activity":
            from serviceos_api.application.diagnostic_contracts import SpecialistEvent
            from serviceos_api.persistence.models import DiagnosticTask, SpecialistRun

            try:
                payload = SpecialistEvent.model_validate(data)
            except (ValidationError, ValueError):
                raise ServiceError(422, "专家活动字段或摘要未获授权。") from None
            task = session.scalar(select(DiagnosticTask).where(
                DiagnosticTask.id == payload.task_id, DiagnosticTask.tenant_id == event.tenant_id,
                DiagnosticTask.conversation_id == conversation.id,
            ))
            specialist = session.scalar(select(SpecialistRun).where(
                SpecialistRun.id == payload.specialist_run_id, SpecialistRun.tenant_id == event.tenant_id,
                SpecialistRun.diagnostic_task_id == payload.task_id,
            ))
            parent = session.scalar(select(AgentRun.id).where(
                AgentRun.id == specialist.parent_agent_run_id,
                AgentRun.tenant_id == event.tenant_id,
                AgentRun.conversation_id == conversation.id,
            )) if specialist else None
            if task is None or specialist is None or parent is None:
                raise ServiceError(422, "专家活动运行引用无效。")
            data = payload.model_dump(mode="json")
            # Never promote INTERNAL events. Recheck current publication policy at dispatch time.
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
        now = datetime.now(timezone.utc)
        expired_diagnostics = self.session.scalars(select(DiagnosticTask).where(
            DiagnosticTask.tenant_id == self.actor.tenant_id,
            DiagnosticTask.conversation_id == conversation.id,
            DiagnosticTask.status == "WAITING_CUSTOMER",
            DiagnosticTask.expires_at <= now,
        ).with_for_update()).all()
        for expired in expired_diagnostics:
            expired.status = "EXPIRED"
            expired.version += 1
        source = {"kind": "CONVERSATION_VIEW", "resource_id": str(conversation.id),
                  "resource_version": conversation.version, "binding": "assistance"}
        refs = {("CONVERSATION_VIEW", conversation.id): conversation.version}
        components = []
        source_run_id = None
        proposal_fallback = None
        if audience == "CUSTOMER":
            components.append({"id": "request-assistance", "type": "ActionBar",
                               "props": {"title": "需要真人协助？", "body": "请求会创建人工任务；你仍可继续发送文字消息。"},
                               "data_source": source,
                               "actions": [{"action_id": "request-human-assistance", "intent": "REQUEST_ASSISTANCE",
                                            "input_schema_ref": "serviceos://ui-inputs/assistance-request/v1"}],
                               "children": []})
            linked_cases = self.session.scalars(select(ServiceCase).join(CaseConversation, and_(
                CaseConversation.case_id == ServiceCase.id,
                CaseConversation.tenant_id == ServiceCase.tenant_id,
            )).where(
                CaseConversation.tenant_id == self.actor.tenant_id,
                CaseConversation.conversation_id == conversation.id,
                ServiceCase.tenant_id == self.actor.tenant_id,
                ServiceCase.customer_id == conversation.customer_id,
                ServiceCase.archived_at.is_(None),
            ).order_by(ServiceCase.created_at.desc(), ServiceCase.id).limit(3)).all()
            for case in linked_cases:
                if len(components) >= 10:
                    break
                task = self.session.scalar(select(ServiceTask).where(
                    ServiceTask.tenant_id == self.actor.tenant_id,
                    ServiceTask.conversation_id == conversation.id,
                    ServiceTask.case_id == case.id,
                    ServiceTask.status != "CLOSED",
                ).order_by(ServiceTask.created_at.desc(), ServiceTask.id.desc()).limit(1))
                action = self.session.scalar(select(CaseAction).where(
                    CaseAction.tenant_id == self.actor.tenant_id, CaseAction.case_id == case.id,
                ).order_by(CaseAction.created_at.desc(), CaseAction.id.desc()).limit(1))
                verification = self.session.scalar(select(CaseVerification).where(
                    CaseVerification.tenant_id == self.actor.tenant_id, CaseVerification.case_id == case.id,
                ).order_by(CaseVerification.created_at.desc(), CaseVerification.id.desc()).limit(1))
                progress = customer_case_progress(case, task, action, verification)
                refs[("CASE_VIEW", case.id)] = case.version
                components.append({"id": f"case-progress-{str(case.id)[:8]}", "type": "ProgressTimeline",
                                   "props": progress,
                                   "data_source": {"kind": "CASE_VIEW", "resource_id": str(case.id),
                                                   "resource_version": case.version, "binding": "progress"},
                                   "actions": [], "children": []})
            if conversation.collaboration_mode == "AI_LEAD" and conversation.reply_policy == "AI_AUTO":
                waiting_diagnostic = self.session.scalar(select(DiagnosticTask).where(
                    DiagnosticTask.tenant_id == self.actor.tenant_id,
                    DiagnosticTask.conversation_id == conversation.id,
                    DiagnosticTask.status == "WAITING_CUSTOMER",
                    DiagnosticTask.expires_at > datetime.now(timezone.utc),
                ).order_by(DiagnosticTask.created_at.desc(), DiagnosticTask.id).limit(1))
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
                    AgentRun.id != waiting_diagnostic.parent_agent_run_id if waiting_diagnostic else true(),
                    AgentRun.created_at > latest_customer_turn if latest_customer_turn else true(),
                ).order_by(AgentRun.created_at.desc()).limit(5)).all()
                verified_models = {model.upper() for model in self.session.scalars(
                    select(DevicePassport.model).join(CaseDevice, and_(
                        CaseDevice.device_id == DevicePassport.id,
                        CaseDevice.tenant_id == DevicePassport.tenant_id,
                    )).join(CaseConversation, and_(
                        CaseConversation.case_id == CaseDevice.case_id,
                        CaseConversation.tenant_id == CaseDevice.tenant_id,
                    )).join(ServiceCase, and_(
                        ServiceCase.id == CaseConversation.case_id,
                        ServiceCase.tenant_id == CaseConversation.tenant_id,
                    )).where(
                        CaseConversation.tenant_id == self.actor.tenant_id,
                        CaseConversation.conversation_id == conversation.id,
                        ServiceCase.customer_id == conversation.customer_id,
                        DevicePassport.customer_id == conversation.customer_id,
                        DevicePassport.identity_status == "VERIFIED",
                        DevicePassport.archived_at.is_(None),
                    )
                ).all() if model}
                from serviceos_api.application.rich_reply import RISK

                for run in runs:
                    proposal = (run.result_payload or {}).get("ui_proposal")
                    source_message = self.session.get(Message, run.message_id)
                    diagnostic = self.session.scalar(select(DiagnosticTask).where(
                        DiagnosticTask.tenant_id == self.actor.tenant_id,
                        DiagnosticTask.conversation_id == conversation.id,
                        DiagnosticTask.parent_agent_run_id == run.id,
                    ).order_by(DiagnosticTask.created_at.desc(), DiagnosticTask.id).limit(1))
                    safety_triggered = bool(
                        (diagnostic and ((diagnostic.result_payload or {}).get("next_step") or {}).get("kind") == "SAFETY_STOP")
                        or (source_message and RISK.search(" ".join(
                            part.get("text", "") for part in source_message.content
                        )))
                    )
                    public_message = self.session.scalar(select(Message.id).where(
                        Message.tenant_id == self.actor.tenant_id,
                        Message.conversation_id == conversation.id,
                        Message.client_message_id == run.id,
                        Message.visibility == "PUBLIC",
                    ))
                    if proposal and proposal.get("audience") == "CUSTOMER" and public_message:
                        if not safety_triggered:
                            try:
                                proposal_fallback = safe_text(proposal.get("fallback_text"), limit=500)
                            except ServiceError:
                                proposal_fallback = None
                        hints = set(proposal.get("component_hints", []))
                        options = proposal.get("options") or []
                        run_components = []
                        if "QuestionForm" in hints or "ChoiceGroup" in hints:
                            # Server-side promotion: clickable options never get dropped just
                            # because the model hinted the free-text form type.
                            kind = "ChoiceGroup" if len(options) >= 2 else "QuestionForm"
                            run_components.append({"id": "agent-choice" if kind == "ChoiceGroup" else "agent-question",
                                                   "type": kind,
                                                   "props": {"title": "下一步需要的信息", "body": proposal["purpose"]},
                                                   "data_source": {"kind": "AGENT_RUN_VIEW", "resource_id": str(run.id),
                                                                   "resource_version": 1, "binding": "question"},
                                                   "actions": [], "children": [],
                                                   "options": options if kind == "ChoiceGroup" else []})
                        if ("KnowledgeMetricChart" in hints and
                                knowledge_source_used_in_run(proposal.get("knowledge_source_id", ""),
                                                             run.result_payload or {})):
                            chart = knowledge_metric_chart(proposal.get("knowledge_source_id", ""), verified_models)
                            if chart:
                                run_components.append({"id": "knowledge-metric", "type": "KnowledgeMetricChart",
                                                       "props": {"title": "加热功能的额外电量消耗估算",
                                                                 "body": chart["note"]},
                                                       "data_source": {"kind": "AGENT_RUN_VIEW", "resource_id": str(run.id),
                                                                       "resource_version": 1, "binding": "metric"},
                                                       "actions": [], "children": [], "chart": chart})
                        if run_components:
                            refs[("AGENT_RUN_VIEW", run.id)] = 1
                            components.extend(run_components)
                            source_run_id = run.id
                            break
                if waiting_diagnostic is not None and len(components) < 12:
                    question = DiagnosticQuestion.model_validate(waiting_diagnostic.question_payload)
                    question_type = "ChoiceGroup" if len(question.options) >= 2 else "QuestionForm"
                    components.append({
                        "id": "diagnostic-question", "type": question_type,
                        "props": {"title": "诊断专家需要补充的信息", "body": question.prompt},
                        "data_source": {"kind": "DIAGNOSTIC_TASK_VIEW", "resource_id": str(waiting_diagnostic.id),
                                        "resource_version": waiting_diagnostic.version, "binding": "question",
                                        "question_revision": waiting_diagnostic.question_revision},
                        "actions": [{"action_id": "submit-diagnostic-answer", "intent": "SUBMIT_DIAGNOSTIC_ANSWER",
                                     "input_schema_ref": "serviceos://ui-inputs/diagnostic-answer/v1"}],
                        "children": [], "options": [{"label": item, "value": f"answer-{index + 1}"}
                                                       for index, item in enumerate(question.options)] if question_type == "ChoiceGroup" else [],
                    })
                    refs[("DIAGNOSTIC_TASK_VIEW", waiting_diagnostic.id)] = waiting_diagnostic.version
                    source_run_id = waiting_diagnostic.parent_agent_run_id
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
            latest_customer_turn = self.session.scalar(select(Message.created_at).where(
                Message.tenant_id == self.actor.tenant_id, Message.conversation_id == conversation.id,
                Message.author_kind == "CUSTOMER", Message.visibility == "PUBLIC",
            ).order_by(Message.created_at.desc(), Message.id.desc()).limit(1))
            internal_runs = self.session.scalars(select(AgentRun).where(
                AgentRun.tenant_id == self.actor.tenant_id,
                AgentRun.conversation_id == conversation.id,
                AgentRun.status == "COMPLETED",
                AgentRun.created_at > latest_customer_turn if latest_customer_turn else true(),
            ).order_by(AgentRun.created_at.desc()).limit(5)).all()
            cases_by_id = {str(summary.case.id): summary.case for summary in summaries}
            for run in internal_runs:
                proposal = (run.result_payload or {}).get("ui_proposal")
                if not proposal or proposal.get("audience") != "STAFF" or "CaseProcessFlow" not in proposal.get("component_hints", []):
                    continue
                case = cases_by_id.get(proposal.get("case_id"))
                if case is None:
                    continue
                task = self.session.scalar(select(ServiceTask).where(
                    ServiceTask.tenant_id == self.actor.tenant_id, ServiceTask.conversation_id == conversation.id,
                    ServiceTask.case_id == case.id,
                ).order_by(ServiceTask.created_at.desc(), ServiceTask.id.desc()).limit(1))
                action = self.session.scalar(select(CaseAction).where(
                    CaseAction.tenant_id == self.actor.tenant_id, CaseAction.case_id == case.id,
                ).order_by(CaseAction.created_at.desc(), CaseAction.id.desc()).limit(1))
                verification = self.session.scalar(select(CaseVerification).where(
                    CaseVerification.tenant_id == self.actor.tenant_id, CaseVerification.case_id == case.id,
                ).order_by(CaseVerification.created_at.desc(), CaseVerification.id.desc()).limit(1))
                refs[("CASE_VIEW", case.id)] = case.version
                if task is not None:
                    refs[("TASK_VIEW", task.id)] = task.version
                flow = case_process_flow(case, task, action, verification)
                if len(components) >= 12:
                    break
                components.append({"id": f"case-flow-{str(case.id)[:8]}", "type": "CaseProcessFlow",
                                   "props": {"title": "案例办理流程", "body": "节点状态来自当前案例、任务、模拟动作和客户核验记录。"},
                                   "data_source": {"kind": "CASE_VIEW", "resource_id": str(case.id),
                                                   "resource_version": case.version, "binding": "process_flow"},
                                   "actions": [], "children": [], "flow": flow})
                source_run_id = run.id
                break
            if not components:
                components.append({"id": "conversation-progress", "type": "ProgressTimeline",
                                   "props": {"title": "会话状态", "body": "会话已建立；尚无关联案例或人工任务。",
                                             "status": conversation.status},
                                   "data_source": {"kind": "CONVERSATION_VIEW", "resource_id": str(conversation.id),
                                                   "resource_version": conversation.version, "binding": "overview"},
                                   "actions": [], "children": []})
        components = validate_components(components[:12], audience, refs)
        fallback = proposal_fallback or safe_text("交互卡暂不可用，请继续使用文字消息。")
        signature = hashlib.sha256(json.dumps({"components": components, "mode": conversation.collaboration_mode,
                                               "policy": conversation.reply_policy}, sort_keys=True,
                                              ensure_ascii=False).encode()).hexdigest()
        active = self.session.scalar(select(UIDocument).where(
            UIDocument.tenant_id == self.actor.tenant_id,
            UIDocument.conversation_id == conversation.id,
            UIDocument.audience == audience, UIDocument.status == "ACTIVE",
        ).with_for_update())
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
        if active and audience == "CUSTOMER" and active.source_agent_run_id and not (
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
            diagnostic_task_id = (UUID(existing.result["diagnostic_task_id"])
                                  if existing.result and existing.result.get("diagnostic_task_id") else None)
            return UIActionResult(client_action_id=request.client_action_id, status="ACCEPTED",
                                  task_id=existing.task_id, diagnostic_task_id=diagnostic_task_id, replayed=True)
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
        if request.action_id == "submit-diagnostic-answer":
            return self._submit_diagnostic_answer(conversation, document, request, fingerprint)
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

    def _submit_diagnostic_answer(self, conversation, document, request, fingerprint):
        if (conversation.status != "ACTIVE" or conversation.collaboration_mode != "AI_LEAD"
                or conversation.reply_policy != "AI_AUTO"):
            raise ServiceError(409, "当前协作策略已变化，请刷新交互卡后重试。")
        component = next((item for item in document.components
                          if item.get("type") in ("QuestionForm", "ChoiceGroup")
                          and item.get("data_source", {}).get("kind") == "DIAGNOSTIC_TASK_VIEW"
                          and item.get("actions") == [{"action_id": "submit-diagnostic-answer",
                              "intent": "SUBMIT_DIAGNOSTIC_ANSWER",
                              "input_schema_ref": "serviceos://ui-inputs/diagnostic-answer/v1"}]), None)
        if component is None:
            raise ServiceError(403, "诊断回答动作不在当前受信交互卡中。")
        if set(request.input) != {"task_version", "question_revision", "answer"}:
            raise ServiceError(422, "诊断回答字段无效。")
        task_version = request.input.get("task_version")
        question_revision = request.input.get("question_revision")
        answer_text = request.input.get("answer")
        if (type(task_version) is not int or type(question_revision) is not int
                or not isinstance(answer_text, str) or not answer_text.strip() or len(answer_text) > 1000):
            raise ServiceError(422, "诊断回答不能为空或字段格式无效。")
        answer_text = " ".join(answer_text.split())
        source = component["data_source"]
        task = self.session.scalar(select(DiagnosticTask).where(
            DiagnosticTask.id == source["resource_id"], DiagnosticTask.tenant_id == self.actor.tenant_id,
            DiagnosticTask.conversation_id == conversation.id,
        ).with_for_update())
        if (task is None or task.status != "WAITING_CUSTOMER" or task.version != source["resource_version"]
                or task.version != task_version or task.question_revision != question_revision):
            raise ServiceError(409, "诊断问题已更新或已提交，请刷新后查看当前状态。")
        if source.get("question_revision") != task.question_revision:
            raise ServiceError(409, "诊断问题版本已更新，请刷新后重试。")
        if task.expires_at is None or task.expires_at <= datetime.now(timezone.utc):
            task.status = "EXPIRED"
            task.version += 1
            self.session.commit()
            raise ServiceError(409, "诊断问题已过期，请继续使用文字消息或请求人工协助。")
        question = DiagnosticQuestion.model_validate(task.question_payload)
        options = component.get("options") or []
        if options and answer_text not in {option["label"] for option in options}:
            raise ServiceError(422, "请使用当前问题中的选项作答。")
        if self.actor.actor_id != conversation.customer_id:
            raise ServiceError(403, "只有当前客户可以回答此诊断问题。")
        message_hash = hashlib.sha256(
            f"diagnostic-answer:{request.client_action_id}:{task.id}:{task.question_revision}:{answer_text}".encode()
        ).hexdigest()
        message = Message(
            tenant_id=self.actor.tenant_id, conversation_id=conversation.id, author_kind="CUSTOMER",
            visibility="PUBLIC", author_customer_id=self.actor.actor_id,
            content=[{"type": "text", "text": answer_text}], related_case_id=task.case_id,
            client_message_id=request.client_action_id, request_hash=message_hash,
        )
        self.session.add(message)
        self.session.flush()
        answer = DiagnosticAnswer(
            tenant_id=self.actor.tenant_id, diagnostic_task_id=task.id,
            question_revision=task.question_revision, client_action_id=request.client_action_id,
            customer_id=self.actor.actor_id, source_message_id=message.id, answer=answer_text,
        )
        self.session.add(answer)
        self.session.flush()
        accepted_question_revision = task.question_revision
        task.status = "RUNNING"
        task.version += 1
        self.session.add(MessageJob(tenant_id=self.actor.tenant_id, message_id=message.id,
                                   conversation_id=conversation.id))
        self.session.add(UIActionInvocation(
            tenant_id=self.actor.tenant_id, ui_document_id=document.id,
            client_action_id=request.client_action_id, actor_kind=self.actor.kind, actor_id=self.actor.actor_id,
            request_hash=fingerprint, action_id=request.action_id, status="ACCEPTED", task_id=None,
            result={"diagnostic_task_id": str(task.id), "answer_id": str(answer.id)},
        ))
        self.record_event("message.created", {"message_id": str(message.id), "conversation_id": str(conversation.id)},
                          visibility="PUBLIC", conversation_id=conversation.id)
        self.record_event("ui.action.accepted", {"ui_id": str(document.ui_id), "revision": document.revision,
                                                  "diagnostic_task_id": str(task.id),
                                                  "question_revision": accepted_question_revision},
                          visibility="PUBLIC", conversation_id=conversation.id)
        self.session.commit()
        return UIActionResult(client_action_id=request.client_action_id, status="ACCEPTED",
                              diagnostic_task_id=task.id, replayed=False)

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
        payload = request.model_dump(mode="json")
        # Preserve fingerprints of pre-upgrade text sends and their unknown-result retries.
        if request.reply_to_message_id is None:
            payload.pop('reply_to_message_id', None)
        payload |= {"actor_id": str(self.actor.actor_id), "actor_kind": self.actor.kind}
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
        if request.reply_to_message_id is not None:
            # Same conversation row lock as ordinary sends: two clicks/tabs cannot both
            # advance a single published follow-up. Exact-id retries above still replay.
            source = self.session.scalar(select(Message).where(
                Message.tenant_id == self.actor.tenant_id, Message.conversation_id == conversation.id,
                Message.visibility == 'PUBLIC').order_by(Message.created_at.desc(), Message.id.desc()).limit(1))
            allowed = []
            if source is not None and source.author_kind == 'AGENT':
                for part in source.content:
                    rich = part.get('rich')
                    if isinstance(rich, dict):
                        allowed.extend(item.get('message') for item in rich.get('quick_replies', []) if isinstance(item, dict))
            sent = '\n'.join(part.text for part in request.content).strip()
            if (self.actor.kind != 'CUSTOMER' or request.visibility != 'PUBLIC' or
                conversation.collaboration_mode != 'AI_LEAD' or conversation.reply_policy != 'AI_AUTO' or
                source is None or source.id != request.reply_to_message_id or sent not in allowed or
                source.related_case_id != request.related_case_id):
                raise ServiceError(409, '此快捷追问已失效，请查看最新消息或直接输入问题。', code='QUICK_REPLY_STALE')
            linked_cases = self.session.scalars(select(ServiceCase).join(CaseConversation, CaseConversation.case_id == ServiceCase.id).where(
                CaseConversation.conversation_id == conversation.id, ServiceCase.tenant_id == self.actor.tenant_id,
                ServiceCase.customer_id == conversation.customer_id, ServiceCase.archived_at.is_(None))).all()
            relevant = [case for case in linked_cases if case.id == source.related_case_id] if source.related_case_id else linked_cases
            if relevant and all(case.status in ('RESOLVED', 'CLOSED') for case in relevant):
                raise ServiceError(409, '关联问题已结束，请直接描述新的服务问题。', code='QUICK_REPLY_STALE')
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

        diagnostic_task = self.session.scalar(select(DiagnosticTask).where(
            DiagnosticTask.tenant_id == tenant_id,
            DiagnosticTask.conversation_id == conversation.id,
            DiagnosticTask.parent_agent_run_id == run.id,
        ).order_by(DiagnosticTask.created_at.desc(), DiagnosticTask.id).limit(1))
        next_kind = (((diagnostic_task.result_payload or {}).get("next_step") or {}).get("kind")
                     if diagnostic_task is not None else None)
        if next_kind == "SAFETY_STOP":
            text = ("请先停止使用和测试设备，不要拆解或短接。若出现冒烟、异味、鼓包或异常发热，请远离易燃物并联系人工客服协助。"
                    "当前设备状态尚未核验，问题尚未解决。")
        elif next_kind == "HUMAN_REVIEW":
            text = "当前信息需要人工客服进一步核实。你可以使用“需要真人协助”创建人工服务任务；当前问题尚未解决。"

        visibility = "PUBLIC" if (
            conversation.collaboration_mode == "AI_LEAD"
            and conversation.reply_policy == "AI_AUTO"
        ) else "INTERNAL"
        from serviceos_api.application.rich_reply import RISK, SAFETY_TEXT
        source_message = self.session.scalar(select(Message).where(Message.id == run.message_id,
            Message.tenant_id == tenant_id, Message.conversation_id == conversation.id))
        safety = next_kind == "SAFETY_STOP" or bool(
            source_message and RISK.search(' '.join(part.get('text', '') for part in source_message.content)))
        if safety:
            # A language model must not override the user's stop-use safety boundary.
            text = SAFETY_TEXT
        guard_decision = None
        if visibility == "PUBLIC" and self.settings.publication_guard:
            from serviceos_api.application.publication_guard import PublicationGuard
            from serviceos_api.persistence.models import PublicationGuardDecision

            customer_text = " ".join(part.get("text", "") for part in
                                     (source_message.content if source_message else []))
            outcome = PublicationGuard(self.session, self.settings, tenant_id).check(
                text, run, conversation.id, customer_text)
            outcome.verifier["latency_ms"] = outcome.latency_ms
            guard_decision = PublicationGuardDecision(
                tenant_id=tenant_id, conversation_id=conversation.id, run_id=run.id,
                decision=outcome.decision, reason_codes=outcome.reason_codes,
                entities={"items": outcome.entities}, verifier=outcome.verifier,
                reply_text=text)
            self.session.add(guard_decision)
            self.session.flush()
            if outcome.decision == "BLOCKED":
                visibility = "INTERNAL"
        content = [{"type": "text", "text": text}]
        draft_rich = (run.result_payload or {}).get('rich_reply')
        if safety and not draft_rich:
            draft_rich = {'schema_version': 1, 'blocks': [], 'quick_replies': []}
        if draft_rich:
            from serviceos_api.application.rich_reply import project_reply
            rich = project_reply(self.session, conversation, run, draft_rich, related_case_id,
                                 force_safety=next_kind == "SAFETY_STOP")
            if rich and (rich['blocks'] or rich['quick_replies']):
                content[0]['rich'] = rich
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
            proposal = AgentProposal(
                tenant_id=tenant_id, agent_run_id=run.id, conversation_id=conversation.id,
                proposal_type="REPLY", idempotency_key="reply-draft",
                payload={"summary": text, "source_message_id": str(message.id)},
            )
            self.session.add(proposal)
            self.session.flush()
            if guard_decision is not None:
                guard_decision.proposal_id = proposal.id
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
