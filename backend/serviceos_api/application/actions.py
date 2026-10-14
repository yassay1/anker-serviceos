"""Application boundary for one explicitly simulated service operation."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from serviceos_api.application.contracts import (
    ActionApprovalDecision, ActionApprovalRead, CaseActionRead, MockActionRequest, MockReceiptRead,
)
from serviceos_api.application.errors import ServiceError
from serviceos_api.application.evidence import enqueue_case_events
from serviceos_api.application.services import BusinessService
from serviceos_api.application.verification import CONFIRMED_CONDITIONS
from serviceos_api.persistence.models import AgentProposal, CaseAction, CaseActionApproval, CaseConversation, ResolutionContract, ServiceCase


def _hash(fields: dict) -> str:
    return hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


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
            adapter=action.adapter, status=action.status, version=action.version,
            approval_id=approval_id, receipt=receipt, created_at=action.created_at,
            reason=action.reason if self.actor.kind == "STAFF" else None,
            requested_by=action.requested_by if self.actor.kind == "STAFF" else None,
        )

    def request(self, case_id: UUID, command: MockActionRequest) -> CaseActionRead:
        self._staff()
        case = self.resource(ServiceCase, case_id, lock=True)
        reason = command.reason.strip()
        if len(reason) < 3:
            raise ServiceError(422, "售后动作原因不能为空。", code="ACTION_REASON_REQUIRED")
        fingerprint = _hash({"kind": command.action_kind, "proposal": str(command.source_proposal_id),
                             "reason": reason})
        previous = self.session.scalar(select(CaseAction).where(
            CaseAction.tenant_id == case.tenant_id, CaseAction.case_id == case.id,
            CaseAction.client_action_id == command.client_action_id,
        ).with_for_update())
        if previous is not None:
            if previous.request_hash != fingerprint or previous.requested_by != self.actor.actor_id:
                raise ServiceError(409, "动作编号已用于其他请求。", code="IDEMPOTENCY_CONFLICT")
            return self._read(previous)
        if case.version != command.expected_case_version:
            raise ServiceError(409, "案例版本已更新，请刷新后重试。", code="STALE_VERSION",
                               current_version=case.version)
        if case.status in ("RESOLVED", "CLOSED"):
            raise ServiceError(409, "已解决或关闭的案例不能发起新动作。", code="CASE_NOT_ACTIONABLE")
        if command.source_proposal_id is not None:
            proposal = self.session.scalar(select(AgentProposal).join(
                CaseConversation, (CaseConversation.conversation_id == AgentProposal.conversation_id)
                & (CaseConversation.tenant_id == AgentProposal.tenant_id),
            ).where(AgentProposal.tenant_id == case.tenant_id,
                    AgentProposal.id == command.source_proposal_id,
                    AgentProposal.proposal_type == "ACTION", CaseConversation.case_id == case.id))
            if proposal is None:
                raise ServiceError(404, "关联的内部动作草稿不存在或不属于此案例。")
        action = CaseAction(
            tenant_id=case.tenant_id, case_id=case.id, client_action_id=command.client_action_id,
            request_hash=fingerprint, action_kind=command.action_kind, adapter="MOCK",
            status="WAITING_APPROVAL", requested_by=self.actor.actor_id,
            source_proposal_id=command.source_proposal_id, reason=reason,
        )
        self.session.add(action)
        self.session.flush()
        self.session.add(ResolutionContract(
            tenant_id=case.tenant_id, case_id=case.id, action_id=action.id,
            version=1, conditions=CONFIRMED_CONDITIONS,
        ))
        approval = CaseActionApproval(tenant_id=case.tenant_id, action_id=action.id)
        self.session.add(approval)
        case.version += 1
        enqueue_case_events(self.session, case.tenant_id, case.id, "action.requested",
                            {"action_id": str(action.id), "case_id": str(case.id)}, "INTERNAL")
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
        approval = self.session.scalar(select(CaseActionApproval).where(
            CaseActionApproval.tenant_id == self.actor.tenant_id,
            CaseActionApproval.id == approval_id,
        ).with_for_update())
        if approval is None:
            raise ServiceError(404, "审批记录不存在或不可见。")
        action = self.session.scalar(select(CaseAction).where(
            CaseAction.tenant_id == self.actor.tenant_id,
            CaseAction.id == approval.action_id,
        ).with_for_update())
        if action is None:
            raise ServiceError(404, "售后动作不存在或不可见。")
        case = self.resource(ServiceCase, action.case_id, lock=True)
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
