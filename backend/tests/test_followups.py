"""Consent, scheduling and due staff task regression against PostgreSQL."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from serviceos_api.bootstrap_local import seed_local_accounts
from serviceos_api.main import create_app
from serviceos_api.persistence.models import FollowUpJob, Message, ServiceTask
from serviceos_api.settings import Settings
from serviceos_api.worker.followups import FollowUpWorker


@pytest.fixture
def app(database_engine):
    with Session(database_engine) as session:
        seed_local_accounts(session)
    return create_app(database_engine=database_engine, settings=Settings(
        environment="test", auth_mode="local", local_password="test-only-password",
    ))


def login(app, username):
    client = TestClient(app)
    response = client.post("/api/v1/local-auth/login", json={"username": username,
                           "password": "test-only-password"})
    assert response.status_code == 200, response.text
    return client


def setup_case(customer):
    case = customer.post("/api/v1/cases", json={"problem_text": "回访测试问题"}).json()
    conversation = customer.post("/api/v1/conversations", json={}).json()
    linked = customer.post(f"/api/v1/cases/{case['id']}/conversations", json={
        "expected_version": case["version"], "conversation_id": conversation["id"],
    })
    assert linked.status_code == 200, linked.text
    return linked.json(), conversation


def test_consent_schedule_and_due_task(app, database_engine):
    customer = login(app, "customer-a")
    staff = login(app, "staff")
    other = login(app, "customer-b")
    outsider = login(app, "other-tenant")
    case, conversation = setup_case(customer)
    consent_url = f"/api/v1/cases/{case['id']}/follow-up-consents"
    schedule_url = f"/api/v1/cases/{case['id']}/follow-ups"
    consent_body = {"client_consent_id": str(uuid4()), "expected_case_version": case["version"],
                    "purpose": "确认充电恢复情况"}
    assert staff.post(consent_url, json=consent_body).status_code == 403
    assert other.post(consent_url, json=consent_body).status_code == 404
    assert outsider.get(consent_url).status_code == 404
    consent = customer.post(consent_url, json=consent_body)
    assert consent.status_code == 201, consent.text
    assert customer.post(consent_url, json=consent_body).json()["id"] == consent.json()["id"]
    assert customer.post(consent_url, json=consent_body | {"purpose": "另一个目的"}).status_code == 409
    due_at = datetime.now(timezone.utc) + timedelta(hours=1)
    body = {"client_follow_up_id": str(uuid4()), "expected_case_version": case["version"] + 1,
            "consent_record_id": consent.json()["id"], "purpose": consent_body["purpose"],
            "due_at": due_at.isoformat()}
    assert customer.post(schedule_url, json=body).status_code == 403
    assert staff.post(schedule_url, json=body | {"purpose": "其他营销用途"}).status_code == 403
    scheduled = staff.post(schedule_url, json=body)
    assert scheduled.status_code == 201, scheduled.text
    assert staff.post(schedule_url, json=body).json()["id"] == scheduled.json()["id"]
    assert staff.post(schedule_url, json=body | {"purpose": "修改目的"}).status_code == 409
    assert staff.post(schedule_url, json=body | {
        "client_follow_up_id": str(uuid4()), "expected_case_version": case["version"] + 2,
    }).status_code == 409
    assert other.get(schedule_url).status_code == 404
    worker = FollowUpWorker(database_engine)
    assert worker.run_once(due_at - timedelta(minutes=1)) is False
    assert worker.run_once(due_at + timedelta(minutes=1)) is True
    assert worker.run_once(due_at + timedelta(minutes=2)) is False
    reminder = staff.get(schedule_url).json()[0]
    assert reminder["status"] == "DUE" and reminder["task_id"]
    assert customer.get(schedule_url).json()[0]["task_id"] is None
    tasks = staff.get(f"/api/v1/conversations/{conversation['id']}/tasks").json()
    assert len([task for task in tasks if task["id"] == reminder["task_id"]]) == 1
    assert customer.get(f"/api/v1/conversations/{conversation['id']}/tasks").status_code == 403
    with Session(database_engine) as session:
        assert session.scalar(select(func.count()).select_from(ServiceTask).where(
            ServiceTask.id == reminder["task_id"])) == 1
        assert session.scalar(select(func.count()).select_from(Message).where(
            Message.related_case_id == case["id"])) == 0


def test_schedule_rejects_missing_consent_or_conversation(app):
    customer = login(app, "customer-a")
    staff = login(app, "staff")
    case = customer.post("/api/v1/cases", json={"problem_text": "需回访"}).json()
    url = f"/api/v1/cases/{case['id']}/follow-ups"
    due_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    body = {"client_follow_up_id": str(uuid4()), "expected_case_version": case["version"],
            "consent_record_id": str(uuid4()), "due_at": due_at, "purpose": "确认问题是否恢复"}
    assert staff.post(url, json=body).status_code == 404
    consent = customer.post(f"/api/v1/cases/{case['id']}/follow-up-consents", json={
        "client_consent_id": str(uuid4()), "expected_case_version": case["version"],
        "purpose": body["purpose"],
    })
    assert consent.status_code == 201, consent.text
    assert staff.post(url, json=body | {"expected_case_version": case["version"] + 1,
                                       "consent_record_id": consent.json()["id"]}).status_code == 409
