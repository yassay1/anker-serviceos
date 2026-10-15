"""Freeze action outcome conditions and judge customer observations in one transaction."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from serviceos_api.application.contracts import ResolutionContractRead, VerificationRead, VerificationRequest
from serviceos_api.application.errors import ServiceError
from serviceos_api.application.evidence import enqueue_case_events
from serviceos_api.application.services import BusinessService
from serviceos_api.persistence.models import (
    CaseAction, CaseImageEvidence, CaseVerification, ExperienceCandidate, ResolutionContract, ServiceCase,
)


CONFIRMED_CONDITIONS = ["模拟服务请求收到成功回执", "客户明确确认问题已解决"]

# 仍在流程中的动作稍后仍可能执行并改变设备，因此不能作为已核验的解决依据。
# 条件列表保持稳定（冻结记录不可回溯变更），该前置判断属于“成功回执”的适用范围。
UNSETTLED_ACTION_STATUSES = ("WAITING_APPROVAL", "APPROVED", "EXECUTING", "UNKNOWN")


def _fingerprint(command: VerificationRequest) -> str:
    fields = {
        "contract_version": command.expected_resolution_contract_version,
        "observed_result": command.observed_result,
        "evidence_ids": sorted(str(item) for item in command.evidence_ids),
        "note": command.note.strip(),
    }
    return hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class VerificationService(BusinessService):
    def _latest_action(self, case: ServiceCase) -> CaseAction:
        action = self.session.scalar(select(CaseAction).where(
            CaseAction.tenant_id == case.tenant_id, CaseAction.case_id == case.id,
        ).order_by(CaseAction.created_at.desc(), CaseAction.id.desc()).limit(1))
        if action is None:
            raise ServiceError(404, "此案例尚无可核验的模拟售后动作。", code="CONTRACT_NOT_FOUND")
        return action

    def _has_unsettled_action(self, case: ServiceCase, latest: CaseAction) -> bool:
        """A later success cannot settle the case while an earlier action may still run.

        UNKNOWN/EXECUTING/APPROVED/WAITING_APPROVAL actions can still change the device
        afterwards, so their case is not verifiable yet even with a successful latest receipt.
        """
        return self.session.scalar(select(CaseAction.id).where(
            CaseAction.tenant_id == case.tenant_id, CaseAction.case_id == case.id,
            CaseAction.id != latest.id, CaseAction.status.in_(UNSETTLED_ACTION_STATUSES),
        ).limit(1)) is not None

    def _contract(self, case: ServiceCase, action: CaseAction) -> ResolutionContract:
        contract = self.session.scalar(select(ResolutionContract).where(
            ResolutionContract.tenant_id == case.tenant_id, ResolutionContract.case_id == case.id,
            ResolutionContract.action_id == action.id,
        ))
        if contract is None:
            raise ServiceError(503, "解决条件记录缺失。", code="CONTRACT_MISSING")
        return contract

    def read_contract(self, case_id: UUID) -> ResolutionContractRead:
        case = self.resource(ServiceCase, case_id)
        return ResolutionContractRead.model_validate(self._contract(case, self._latest_action(case)))

    def list_verifications(self, case_id: UUID) -> list[VerificationRead]:
        case = self.resource(ServiceCase, case_id)
        rows = self.session.scalars(select(CaseVerification).where(
            CaseVerification.tenant_id == case.tenant_id, CaseVerification.case_id == case.id,
        ).order_by(CaseVerification.created_at, CaseVerification.id)).all()
        return [VerificationRead.model_validate(row) for row in rows]

    def record(self, case_id: UUID, command: VerificationRequest) -> VerificationRead:
        if self.actor.kind != "CUSTOMER":
            raise ServiceError(403, "只有案例客户本人可以确认问题是否解决。", code="CUSTOMER_CONFIRMATION_REQUIRED")
        case = self.resource(ServiceCase, case_id, lock=True)
        fingerprint = _fingerprint(command)
        previous = self.session.scalar(select(CaseVerification).where(
            CaseVerification.tenant_id == case.tenant_id, CaseVerification.case_id == case.id,
            CaseVerification.client_verification_id == command.client_verification_id,
        ).with_for_update())
        if previous is not None:
            if previous.request_hash != fingerprint or previous.customer_id != self.actor.actor_id:
                raise ServiceError(409, "核验编号已用于其他观察结果。", code="IDEMPOTENCY_CONFLICT")
            return VerificationRead.model_validate(previous)
        if case.version != command.expected_case_version:
            raise ServiceError(409, "案例版本已更新，请刷新后重试。", code="STALE_VERSION",
                               current_version=case.version)
        if case.status in ("RESOLVED", "CLOSED"):
            raise ServiceError(409, "案例已解决或关闭；新问题需重新开启服务。", code="CASE_NOT_VERIFIABLE")
        action = self._latest_action(case)
        contract = self._contract(case, action)
        if contract.version != command.expected_resolution_contract_version:
            raise ServiceError(409, "解决条件版本已更新，请刷新后重试。", code="STALE_CONTRACT",
                               current_version=contract.version)
        evidence_ids = set(command.evidence_ids)
        if len(evidence_ids) != len(command.evidence_ids):
            raise ServiceError(422, "证据编号不能重复。", code="DUPLICATE_EVIDENCE")
        if evidence_ids:
            visible = set(self.session.scalars(select(CaseImageEvidence.id).where(
                CaseImageEvidence.tenant_id == case.tenant_id,
                CaseImageEvidence.case_id == case.id,
                CaseImageEvidence.id.in_(evidence_ids),
                CaseImageEvidence.visibility == "PUBLIC",
                CaseImageEvidence.inspection_status == "CLEAN",
            )).all())
            if visible != evidence_ids:
                raise ServiceError(404, "证据不存在、不可见或尚未通过检查。", code="EVIDENCE_NOT_AVAILABLE")
        receipt_succeeded = action.status == "SUCCEEDED" and action.receipt_result == "SUCCEEDED"
        if command.observed_result == "WORKING" and receipt_succeeded and not self._has_unsettled_action(case, action):
            decision = "VERIFIED_RESOLVED"
            case.status = "RESOLVED"
            case.resolved_at = datetime.now(timezone.utc)
        elif command.observed_result == "NOT_WORKING":
            decision = "NOT_RESOLVED"
            case.status = "IN_PROGRESS"
        else:
            decision = "PENDING"
        case.version += 1
        row = CaseVerification(
            tenant_id=case.tenant_id, case_id=case.id, contract_id=contract.id,
            customer_id=self.actor.actor_id, client_verification_id=command.client_verification_id,
            request_hash=fingerprint, observed_result=command.observed_result, decision=decision,
            note=command.note.strip(), evidence_ids=sorted(str(item) for item in evidence_ids),
            case_status=case.status,
        )
        self.session.add(row)
        self.session.flush()
        if decision == "VERIFIED_RESOLVED":
            # Keep the experience seed source-linked and empty. Never copy raw customer
            # text or ask an LLM to generalize a single case on the customer hot path.
            self.session.add(ExperienceCandidate(
                tenant_id=case.tenant_id, source_case_id=case.id, source_verification_id=row.id,
                content=None, status="DRAFT", version=1,
            ))
        enqueue_case_events(self.session, case.tenant_id, case.id, "verification.recorded", {
            "case_id": str(case.id), "verification_id": str(row.id), "decision": decision,
            "case_status": case.status, "case_version": case.version,
        }, "PUBLIC")
        self.session.commit()
        return VerificationRead.model_validate(row)
