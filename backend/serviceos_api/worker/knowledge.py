"""Lease-based knowledge pipeline worker: convert, chunk, embed uploaded documents."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from serviceos_api.application.knowledge_pipeline import process_knowledge_job
from serviceos_api.integrations.local_evidence_storage import evidence_storage_from_settings
from serviceos_api.persistence.database import build_engine
from serviceos_api.persistence.knowledge_models import KnowledgeJob
from serviceos_api.settings import Settings
from serviceos_api.worker.health import run_loop
from serviceos_api.worker.runtime import Lease

# Single source of truth for the container healthcheck role.
ROLE = "knowledge"

# Knowledge documents are global; leases still need a tenant slot.
GLOBAL_TENANT = UUID(int=0)

logger = logging.getLogger("serviceos.knowledge")


class KnowledgeWorker:
    def __init__(self, engine, settings: Settings, worker_id: str | None = None):
        self.engine = engine
        self.settings = settings
        self.worker_id = worker_id or f"knowledge-{uuid4()}"
        self.storage = evidence_storage_from_settings(settings)

    def claim_one(self) -> Lease | None:
        now = datetime.now(timezone.utc)
        limit = self.settings.worker_max_attempts
        with Session(self.engine, expire_on_commit=False) as session:
            exhausted = session.scalars(select(KnowledgeJob).where(
                KnowledgeJob.status == "RUNNING",
                KnowledgeJob.lease_expires_at <= now,
                KnowledgeJob.attempt_count >= func.least(KnowledgeJob.max_attempts, limit),
            ).with_for_update(skip_locked=True).limit(20)).all()
            for row in exhausted:
                row.status = "FAILED"
                row.last_error_code = "lease_expired_max_attempts"
                row.lease_owner = None
                row.lease_token = None
                row.lease_expires_at = None
            claimed = session.execute(select(KnowledgeJob).where(
                or_(KnowledgeJob.attempt_count < func.least(KnowledgeJob.max_attempts, limit)),
                or_(
                    and_(KnowledgeJob.status == "QUEUED", KnowledgeJob.available_at <= now),
                    and_(KnowledgeJob.status == "RUNNING", KnowledgeJob.lease_expires_at <= now),
                ),
            ).order_by(KnowledgeJob.available_at, KnowledgeJob.created_at, KnowledgeJob.id)
             .with_for_update(skip_locked=True).limit(1)).scalar_one_or_none()
            if claimed is None:
                session.commit()
                return None
            job = claimed
            token = uuid4()
            job.status = "RUNNING"
            job.attempt_count += 1
            job.lease_owner = self.worker_id
            job.lease_token = token
            job.lease_expires_at = now + timedelta(seconds=self.settings.worker_lease_seconds)
            job.heartbeat_at = now
            job.last_error_code = None
            lease = Lease(job.tenant_id or GLOBAL_TENANT, job.id, token)
            session.commit()
            return lease

    def process(self, lease: Lease) -> None:
        try:
            with Session(self.engine) as session:
                job = session.scalar(select(KnowledgeJob).where(
                    KnowledgeJob.id == lease.item_id,
                    KnowledgeJob.lease_token == lease.token,
                    KnowledgeJob.status == "RUNNING",
                ).with_for_update())
                if job is None:
                    return
                error_code = process_knowledge_job(session, job, self.settings, self.storage)
                self._settle(session, job, error_code)
                session.commit()
            if error_code is None:
                logger.info("knowledge job completed: job_id=%s", lease.item_id)
            else:
                logger.warning("knowledge job ended: job_id=%s error_code=%s", lease.item_id, error_code)
        except Exception as error:  # pragma: no cover - defensive worker boundary
            logger.warning("knowledge job crashed: job_id=%s error=%s", lease.item_id, error)
            with Session(self.engine) as session:
                job = session.scalar(select(KnowledgeJob).where(
                    KnowledgeJob.id == lease.item_id,
                    KnowledgeJob.lease_token == lease.token,
                ).with_for_update())
                if job is not None:
                    self._settle(session, job, "knowledge_process_failed")
                    session.commit()

    def _settle(self, session: Session, job: KnowledgeJob, error_code: str | None) -> None:
        now = datetime.now(timezone.utc)
        if error_code is None:
            job.status = "COMPLETED"
            job.lease_owner = None
            job.lease_token = None
            job.lease_expires_at = None
            job.last_error_code = None
            return
        terminal = job.attempt_count >= min(job.max_attempts, self.settings.worker_max_attempts)
        job.status = "FAILED" if terminal else "QUEUED"
        job.last_error_code = error_code
        job.available_at = now + timedelta(seconds=min(300, 2 ** job.attempt_count))
        job.lease_owner = None
        job.lease_token = None
        job.lease_expires_at = None

    def run_once(self) -> bool:
        lease = self.claim_one()
        if lease is None:
            return False
        self.process(lease)
        return True


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Process queued knowledge pipeline jobs")
    parser.add_argument("--once", action="store_true", help="Process one available job and exit")
    arguments = parser.parse_args()
    settings = Settings.from_environment()
    engine = build_engine()
    worker = KnowledgeWorker(engine, settings)
    try:
        if arguments.once:
            logging.basicConfig(level=logging.INFO)
            worker.run_once()
            return
        # run_loop writes the heartbeat that the container healthcheck reads.
        run_loop(ROLE, worker.run_once)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
