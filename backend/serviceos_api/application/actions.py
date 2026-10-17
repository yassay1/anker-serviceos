"""Application boundary for one explicitly simulated service operation."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select

from serviceos_api.application.contracts import (
    ActionApprovalDecision, ActionApprovalRead, CaseActionRead, MockActionRequest, MockReceiptRead,
)
from serviceos_api.application.errors import ServiceError
from serviceos_api.application.evidence import enqueue_case_events
from serviceos_api.application.business import BusinessService
from serviceos_api.application.verification import CONFIRMED_CONDITIONS
from serviceos_api.persistence.models import (
    AgentProposal, AgentRun, CaseAction, CaseActionApproval, CaseConversation, Conversation,
    ResolutionContract, ServiceCase,
)


def _hash(fields: dict) -> str:
    return hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class ActionReceipt(Protocol):
    result: str
    external_reference: str
    received_at: datetime


def claim_mock_action(action: CaseAction, token: UUID, now: datetime, lease_seconds: int) -> bool:
    """Apply the execution lease state; return whether this claim may only reconcile."""
    reconcile_only = action.status != "APPROVED"
    action.status = "UNKNOWN" if reconcile_only else "EXECUTING"
    action.attempt_count += 1
    action.version += 1
    action.lease_token = token
    action.lease_expires_at = now + timedelta(seconds=lease_seconds)
    action.last_error_code = None
    return reconcile_only


def finish_mock_action(session, action: CaseAction, receipt: ActionReceipt | None,
                       error_code: str | None, now: datetime) -> None:
    """Record the authoritative Mock receipt or preserve an uncertain outcome."""
    if receipt is None:
        action.status = "UNKNOWN"
        action.last_error_code = error_code or "mock_receipt_missing"
        action.available_at = now + timedelta(seconds=min(300, 2 ** min(action.attempt_count, 8)))
    else:
        action.status = receipt.result
        action.receipt_result = receipt.result
        action.receipt_reference = receipt.external_reference
        action.receipt_at = receipt.received_at
        action.last_error_code = None
        enqueue_case_events(session, action.tenant_id, action.case_id, "action.state_changed", {
            "action_id": str(action.id), "case_id": str(action.case_id),
            "status": action.status, "adapter": "MOCK",
        }, "PUBLIC")
    action.version += 1
    action.lease_token = None
    action.lease_expires_at = None


def _persist_action_request(session, case: ServiceCase, command: MockActionRequest, *,
                            requested_by: UUID | None, requested_by_agent_run_id: UUID | None):
    reason = command.reason.strip()
    if len(reason) < 3:
        raise ServiceError(422, "售后动作原因不能为空。", code="ACTION_REASON_REQUIRED")
    fingerprint = _hash({"kind": command.action_kind, "proposal": str(command.source_proposal_id),
                         "reason": reason, "remedy": command.remedy_type})
    previous = session.scalar(select(CaseAction).where(
        CaseAction.tenant_id == case.tenant_id, CaseAction.case_id == case.id,
        CaseAction.client_action_id == command.client_action_id,
    ).with_for_update().execution_options(populate_existing=True))
    if previous is not None:
        if (previous.request_hash != fingerprint or previous.requested_by != requested_by
                or previous.requested_by_agent_run_id != requested_by_agent_run_id):
            raise ServiceError(409, "动作编号已用于其他请求。", code="IDEMPOTENCY_CONFLICT")
        approval = session.scalar(select(CaseActionApproval).where(
            CaseActionApproval.tenant_id == case.tenant_id,
            CaseActionApproval.action_id == previous.id,
        ))
        if approval is None:
            raise ServiceError(503, "售后动作审批记录缺失。", code="ACTION_APPROVAL_MISSING")
        return previous, approval, False
    if case.version != command.expected_case_version:
        raise ServiceError(409, "案例版本已更新，请刷新后重试。", code="STALE_VERSION",
                           current_version=case.version)
    if case.status in ("RESOLVED", "CLOSED"):
        raise ServiceError(409, "已解决或关闭的案例不能发起新动作。", code="CASE_NOT_ACTIONABLE")
    action = CaseAction(
        tenant_id=case.tenant_id, case_id=case.id, client_action_id=command.client_action_id,
        request_hash=fingerprint, action_kind=command.action_kind, adapter="MOCK",
        status="WAITING_APPROVAL", requested_by=requested_by,
        requested_by_agent_run_id=requested_by_agent_run_id,
        source_proposal_id=command.source_proposal_id, reason=reason,
        remedy_type=command.remedy_type,
    )
    session.add(action)
    session.flush()
    session.add(ResolutionContract(
        tenant_id=case.tenant_id, case_id=case.id, action_id=action.id,
        version=1, conditions=CONFIRMED_CONDITIONS,
    ))
    approval = CaseActionApproval(tenant_id=case.tenant_id, action_id=action.id)
    session.add(approval)
    case.version += 1
    enqueue_case_events(session, case.tenant_id, case.id, "action.requested",
                        {"action_id": str(action.id), "case_id": str(case.id)}, "INTERNAL")
    session.flush()
    return action, approval, True


def request_mock_action_from_agent(session, *, tenant_id: UUID, conversation_id: UUID,
                                   run: AgentRun, remedy_type: str, reason: str) -> CaseActionRead:
    """Create a pending Mock action for the sole Case linked to this validated AgentRun."""
    if run.tenant_id != tenant_id or run.conversation_id != conversation_id or run.status != "RUNNING":
        raise ServiceError(403, "Agent 执行上下文无效。", code="AGENT_ACTION_CONTEXT_INVALID")
    reason = " ".join(reason.split()) if isinstance(reason, str) else ""
    if len(reason) < 3 or len(reason) > 1000:
        raise ServiceError(422, "售后动作原因长度无效。", code="ACTION_REASON_REQUIRED")
    if remedy_type not in ("REPAIR", "RESHIP", "REFER_SELLER", "DECLINE"):
        raise ServiceError(422, "不支持的售后动作类型。", code="ACTION_REMEDY_NOT_ALLOWED")
    conversation = session.scalar(select(Conversation).where(
        Conversation.tenant_id == tenant_id, Conversation.id == conversation_id,
    ))
    if conversation is None:
        raise ServiceError(404, "当前会话不存在或不可见。")
    linked_case_ids = list(session.scalars(select(CaseConversation.case_id).where(
        CaseConversation.tenant_id == tenant_id,
        CaseConversation.conversation_id == conversation_id,
    )).all())
    if len(linked_case_ids) != 1:
        code = "CASE_LINK_REQUIRED" if not linked_case_ids else "CASE_LINK_AMBIGUOUS"
        raise ServiceError(409, "当前会话必须且只能关联一个服务案例，才能提交售后动作。", code=code)
    case = session.scalar(select(ServiceCase).where(
        ServiceCase.tenant_id == tenant_id, ServiceCase.id == linked_case_ids[0],
        ServiceCase.customer_id == conversation.customer_id, ServiceCase.archived_at.is_(None),
    ).with_for_update())
    if case is None:
        raise ServiceError(404, "关联服务案例不存在或不可见。")
    command = MockActionRequest(
        client_action_id=uuid5(NAMESPACE_URL, f"serviceos-agent-mock-action:{tenant_id}:{run.id}"),
        expected_case_version=case.version, action_kind="MOCK_SERVICE_REQUEST",
        remedy_type=remedy_type, reason=reason,
    )
    outstanding = session.scalar(select(CaseAction).where(
        CaseAction.tenant_id == tenant_id, CaseAction.case_id == case.id,
        CaseAction.status.in_(("WAITING_APPROVAL", "APPROVED", "EXECUTING", "UNKNOWN")),
        CaseAction.client_action_id != command.client_action_id,
    ).with_for_update())
    if outstanding is not None:
        raise ServiceError(409, "此案例已有待审批、执行或对账的售后动作。", code="ACTION_UNSETTLED")
    action, approval, _ = _persist_action_request(
        session, case, command, requested_by=None, requested_by_agent_run_id=run.id,
    )
    session.commit()
    receipt = None
    if action.receipt_reference is not None:
        receipt = MockReceiptRead(external_reference=action.receipt_reference,
                                  result=action.receipt_result, received_at=action.receipt_at)
    return CaseActionRead(
        id=action.id, case_id=action.case_id, action_kind=action.action_kind,
        remedy_type=action.remedy_type, adapter=action.adapter, status=action.status,
        version=action.version, approval_id=approval.id, receipt=receipt,
        created_at=action.created_at,
    )


class ServiceActionService(BusinessService):
    def _staff(self) -> None:
        if self.actor.kind != "STAFF" or self.actor.role not in ("SUPPORT", "SUPERVISOR", "ADMIN"):
            raise ServiceError(403, "当前身份无权办理售后动作。", code="ACTION_FORBIDDEN")

    def _action(self, action_id: UUID) -> CaseAction:
        action = self.session.scalar(select(CaseAction).where(
            CaseAction.tenant_id == self.actor.tenant_id, CaseAction.id == action_id,
        ))
        if action is None:
            raise ServiceError(404, "售后动作不存在或不可见。")
        self.resource(ServiceCase, action.case_id)
        return action

    def _approval_for(self, action: CaseAction) -> CaseActionApproval:
        approval = self.session.scalar(select(CaseActionApproval).where(
            CaseActionApproval.tenant_id == self.actor.tenant_id,
            CaseActionApproval.action_id == action.id,
        ))
        if approval is None:
            raise ServiceError(503, "售后动作审批记录缺失。", code="ACTION_APPROVAL_MISSING")
        return approval

    def _read(self, action: CaseAction, approval_id: UUID | None = None) -> CaseActionRead:
        if approval_id is None:
            approval_id = self._approval_for(action).id
        receipt = None
        if action.receipt_reference is not None:
            receipt = MockReceiptRead(external_reference=action.receipt_reference,
                                      result=action.receipt_result, received_at=action.receipt_at)
        return CaseActionRead(
            id=action.id, case_id=action.case_id, action_kind=action.action_kind,
            remedy_type=action.remedy_type, adapter=action.adapter, status=action.status, version=action.version,
            approval_id=approval_id, receipt=receipt, created_at=action.created_at,
            reason=action.reason if self.actor.kind == "STAFF" else None,
            requested_by=action.requested_by if self.actor.kind == "STAFF" else None,
        )

    def request(self, case_id: UUID, command: MockActionRequest) -> CaseActionRead:
        self._staff()
        case = self.resource(ServiceCase, case_id, lock=True)
        if command.source_proposal_id is not None:
            proposal = self.session.scalar(select(AgentProposal).join(
                CaseConversation, (CaseConversation.conversation_id == AgentProposal.conversation_id)
                & (CaseConversation.tenant_id == AgentProposal.tenant_id),
            ).where(AgentProposal.tenant_id == case.tenant_id,
                    AgentProposal.id == command.source_proposal_id,
                    AgentProposal.proposal_type == "ACTION", CaseConversation.case_id == case.id))
            if proposal is None:
                raise ServiceError(404, "关联的内部动作草稿不存在或不属于此案例。")
        action, approval, created = _persist_action_request(
            self.session, case, command, requested_by=self.actor.actor_id,
            requested_by_agent_run_id=None,
        )
        if not created:
            return self._read(action, approval.id)
        self.session.commit()
        return self._read(action, approval.id)

    def list_actions(self, case_id: UUID) -> list[CaseActionRead]:
        case = self.resource(ServiceCase, case_id)
        actions = self.session.scalars(select(CaseAction).where(
            CaseAction.tenant_id == case.tenant_id, CaseAction.case_id == case.id,
        ).order_by(CaseAction.created_at, CaseAction.id)).all()
        return [self._read(action) for action in actions]

    def read_action(self, action_id: UUID) -> CaseActionRead:
        return self._read(self._action(action_id))

    def list_approvals(self, case_id: UUID) -> list[ActionApprovalRead]:
        self._staff()
        case = self.resource(ServiceCase, case_id)
        rows = self.session.scalars(select(CaseActionApproval).join(
            CaseAction, (CaseAction.id == CaseActionApproval.action_id)
            & (CaseAction.tenant_id == CaseActionApproval.tenant_id),
        ).where(CaseAction.tenant_id == case.tenant_id, CaseAction.case_id == case.id)
            .order_by(CaseActionApproval.created_at, CaseActionApproval.id)).all()
        return [ActionApprovalRead.model_validate(row) for row in rows]

    def decide(self, approval_id: UUID, command: ActionApprovalDecision) -> ActionApprovalRead:
        self._staff()
        if self.actor.role not in ("SUPERVISOR", "ADMIN"):
            raise ServiceError(403, "需要主管审批权限。", code="APPROVAL_FORBIDDEN")
        # Discover only tenant-scoped identities before acquiring locks. Request
        # replays lock Case -> Action, so decisions must use the same order.
        identity = self.session.execute(select(CaseAction.id, CaseAction.case_id).join(
            CaseActionApproval, (CaseActionApproval.action_id == CaseAction.id)
            & (CaseActionApproval.tenant_id == CaseAction.tenant_id),
        ).where(
            CaseAction.tenant_id == self.actor.tenant_id,
            CaseActionApproval.tenant_id == self.actor.tenant_id,
            CaseActionApproval.id == approval_id,
        )).one_or_none()
        if identity is None:
            raise ServiceError(404, "审批记录不存在或不可见。")
        case = self.resource(ServiceCase, identity.case_id, lock=True)
        self.session.refresh(case)
        action = self.session.scalar(select(CaseAction).where(
            CaseAction.tenant_id == case.tenant_id, CaseAction.case_id == case.id,
            CaseAction.id == identity.id,
        ).with_for_update().execution_options(populate_existing=True))
        if action is None:
            raise ServiceError(404, "售后动作不存在或不可见。")
        approval = self.session.scalar(select(CaseActionApproval).where(
            CaseActionApproval.tenant_id == case.tenant_id,
            CaseActionApproval.action_id == action.id,
            CaseActionApproval.id == approval_id,
        ).with_for_update().execution_options(populate_existing=True))
        if approval is None:
            raise ServiceError(404, "审批记录不存在或不可见。")
        reason = command.reason.strip()
        if len(reason) < 3:
            raise ServiceError(422, "审批原因不能为空。", code="DECISION_REASON_REQUIRED")
        fingerprint = _hash({"decision": command.decision, "reason": reason})
        if approval.decision_id == command.decision_id:
            if approval.decision_hash != fingerprint or approval.decided_by != self.actor.actor_id:
                raise ServiceError(409, "审批编号已用于其他决定。", code="IDEMPOTENCY_CONFLICT")
            return ActionApprovalRead.model_validate(approval)
        if approval.status != "PENDING" or action.status != "WAITING_APPROVAL":
            raise ServiceError(409, "审批已处理，请刷新。", code="APPROVAL_ALREADY_DECIDED")
        if approval.version != command.expected_version:
            raise ServiceError(409, "审批版本已更新，请刷新。", code="STALE_VERSION",
                               current_version=approval.version)
        if action.requested_by == self.actor.actor_id:
            raise ServiceError(403, "不能批准自己提出的售后动作。", code="SELF_APPROVAL_FORBIDDEN")
        if case.status in ("RESOLVED", "CLOSED") and command.decision == "APPROVED":
            raise ServiceError(409, "案例已解决或关闭，不能批准执行。", code="CASE_NOT_ACTIONABLE")
        now = datetime.now(timezone.utc)
        approval.status = command.decision
        approval.version += 1
        approval.decision_id = command.decision_id
        approval.decision_hash = fingerprint
        approval.decided_by = self.actor.actor_id
        approval.decision_reason = reason
        approval.decided_at = now
        action.status = "APPROVED" if command.decision == "APPROVED" else "REJECTED"
        action.version += 1
        enqueue_case_events(self.session, case.tenant_id, case.id, "action.approval_decided",
                            {"action_id": str(action.id), "approval_id": str(approval.id),
                             "decision": command.decision}, "INTERNAL")
        self.session.commit()
        return ActionApprovalRead.model_validate(approval)
