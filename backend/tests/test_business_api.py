"""HTTP acceptance checks against a migrated, disposable PostgreSQL database."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from serviceos_api.bootstrap_local import seed_local_accounts
from serviceos_api.main import create_app
from serviceos_api.persistence.models import (
    AuthSession, DeviceFact, Message, MessageJob, OutboxEvent, TenantMembership,
)
from serviceos_api.settings import Settings


@pytest.fixture
def app(database_engine):
    with Session(database_engine) as session:
        seed_local_accounts(session)
    return create_app(database_engine=database_engine, settings=Settings(
        environment="test", auth_mode="local", local_password="test-only-password",
    ))


def login(app, username="customer-a"):
    client = TestClient(app)
    result = client.post("/api/v1/local-auth/login", json={
        "username": username, "password": "test-only-password",
    })
    assert result.status_code == 200, result.text
    assert "httponly" in result.headers["set-cookie"].lower()
    assert "samesite=strict" in result.headers["set-cookie"].lower()
    return client


def conversation(client):
    response = client.post("/api/v1/conversations", json={})
    assert response.status_code == 201, response.text
    return response.json()


def message_body(key=None, text="我的充电器无法充电", **extra):
    return {"client_message_id": str(key or uuid4()),
            "content": [{"type": "text", "text": text}], **extra}


def test_login_cookie_logout_and_expiry(app, database_engine):
    client = TestClient(app)
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/local-auth/login", json={
        "username": "customer-a", "password": "wrong",
    }).status_code == 401
    client = login(app)
    assert client.get("/api/v1/auth/me").json()["kind"] == "CUSTOMER"
    token = client.cookies.get("serviceos_session")
    with Session(database_engine) as session:
        row = session.scalar(select(AuthSession).where(AuthSession.customer_id.is_not(None)).order_by(AuthSession.created_at.desc()))
        assert row.token_hash != token
        assert len(row.token_hash) == 64
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    assert client.get("/api/v1/auth/me").status_code == 401
    client = login(app)
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_customer_message_is_durable_and_deduplicated(app, database_engine):
    customer = login(app)
    conv = conversation(customer)
    body = message_body()
    first = customer.post(f"/api/v1/conversations/{conv['id']}/messages", json=body)
    assert first.status_code == 202, first.text
    assert first.json()["processing_state"] == "QUEUED"
    assert first.json()["replayed"] is False
    repeated = customer.post(f"/api/v1/conversations/{conv['id']}/messages", json=body)
    assert repeated.status_code == 202
    assert repeated.json()["replayed"] is True
    assert repeated.json()["message"]["id"] == first.json()["message"]["id"]
    altered = customer.post(f"/api/v1/conversations/{conv['id']}/messages", json=body | {
        "content": [{"type": "text", "text": "不同内容"}],
    })
    assert altered.status_code == 409
    with Session(database_engine) as session:
        message_id = first.json()["message"]["id"]
        assert session.scalar(select(func.count()).select_from(Message).where(Message.id == message_id)) == 1
        assert session.scalar(select(func.count()).select_from(MessageJob).where(MessageJob.message_id == message_id)) == 1
        assert session.scalar(select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.type == "message.created", OutboxEvent.data["message_id"].astext == message_id,
        )) == 1
    assert customer.get(f"/api/v1/conversations/{conv['id']}/messages").json()["items"][0]["id"] == message_id


def test_customer_and_tenant_ownership_internal_visibility(app):
    owner = login(app)
    other = login(app, "customer-b")
    outside = login(app, "other-tenant")
    staff = login(app, "staff")
    conv = conversation(owner)
    for client in (other, outside):
        assert client.get(f"/api/v1/conversations/{conv['id']}").status_code == 404
        assert client.get(f"/api/v1/conversations/{conv['id']}/messages").status_code == 404
        assert client.post(f"/api/v1/conversations/{conv['id']}/messages", json=message_body()).status_code == 404
    assert owner.post(f"/api/v1/conversations/{conv['id']}/messages", json=message_body(visibility="INTERNAL")).status_code == 403
    note = staff.post(f"/api/v1/conversations/{conv['id']}/messages", json=message_body(text="仅客服可见", visibility="INTERNAL"))
    assert note.status_code == 202, note.text
    assert note.json()["processing_state"] == "NOT_SCHEDULED"
    assert owner.get(f"/api/v1/conversations/{conv['id']}/messages").json()["items"] == []
    assert len(staff.get(f"/api/v1/conversations/{conv['id']}/messages").json()["items"]) == 1
    assert outside.get("/api/v1/conversations").json()["items"] == []


def test_case_device_conversation_are_independent_and_versioned(app):
    customer = login(app)
    conv1, conv2 = conversation(customer), conversation(customer)
    case_response = customer.post("/api/v1/cases", json={"problem_text": "线材接触不良"})
    assert case_response.status_code == 201, case_response.text
    case = case_response.json()
    assert case["version"] == 1
    assert customer.get("/api/v1/devices").json() == []
    device = customer.post("/api/v1/devices", json={"model": "Nano Charger"}).json()
    assert device["identity_status"] == "UNVERIFIED"
    link1 = customer.post(f"/api/v1/cases/{case['id']}/conversations", json={
        "conversation_id": conv1["id"], "expected_version": 1,
    })
    assert link1.status_code == 200, link1.text
    link2 = customer.post(f"/api/v1/cases/{case['id']}/conversations", json={
        "conversation_id": conv2["id"], "expected_version": 2,
    })
    assert link2.status_code == 200, link2.text
    linked = customer.post(f"/api/v1/cases/{case['id']}/devices", json={
        "device_id": device["id"], "expected_version": 3, "is_primary": True,
    })
    assert linked.status_code == 200, linked.text
    assert linked.json()["version"] == 4
    assert customer.post(f"/api/v1/cases/{case['id']}/devices", json={
        "device_id": device["id"], "expected_version": 1,
    }).status_code == 409
    assert customer.post(f"/api/v1/conversations/{conv1['id']}/messages", json=message_body(
        related_case_id=case["id"],
    )).status_code == 202
    assert customer.get(f"/api/v1/devices/{device['id']}/cases").json()[0]["id"] == case["id"]
    assert customer.delete(f"/api/v1/cases/{case['id']}").status_code == 409
    assert customer.delete(f"/api/v1/devices/{device['id']}").status_code == 409


def test_cross_owner_links_and_payload_privilege_rejected(app):
    first = login(app)
    second = login(app, "customer-b")
    own_conv = conversation(first)
    foreign_device = second.post("/api/v1/devices", json={"model": "A"}).json()
    case = first.post("/api/v1/cases", json={"problem_text": "问题"}).json()
    assert first.post(f"/api/v1/cases/{case['id']}/devices", json={
        "device_id": foreign_device["id"], "expected_version": 1,
    }).status_code == 404
    assert first.post("/api/v1/cases", json={
        "problem_text": "问题", "customer_id": second.get("/api/v1/auth/me").json()["actor_id"],
    }).status_code == 403
    assert first.post(f"/api/v1/conversations/{own_conv['id']}/messages", json=message_body(
        author_kind="STAFF",
    )).status_code == 422
    assert first.patch(f"/api/v1/devices/{foreign_device['id']}", json={
        "expected_revision": 1, "identity_status": "VERIFIED",
    }).status_code == 422


def test_pagination_and_cursor_scope(app):
    customer = login(app)
    first, second = conversation(customer), conversation(customer)
    ids = []
    for index in range(3):
        item = customer.post(f"/api/v1/conversations/{first['id']}/messages", json=message_body(text=str(index))).json()
        ids.append(item["message"]["id"])
    page = customer.get(f"/api/v1/conversations/{first['id']}/messages?limit=2").json()
    assert len(page["items"]) == 2
    assert page["next_cursor"] == page["items"][-1]["id"]
    tail = customer.get(f"/api/v1/conversations/{first['id']}/messages?limit=2&cursor={page['next_cursor']}").json()
    assert len(tail["items"]) == 1 and tail["next_cursor"] is None
    assert {item["id"] for item in page["items"] + tail["items"]} == set(ids)
    assert customer.get(f"/api/v1/conversations/{second['id']}/messages?cursor={ids[0]}").status_code == 422


def test_concurrent_same_key_has_one_message_job_event(app, database_engine):
    customer = login(app)
    conv = conversation(customer)
    body = message_body()
    token = customer.cookies.get("serviceos_session")

    def post_once(_):
        with TestClient(app) as client:
            client.cookies.set("serviceos_session", token)
            return client.post(f"/api/v1/conversations/{conv['id']}/messages", json=body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(post_once, range(2)))
    assert [item.status_code for item in responses] == [202, 202]
    assert responses[0].json()["message"]["id"] == responses[1].json()["message"]["id"]
    message_id = responses[0].json()["message"]["id"]
    with Session(database_engine) as session:
        assert session.scalar(select(func.count()).select_from(Message).where(Message.id == message_id)) == 1
        assert session.scalar(select(func.count()).select_from(MessageJob).where(MessageJob.message_id == message_id)) == 1


def test_origin_and_staff_revocation(app, database_engine):
    staff = login(app, "staff")
    assert staff.post("/api/v1/conversations", json={}, headers={
        "Origin": "https://unexpected.example",
    }).status_code == 403
    assert staff.get("/api/v1/auth/me").status_code == 200
    actor_id = staff.get("/api/v1/auth/me").json()["actor_id"]
    with Session(database_engine) as session:
        row = session.scalar(select(TenantMembership).where(TenantMembership.staff_user_id == actor_id))
        row.active = False
        session.commit()
    assert staff.get("/api/v1/auth/me").status_code == 403
    with Session(database_engine) as session:
        row = session.scalar(select(TenantMembership).where(TenantMembership.staff_user_id == actor_id))
        row.active = True
        session.commit()


def test_case_status_transition_is_staff_only_versioned_and_recorded(app, database_engine):
    customer = login(app)
    staff = login(app, "staff")
    case = customer.post("/api/v1/cases", json={"problem_text": "无法开机"}).json()
    endpoint = f"/api/v1/cases/{case['id']}/transitions"
    request = {"expected_version": 1, "target_status": "IN_PROGRESS", "reason": "已开始核对"}
    assert customer.post(endpoint, json=request).status_code == 403
    started = staff.post(endpoint, json=request)
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "IN_PROGRESS"
    assert staff.post(endpoint, json=request).status_code == 409
    assert staff.post(endpoint, json={
        "expected_version": 2, "target_status": "CLOSED", "reason": "不能跳级关闭",
    }).status_code == 409
    resolved = staff.post(endpoint, json={
        "expected_version": 2, "target_status": "RESOLVED", "reason": "已提供修复方案",
    })
    assert resolved.status_code == 200
    closed = staff.post(endpoint, json={
        "expected_version": 3, "target_status": "CLOSED", "reason": "客户确认已恢复",
    })
    assert closed.status_code == 200
    assert customer.delete(f"/api/v1/cases/{case['id']}").status_code == 204
    assert customer.get(f"/api/v1/cases/{case['id']}").status_code == 404
    with Session(database_engine) as session:
        recorded = session.scalars(select(OutboxEvent).where(
            OutboxEvent.type == "case.status_changed",
            OutboxEvent.data["case_id"].astext == case["id"],
        )).all()
        assert [item.data["to"] for item in recorded] == ["IN_PROGRESS", "RESOLVED", "CLOSED"]


def test_device_read_exposes_only_verified_facts(app, database_engine):
    customer = login(app)
    device = customer.post("/api/v1/devices", json={"model": "A3134"}).json()
    with Session(database_engine) as session:
        tenant_id = customer.get("/api/v1/auth/me").json()["tenant_id"]
        for validity, value in (("CANDIDATE", "maybe"), ("VERIFIED", "confirmed")):
            session.add(DeviceFact(
                tenant_id=tenant_id, device_id=device["id"], fact_key="battery_type",
                value=value, source_kind="HUMAN", source="support-check",
                validity=validity,
                verifier_kind="HUMAN" if validity == "VERIFIED" else None,
                verified_by="support" if validity == "VERIFIED" else None,
                verified_at=datetime.now(timezone.utc) if validity == "VERIFIED" else None,
            ))
        session.commit()
    read = customer.get(f"/api/v1/devices/{device['id']}")
    assert read.status_code == 200, read.text
    assert [item["value"] for item in read.json()["verified_facts"]] == ["confirmed"]


def test_fact_candidate_verify_retract_lifecycle(app):
    customer = login(app)
    staff = login(app, "staff")
    device = customer.post("/api/v1/devices", json={"model": "A3134"}).json()
    base = f"/api/v1/devices/{device['id']}"
    forged = customer.post(base + "/facts", json={
        "expected_device_revision": 1, "fact_key": "battery_type", "value": "Li-ion",
        "validity": "VERIFIED", "verified_by": "customer",
    })
    assert forged.status_code == 422
    candidate = customer.post(base + "/facts", json={
        "expected_device_revision": 1, "fact_key": "battery_type", "value": "Li-ion",
    })
    assert candidate.status_code == 201, candidate.text
    fact = candidate.json()
    assert fact["validity"] == "CANDIDATE" and fact["source_kind"] == "USER"
    assert customer.get(base).json()["verified_facts"] == []
    assert customer.get(base + "/fact-candidates").status_code == 403
    assert [item["id"] for item in staff.get(base + "/fact-candidates").json()] == [fact["id"]]
    decision = {"expected_device_revision": 2, "expected_fact_revision": 1, "reason": "核对原厂标签"}
    assert customer.post(base + f"/facts/{fact['id']}/verify", json=decision).status_code == 403
    verified = staff.post(base + f"/facts/{fact['id']}/verify", json=decision)
    assert verified.status_code == 200, verified.text
    assert verified.json()["validity"] == "VERIFIED"
    assert customer.get(base).json()["verified_facts"][0]["value"] == "Li-ion"
    assert staff.post(base + f"/facts/{fact['id']}/verify", json=decision).status_code == 409
    retract = staff.post(base + f"/facts/{fact['id']}/retract", json={
        "expected_device_revision": 3, "expected_fact_revision": 2,
        "reason": "后续实物复核发现标签不符",
    })
    assert retract.status_code == 200, retract.text
    assert retract.json()["validity"] == "RETRACTED"
    assert customer.get(base).json()["verified_facts"] == []


def test_message_job_outbox_rollback_together(app, database_engine):
    customer = login(app)
    conv = conversation(customer)
    key = str(uuid4())

    def fail_outbox(mapper, connection, target):
        if target.type == "message.created":
            raise RuntimeError("test-injected outbox failure")

    event.listen(OutboxEvent, "before_insert", fail_outbox)
    try:
        client = TestClient(app, raise_server_exceptions=False)
        client.cookies.set("serviceos_session", customer.cookies.get("serviceos_session"))
        response = client.post(f"/api/v1/conversations/{conv['id']}/messages", json=message_body(key=key))
        assert response.status_code == 500
    finally:
        event.remove(OutboxEvent, "before_insert", fail_outbox)
    with Session(database_engine) as session:
        assert session.scalar(select(func.count()).select_from(Message).where(Message.client_message_id == key)) == 0
        assert session.scalar(select(func.count()).select_from(MessageJob).where(MessageJob.conversation_id == conv["id"])) == 0
    assert customer.post(f"/api/v1/conversations/{conv['id']}/messages", json=message_body(key=key)).status_code == 202

