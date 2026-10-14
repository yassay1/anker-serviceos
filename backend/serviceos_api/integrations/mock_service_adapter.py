"""Durable local simulation of an external service request.

It is intentionally enabled only for development and tests. The operation row
represents the mock system's own receipt, separate from CaseAction's copy.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from serviceos_api.persistence.models import MockServiceOperation
from serviceos_api.settings import Settings


@dataclass(frozen=True)
class MockReceipt:
    external_reference: str
    result: str
    received_at: datetime


class MockServiceAdapter:
    def __init__(self, engine, settings: Settings):
        if settings.environment not in ("development", "test"):
            raise RuntimeError("Mock service operations are disabled outside development and tests.")
        if settings.mock_action_result not in ("SUCCEEDED", "FAILED"):
            raise RuntimeError("Invalid local mock action result.")
        self.engine = engine
        self.result = settings.mock_action_result

    @staticmethod
    def _receipt(row: MockServiceOperation | None) -> MockReceipt | None:
        if row is None:
            return None
        return MockReceipt(row.external_reference, row.result, row.created_at)

    def lookup(self, tenant_id: UUID, action_id: UUID) -> MockReceipt | None:
        with Session(self.engine) as session:
            row = session.scalar(select(MockServiceOperation).where(
                MockServiceOperation.tenant_id == tenant_id,
                MockServiceOperation.action_id == action_id,
            ))
            return self._receipt(row)

    def execute(self, tenant_id: UUID, action_id: UUID) -> MockReceipt:
        # Stable key and unique constraint make a retry return the original
        # simulated operation; never create a second operation for one action.
        with Session(self.engine, expire_on_commit=False) as session:
            session.execute(insert(MockServiceOperation).values(
                tenant_id=tenant_id, action_id=action_id,
                external_reference=f"MOCK-{action_id}", result=self.result,
            ).on_conflict_do_nothing(index_elements=["tenant_id", "action_id"]))
            session.commit()
            row = session.scalar(select(MockServiceOperation).where(
                MockServiceOperation.tenant_id == tenant_id,
                MockServiceOperation.action_id == action_id,
            ))
            return self._receipt(row)
