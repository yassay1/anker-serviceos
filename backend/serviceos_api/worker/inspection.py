"""Lease-based local image inspection. This process does not call a model provider."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from serviceos_api.application.evidence import complete_inspection
from serviceos_api.persistence.database import build_engine
from serviceos_api.persistence.models import EvidenceInspectionJob
from serviceos_api.settings import Settings
from serviceos_api.worker.runtime import Lease

logger = logging.getLogger("serviceos.evidence")


class EvidenceInspectionWorker:
    def __init__(self, engine, settings: Settings, worker_id: str | None = None):
        self.engine = engine
        self.settings = settings
        self.worker_id = worker_id or f"evidence-{uuid4()}"

    def claim_one(self) -> Lease | None:
        now = datetime.now(timezone.utc)
        limit = self.settings.worker_max_attempts
        with Session(self.engine, expire_on_commit=False) as session:
            exhausted = session.scalars(select(EvidenceInspectionJob).where(
                EvidenceInspectionJob.status == "RUNNING",
                EvidenceInspectionJob.lease_expires_at <= now,
                EvidenceInspectionJob.attempt_count >= func.least(EvidenceInspectionJob.max_attempts, limit),
            ).with_for_update(skip_locked=True).limit(20)).all()
            for row in exhausted:
                row.status = "FAILED"
                row.last_error_code = "lease_expired_max_attempts"
                row.lease_owner = None
                row.lease_token = None
                row.lease_expires_at = None
            job = session.scalars(select(EvidenceInspectionJob).where(
                EvidenceInspectionJob.attempt_count < func.least(EvidenceInspectionJob.max_attempts, limit),
                or_(
                    and_(EvidenceInspectionJob.status == "QUEUED", EvidenceInspectionJob.available_at <= now),
                    and_(EvidenceInspectionJob.status == "RUNNING", EvidenceInspectionJob.lease_expires_at <= now),
                ),
            ).order_by(EvidenceInspectionJob.available_at, EvidenceInspectionJob.created_at, EvidenceInspectionJob.id)
             .with_for_update(skip_locked=True).limit(1)).first()
            if job is None:
                session.commit()
                return None
            token = uuid4()
            job.status = "RUNNING"
            job.attempt_count += 1
            job.lease_owner = self.worker_id
            job.lease_token = token
            job.lease_expires_at = now + timedelta(seconds=self.settings.worker_lease_seconds)
            job.heartbeat_at = now
            job.last_error_code = None
            lease = Lease(job.tenant_id, job.id, token)
            session.commit()
            return lease

    def process(self, lease: Lease) -> None:
        try:
            with Session(self.engine) as session:
                job = session.scalar(select(EvidenceInspectionJob).where(
                    EvidenceInspectionJob.id == lease.item_id,
                    EvidenceInspectionJob.tenant_id == lease.tenant_id,
                    EvidenceInspectionJob.lease_token == lease.token,
                    EvidenceInspectionJob.status == "RUNNING",
                ).with_for_update())
                if job is None:
                    return
                complete_inspection(session, lease.tenant_id, job.evidence_id)
                job.status = "COMPLETED"
                job.completed_at = datetime.now(timezone.utc)
                job.lease_owner = None
                job.lease_token = None
                job.lease_expires_at = None
                job.last_error_code = None
                session.commit()
        except Exception:
            self._requeue(lease, "evidence_inspection_failed")

    def _requeue(self, lease: Lease, error_code: str) -> None:
        now = datetime.now(timezone.utc)
        with Session(self.engine) as session:
            job = session.scalar(select(EvidenceInspectionJob).where(
                EvidenceInspectionJob.id == lease.item_id,
                EvidenceInspectionJob.tenant_id == lease.tenant_id,
                EvidenceInspectionJob.lease_token == lease.token,
            ).with_for_update())
            if job is None:
                return
            terminal = job.attempt_count >= min(job.max_attempts, self.settings.worker_max_attempts)
            job.status = "FAILED" if terminal else "QUEUED"
            job.last_error_code = error_code
            job.available_at = now + timedelta(seconds=min(300, 2 ** job.attempt_count))
            job.lease_owner = None
            job.lease_token = None
            job.lease_expires_at = None
            session.commit()
        logger.warning("evidence inspection ended: error_code=%s", error_code)

    def run_once(self) -> bool:
        lease = self.claim_one()
        if lease is None:
            return False
        self.process(lease)
        return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings.from_environment()
    engine = build_engine()
    worker = EvidenceInspectionWorker(engine, settings)
    try:
        while True:
            if not worker.run_once():
                time.sleep(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
