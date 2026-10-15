"""Human-reviewed, source-linked after-sales experience candidates."""

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceos_api.application.auth import Principal
from serviceos_api.application.contracts import (
    ExperienceCandidatePage, ExperienceCandidateRead, ExperienceCandidateUpdate,
    ExperienceDecision, ExperienceReviewPage, ExperienceReviewRead,
)
from serviceos_api.application.errors import ServiceError
from serviceos_api.persistence.models import (
    ExperienceCandidate, ExperienceReview, ServiceCase, CaseVerification,
)


def _request_hash(request: ExperienceDecision) -> str:
    payload = request.model_dump(mode="json", exclude={"decision_id"})
    payload["reason"] = payload["reason"].strip()
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class ExperienceService:
    def __init__(self, session: Session, actor: Principal):
        self.session = session
        self.actor = actor

    def _staff(self):
        if self.actor.kind != "STAFF":
            raise ServiceError(403, "只有客服可以查看或整理经验候选。")

    def _candidate(self, candidate_id: UUID, *, lock: bool = False) -> ExperienceCandidate:
        query = select(ExperienceCandidate).where(
            ExperienceCandidate.tenant_id == self.actor.tenant_id,
            ExperienceCandidate.id == candidate_id,
        )
        if lock:
            query = query.with_for_update()
        candidate = self.session.scalar(query)
        if candidate is None:
            raise ServiceError(404, "经验候选不存在或当前账号无权访问。")
        return candidate

    def list(self, status: str | None = None, limit: int = 50) -> ExperienceCandidatePage:
        self._staff()
        if not 1 <= limit <= 100:
            raise ServiceError(422, "分页数量须在 1 至 100 之间。")
        query = select(ExperienceCandidate).where(ExperienceCandidate.tenant_id == self.actor.tenant_id)
        if status is not None:
            query = query.where(ExperienceCandidate.status == status)
        rows = self.session.scalars(query.order_by(
            ExperienceCandidate.updated_at.desc(), ExperienceCandidate.id).limit(limit)).all()
        return ExperienceCandidatePage(items=[ExperienceCandidateRead.model_validate(row) for row in rows])

    def read(self, candidate_id: UUID) -> ExperienceCandidateRead:
        self._staff()
        return ExperienceCandidateRead.model_validate(self._candidate(candidate_id))

    def reviews(self, candidate_id: UUID) -> ExperienceReviewPage:
        self._staff()
        candidate = self._candidate(candidate_id)
        rows = self.session.scalars(select(ExperienceReview).where(
            ExperienceReview.tenant_id == self.actor.tenant_id,
            ExperienceReview.candidate_id == candidate.id,
        ).order_by(ExperienceReview.created_at, ExperienceReview.id)).all()
        return ExperienceReviewPage(items=[ExperienceReviewRead.model_validate(row) for row in rows])

    def update(self, candidate_id: UUID, request: ExperienceCandidateUpdate) -> ExperienceCandidateRead:
        self._staff()
        candidate = self._candidate(candidate_id, lock=True)
        if candidate.version != request.expected_version:
            raise ServiceError(409, "经验候选已更新，请刷新后重试。", code="STALE_VERSION",
                               current_version=candidate.version)
        if candidate.status not in ("DRAFT", "REJECTED"):
            raise ServiceError(409, "当前状态的经验候选不能修改。", code="CANDIDATE_NOT_EDITABLE")
        if request.submit_for_review:
            self._require_resolved_source(candidate)
            candidate.status = "PENDING_REVIEW"
            candidate.submitted_at = datetime.now(timezone.utc)
        else:
            candidate.status = "DRAFT"
            candidate.submitted_at = None
        candidate.content = request.content.model_dump(mode="json")
        candidate.authored_by = self.actor.actor_id
        candidate.version += 1
        self.session.commit()
        return ExperienceCandidateRead.model_validate(candidate)

    def decide(self, candidate_id: UUID, request: ExperienceDecision) -> ExperienceCandidateRead:
        self._staff()
        if self.actor.role not in ("SUPERVISOR", "ADMIN"):
            raise ServiceError(403, "只有主管或管理员可以审核经验候选。")
        candidate = self._candidate(candidate_id, lock=True)
        digest = _request_hash(request)
        previous = self.session.scalar(select(ExperienceReview).where(
            ExperienceReview.tenant_id == self.actor.tenant_id,
            ExperienceReview.candidate_id == candidate.id,
            ExperienceReview.decision_id == request.decision_id,
        ))
        if previous is not None:
            if previous.request_hash != digest or previous.reviewer_id != self.actor.actor_id:
                raise ServiceError(409, "审核编号已用于其他决定。", code="IDEMPOTENCY_CONFLICT")
            return ExperienceCandidateRead.model_validate(candidate)
        if candidate.version != request.expected_version:
            raise ServiceError(409, "经验候选已更新，请刷新后重试。", code="STALE_VERSION",
                               current_version=candidate.version)
        if candidate.authored_by == self.actor.actor_id:
            raise ServiceError(403, "整理人不能审核自己提交的经验候选。", code="REVIEWER_MUST_DIFFER")
        if request.decision in ("APPROVED", "REJECTED"):
            if candidate.status != "PENDING_REVIEW":
                raise ServiceError(409, "只有待审核候选可以批准或拒绝。", code="CANDIDATE_NOT_REVIEWABLE")
            self._require_resolved_source(candidate)
            if request.decision == "APPROVED" and candidate.content is None:
                raise ServiceError(409, "经验内容尚未填写。", code="CANDIDATE_CONTENT_REQUIRED")
        elif candidate.status != "APPROVED":
            raise ServiceError(409, "只有已批准经验可以撤销。", code="CANDIDATE_NOT_REVOCABLE")

        old_version = candidate.version
        candidate.status = request.decision
        candidate.version += 1
        self.session.add(ExperienceReview(
            tenant_id=self.actor.tenant_id,
            candidate_id=candidate.id,
            reviewer_id=self.actor.actor_id,
            decision_id=request.decision_id,
            candidate_version=old_version,
            decision=request.decision,
            request_hash=digest,
            reason=request.reason.strip(),
        ))
        self.session.commit()
        return ExperienceCandidateRead.model_validate(candidate)

    def _require_resolved_source(self, candidate: ExperienceCandidate) -> None:
        case = self.session.scalar(select(ServiceCase).where(
            ServiceCase.tenant_id == self.actor.tenant_id,
            ServiceCase.id == candidate.source_case_id,
        ))
        verification = self.session.scalar(select(CaseVerification).where(
            CaseVerification.tenant_id == self.actor.tenant_id,
            CaseVerification.id == candidate.source_verification_id,
            CaseVerification.case_id == candidate.source_case_id,
            CaseVerification.decision == "VERIFIED_RESOLVED",
        ))
        latest_verification_id = self.session.scalar(select(CaseVerification.id).where(
            CaseVerification.tenant_id == self.actor.tenant_id,
            CaseVerification.case_id == candidate.source_case_id,
        ).order_by(CaseVerification.created_at.desc(), CaseVerification.id.desc()).limit(1))
        if (case is None or case.status not in ("RESOLVED", "CLOSED") or verification is None
                or latest_verification_id != candidate.source_verification_id):
            raise ServiceError(409, "来源案例已重开或核验依据无效，不能提交或批准该经验。",
                               code="SOURCE_NOT_RESOLVED")
