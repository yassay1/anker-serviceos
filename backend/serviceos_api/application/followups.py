"""Customer-authorized follow-up scheduling; reminders are staff tasks only."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select

from serviceos_api.application.contracts import (
    FollowUpConsentRead, FollowUpConsentRequest, FollowUpRead, FollowUpRequest,
)
from serviceos_api.application.errors import ServiceError
from serviceos_api.application.evidence import enqueue_case_events
from serviceos_api.application.business import BusinessService
from serviceos_api.persistence.models import CaseConversation, FollowUpConsent, FollowUpJob, ServiceCase, ServiceTask, TaskAssignment


def fingerprint(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def complete_due_follow_up(session, job: FollowUpJob, now: datetime) -> None:
    """Apply a claimed reminder as one internal task in the caller's transaction."""
    task = ServiceTask(tenant_id=job.tenant_id, conversation_id=job.conversation_id,
                       case_id=job.case_id, reason=f"已到预约时间的客户回访：{job.purpose}",
                       status="ASSIGNED")
    session.add(task)
    session.flush()
    session.add(TaskAssignment(tenant_id=job.tenant_id, task_id=task.id,
                               staff_user_id=job.scheduled_by))
    job.status = "DUE"
    job.task_id = task.id
    job.reminded_at = now
    enqueue_case_events(session, job.tenant_id, job.case_id, "follow_up.due", {
        "case_id": str(job.case_id), "follow_up_id": str(job.id), "task_id": str(task.id),
    }, "INTERNAL")


