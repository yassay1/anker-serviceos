"""Check the state decisions shared by workers without a database dependency."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from serviceos_api.application import actions, followups
from serviceos_api.integrations.mock_service_adapter import MockReceipt


def test_mock_action_claim_and_uncertain_outcome_preserve_reconciliation():
    now = datetime.now(timezone.utc)
    action = SimpleNamespace(status="APPROVED", attempt_count=0, version=1,
                             lease_token=None, lease_expires_at=None, last_error_code=None,
                             available_at=None, tenant_id=uuid4(), case_id=uuid4(), id=uuid4(),
                             receipt_result=None, receipt_reference=None, receipt_at=None)
    token = uuid4()

    assert actions.claim_mock_action(action, token, now, 90) is False
    assert (action.status, action.attempt_count, action.version) == ("EXECUTING", 1, 2)
    assert action.lease_token == token and action.lease_expires_at == now + timedelta(seconds=90)

    actions.finish_mock_action(None, action, None, "mock_outcome_unknown", now)
    assert action.status == "UNKNOWN" and action.last_error_code == "mock_outcome_unknown"
    assert action.available_at == now + timedelta(seconds=2)
    assert action.lease_token is None and action.version == 3
    assert actions.claim_mock_action(action, uuid4(), now, 90) is True


def test_mock_action_receipt_emits_only_the_recorded_result(monkeypatch):
    events = []
    monkeypatch.setattr(actions, "enqueue_case_events", lambda *args: events.append(args))
    now = datetime.now(timezone.utc)
    action = SimpleNamespace(status="EXECUTING", attempt_count=1, version=2,
                             lease_token=uuid4(), lease_expires_at=now, last_error_code=None,
                             tenant_id=uuid4(), case_id=uuid4(), id=uuid4())
    receipt = MockReceipt("MOCK-123", "SUCCEEDED", now)

    actions.finish_mock_action(object(), action, receipt, None, now)

    assert (action.status, action.receipt_result, action.receipt_reference, action.receipt_at) == (
        "SUCCEEDED", "SUCCEEDED", "MOCK-123", now,
    )
    assert action.lease_token is None and action.version == 3
    assert len(events) == 1 and events[0][4]["status"] == "SUCCEEDED" and events[0][5] == "PUBLIC"


def test_due_follow_up_creates_one_internal_task_in_callers_transaction(monkeypatch):
    events = []
    monkeypatch.setattr(followups, "enqueue_case_events", lambda *args: events.append(args))
    task_id = uuid4()

    class Session:
        def __init__(self):
            self.rows = []

        def add(self, row):
            self.rows.append(row)

        def flush(self):
            self.rows[0].id = task_id

    session = Session()
    now = datetime.now(timezone.utc)
    job = SimpleNamespace(id=uuid4(), tenant_id=uuid4(), conversation_id=uuid4(),
                          case_id=uuid4(), purpose="确认恢复情况", scheduled_by=uuid4(),
                          status="SCHEDULED", task_id=None, reminded_at=None)

    followups.complete_due_follow_up(session, job, now)

    assert len(session.rows) == 2
    assert session.rows[1].staff_user_id == job.scheduled_by
    assert (job.status, job.task_id, job.reminded_at) == ("DUE", task_id, now)
    assert len(events) == 1 and events[0][4]["task_id"] == str(task_id) and events[0][5] == "INTERNAL"
