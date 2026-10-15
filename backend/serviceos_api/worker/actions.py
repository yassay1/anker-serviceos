"""Independent worker for approved mock actions and uncertain-result reconciliation."""

from __future__ import annotations

import logging
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from serviceos_api.application.actions import claim_mock_action, finish_mock_action
from serviceos_api.integrations.mock_service_adapter import MockReceipt, MockServiceAdapter
from serviceos_api.persistence.database import build_engine
from serviceos_api.persistence.models import CaseAction, ServiceCase
from serviceos_api.settings import Settings
from serviceos_api.worker.health import run_loop

# Single source of truth for the container healthcheck role.
ROLE = "actions"

logger = logging.getLogger("serviceos.actions")


@dataclass(frozen=True)
class ActionLease:
    tenant_id: UUID
    action_id: UUID
    token: UUID
    reconcile_only: bool


class MockActionWorker:
    def __init__(self, engine, settings: Settings, adapter: MockServiceAdapter | None = None):
        self.engine = engine
        self.settings = settings
        self.adapter = adapter or MockServiceAdapter(engine, settings)

    def claim_one(self) -> ActionLease | None:
        now = datetime.now(timezone.utc)
        with Session(self.engine, expire_on_commit=False) as session:
            action = session.scalars(select(CaseAction).where(or_(
                and_(CaseAction.status == "APPROVED", CaseAction.available_at <= now),
                and_(CaseAction.status == "UNKNOWN", CaseAction.available_at <= now,
                     or_(CaseAction.lease_expires_at.is_(None), CaseAction.lease_expires_at <= now)),
                and_(CaseAction.status == "EXECUTING", CaseAction.lease_expires_at <= now),
            )).order_by(CaseAction.available_at, CaseAction.created_at, CaseAction.id)
                .with_for_update(skip_locked=True).limit(1)).first()
            if action is None:
                return None
            token = uuid4()
            reconcile_only = claim_mock_action(action, token, now, self.settings.worker_lease_seconds)
            lease = ActionLease(action.tenant_id, action.id, token, reconcile_only)
            session.commit()
            return lease

    def _finish(self, lease: ActionLease, receipt: MockReceipt | None, error_code: str | None = None) -> None:
        now = datetime.now(timezone.utc)
        with Session(self.engine) as session:
            action = session.scalar(select(CaseAction).where(
                CaseAction.id == lease.action_id, CaseAction.tenant_id == lease.tenant_id,
                CaseAction.lease_token == lease.token,
                CaseAction.status.in_(("EXECUTING", "UNKNOWN")),
            ).with_for_update())
            if action is None:
                return
            finish_mock_action(session, action, receipt, error_code, now)
            session.commit()

    def _case_actionable(self, lease: ActionLease) -> bool:
        with Session(self.engine) as session:
            action = session.scalar(select(CaseAction).where(
                CaseAction.id == lease.action_id, CaseAction.tenant_id == lease.tenant_id,
                CaseAction.lease_token == lease.token,
            ))
            if action is None:
                return False
            case = session.scalar(select(ServiceCase).where(
                ServiceCase.tenant_id == lease.tenant_id, ServiceCase.id == action.case_id,
            ))
            return bool(case and case.status not in ("RESOLVED", "CLOSED"))

    def process(self, lease: ActionLease) -> None:
        try:
            if lease.reconcile_only:
                receipt = self.adapter.lookup(lease.tenant_id, lease.action_id)
            elif self._case_actionable(lease):
                receipt = self.adapter.execute(lease.tenant_id, lease.action_id)
            else:
                self._finish(lease, None, "case_not_actionable")
                return
            self._finish(lease, receipt)
        except Exception:
            # The adapter may have committed before a timeout. Never execute
            # again after an uncertain result; subsequent leases only query.
            logger.warning("Mock action requires reconciliation: error_code=mock_outcome_unknown",
                           extra={"error_code": "mock_outcome_unknown"})
            self._finish(lease, None, "mock_outcome_unknown")

    def run_once(self) -> bool:
        lease = self.claim_one()
        if lease is None:
            return False
        self.process(lease)
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the development-only mock service action worker.")
    parser.add_argument("--once", action="store_true", help="Process at most one ready action and exit.")
    args = parser.parse_args()
    settings = Settings.from_environment()
    engine = build_engine()
    worker = MockActionWorker(engine, settings)
    try:
        if args.once:
            logging.basicConfig(level=logging.INFO)
            worker.run_once()
            return
        # run_loop writes the heartbeat that the container healthcheck reads.
        run_loop(ROLE, worker.run_once)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