class FollowUpService(BusinessService):
    def list_consents(self, case_id: UUID) -> list[FollowUpConsentRead]:
        case = self.resource(ServiceCase, case_id)
        rows = self.session.scalars(select(FollowUpConsent).where(
            FollowUpConsent.tenant_id == case.tenant_id, FollowUpConsent.case_id == case.id,
        ).order_by(FollowUpConsent.created_at, FollowUpConsent.id)).all()
        return [FollowUpConsentRead.model_validate(row) for row in rows]

    def consent(self, case_id: UUID, command: FollowUpConsentRequest) -> FollowUpConsentRead:
        if self.actor.kind != "CUSTOMER":
            raise ServiceError(403, "只有案例客户本人可以同意回访。", code="CUSTOMER_CONSENT_REQUIRED")
        case = self.resource(ServiceCase, case_id, lock=True)
        purpose = command.purpose.strip()
        if len(purpose) < 3:
            raise ServiceError(422, "回访目的至少需要三个字。")
        key = fingerprint({"purpose": purpose})
        previous = self.session.scalar(select(FollowUpConsent).where(
            FollowUpConsent.tenant_id == case.tenant_id, FollowUpConsent.case_id == case.id,
            FollowUpConsent.client_consent_id == command.client_consent_id,
        ).with_for_update())
        if previous is not None:
            if previous.request_hash != key or previous.customer_id != self.actor.actor_id:
                raise ServiceError(409, "同意编号已用于其他目的。", code="IDEMPOTENCY_CONFLICT")
            return FollowUpConsentRead.model_validate(previous)
        if case.version != command.expected_case_version:
            raise ServiceError(409, "案例版本已更新，请刷新后重试。", code="STALE_VERSION", current_version=case.version)
        if case.status == "CLOSED":
            raise ServiceError(409, "已关闭案例不能预约回访。")
        row = FollowUpConsent(tenant_id=case.tenant_id, case_id=case.id, customer_id=case.customer_id,
                              client_consent_id=command.client_consent_id, request_hash=key, purpose=purpose)
        self.session.add(row)
        self.session.flush()
        case.version += 1
        enqueue_case_events(self.session, case.tenant_id, case.id, "follow_up.consented",
                            {"case_id": str(case.id), "consent_id": str(row.id)}, "PUBLIC")
        self.session.commit()
        return FollowUpConsentRead.model_validate(row)

    def list_jobs(self, case_id: UUID) -> list[FollowUpRead]:
        case = self.resource(ServiceCase, case_id)
        rows = self.session.scalars(select(FollowUpJob).where(
            FollowUpJob.tenant_id == case.tenant_id, FollowUpJob.case_id == case.id,
        ).order_by(FollowUpJob.created_at, FollowUpJob.id)).all()
        result = [FollowUpRead.model_validate(row) for row in rows]
        if self.actor.kind == "CUSTOMER":
            return [item.model_copy(update={"task_id": None}) for item in result]
        return result

    def schedule(self, case_id: UUID, command: FollowUpRequest) -> FollowUpRead:
        if self.actor.kind != "STAFF":
            raise ServiceError(403, "只有客服可以预约回访。", code="STAFF_REQUIRED")
        case = self.resource(ServiceCase, case_id, lock=True)
        purpose = command.purpose.strip()
        if len(purpose) < 3:
            raise ServiceError(422, "回访目的至少需要三个字。")
        due_at = command.due_at
        if due_at.tzinfo is None or due_at.utcoffset() is None:
            raise ServiceError(422, "请提供带时区的回访时间。")
        due_at = due_at.astimezone(timezone.utc)
        key = fingerprint({"consent_id": str(command.consent_record_id), "purpose": purpose,
                           "due_at": due_at.isoformat()})
        previous = self.session.scalar(select(FollowUpJob).where(
            FollowUpJob.tenant_id == case.tenant_id, FollowUpJob.case_id == case.id,
            FollowUpJob.client_follow_up_id == command.client_follow_up_id,
        ).with_for_update())
        if previous is not None:
            if previous.request_hash != key:
                raise ServiceError(409, "回访编号已用于其他安排。", code="IDEMPOTENCY_CONFLICT")
            return FollowUpRead.model_validate(previous)
        if case.version != command.expected_case_version:
            raise ServiceError(409, "案例版本已更新，请刷新后重试。", code="STALE_VERSION", current_version=case.version)
        if case.status == "CLOSED":
            raise ServiceError(409, "已关闭案例不能预约回访。")
        now = datetime.now(timezone.utc)
        if due_at <= now or due_at > now + timedelta(days=90):
            raise ServiceError(422, "回访时间须在未来 90 天内。")
        consent = self.session.scalar(select(FollowUpConsent).where(
            FollowUpConsent.tenant_id == case.tenant_id, FollowUpConsent.case_id == case.id,
            FollowUpConsent.customer_id == case.customer_id,
            FollowUpConsent.id == command.consent_record_id,
        ))
        if consent is None:
            raise ServiceError(404, "此案例没有对应的客户回访同意。", code="CONSENT_NOT_FOUND")
        if purpose != consent.purpose:
            raise ServiceError(403, "预约目的必须与客户同意的目的相同。", code="CONSENT_PURPOSE_MISMATCH")
        already_scheduled = self.session.scalar(select(FollowUpJob.id).where(
            FollowUpJob.tenant_id == case.tenant_id,
            FollowUpJob.consent_record_id == consent.id,
        ).limit(1))
        if already_scheduled is not None:
            raise ServiceError(409, "本次客户同意已用于一次回访预约。", code="CONSENT_ALREADY_USED")
        conversation_id = self.session.scalar(select(CaseConversation.conversation_id).where(
            CaseConversation.tenant_id == case.tenant_id, CaseConversation.case_id == case.id,
        ).order_by(CaseConversation.conversation_id).limit(1))
        if conversation_id is None:
            raise ServiceError(409, "案例需关联会话，才能创建可见的客服回访待办。")
        row = FollowUpJob(tenant_id=case.tenant_id, case_id=case.id,
                          consent_record_id=consent.id, conversation_id=conversation_id,
                          client_follow_up_id=command.client_follow_up_id, request_hash=key,
                          scheduled_by=self.actor.actor_id, purpose=purpose, due_at=due_at)
        self.session.add(row)
        self.session.flush()
        case.version += 1
        enqueue_case_events(self.session, case.tenant_id, case.id, "follow_up.scheduled",
                            {"case_id": str(case.id), "follow_up_id": str(row.id)}, "INTERNAL")
        self.session.commit()
        return FollowUpRead.model_validate(row)
