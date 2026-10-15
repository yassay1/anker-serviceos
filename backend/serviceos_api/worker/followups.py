"""Turn due, consented follow-ups into internal staff tasks exactly once."""

import argparse
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceos_api.application.evidence import enqueue_case_events
from serviceos_api.persistence.database import build_engine
from serviceos_api.persistence.models import FollowUpJob, ServiceTask, TaskAssignment
from serviceos_api.worker.health import run_loop

# Single source of truth for the container healthcheck role.
ROLE = "followups"

logger = logging.getLogger("serviceos.followups")


class FollowUpWorker:
    def __init__(self, engine):
        self.engine = engine

    def run_once(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        with Session(self.engine) as session, session.begin():
            job = session.scalar(select(FollowUpJob).where(
                FollowUpJob.status == "SCHEDULED", FollowUpJob.due_at <= now,
            ).order_by(FollowUpJob.due_at, FollowUpJob.id).with_for_update(skip_locked=True).limit(1))
            if job is None:
                return False
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
            return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    engine = build_engine()
    try:
        worker = FollowUpWorker(engine)
        if args.once:
            worker.run_once()
            return
        run_loop(ROLE, worker.run_once)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
