"""Turn due, consented follow-ups into internal staff tasks exactly once."""

import argparse
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceos_api.application.followups import complete_due_follow_up
from serviceos_api.persistence.database import build_engine
from serviceos_api.persistence.models import FollowUpJob
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
            complete_due_follow_up(session, job, now)
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
