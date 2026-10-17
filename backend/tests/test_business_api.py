"""HTTP acceptance checks against a migrated, disposable PostgreSQL database."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import logging
import math
from time import perf_counter, sleep
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from serviceos_api.bootstrap_local import seed_local_accounts
from serviceos_api.application import auth
from serviceos_api.application.auth import Principal
from serviceos_api.application.contracts import ClaimTask
from serviceos_api.application.errors import ServiceError
from serviceos_api.application.services import ConversationService
from serviceos_api.api.business import _read_authorized_event_page, stream_events
import serviceos_api.api.business as business_api
from serviceos_api.main import create_app
from serviceos_api.persistence.models import (
    AuthSession, AgentProposal, AgentRun, CaseEvidence, DeviceFact, Message, MessageJob, OutboxEvent,
    StaffUser, TenantMembership,
)
from serviceos_api.settings import Settings
from serviceos_api.observability import SafeJsonFormatter
from serviceos_api.worker.runtime import OutboxDispatcher


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


def test_conversation_title_uses_first_public_customer_message_and_survives_login(app):
    customer = login(app)
    created = conversation(customer)
    identifier = created['id']
    assert created.get('title') == '新会话'
    staff = login(app, 'staff')
    assert staff.post(f'/api/v1/conversations/{identifier}/messages',
                      json=message_body(text='秘密内部备注，不得作为标题', visibility='INTERNAL')).status_code == 202
    assert customer.post(f'/api/v1/conversations/{identifier}/messages',
                         json=message_body(text='您好，我的充电宝充电时断断续续，该怎么排查？')).status_code == 202
    assert customer.post(f'/api/v1/conversations/{identifier}/messages',
                         json=message_body(text='后续问题不改变标题')).status_code == 202
    customer = login(app)
    listed = customer.get('/api/v1/conversations').json()['items']
    assert next(row['title'] for row in listed if row['id'] == identifier) == '充电宝充电时断断续续'
    assert customer.get(f'/api/v1/conversations/{identifier}').json()['title'] == '充电宝充电时断断续续'
    assert login(app, 'customer-b').get(f'/api/v1/conversations/{identifier}').status_code == 404


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
    case_links = customer.get(f"/api/v1/conversations/{conv1['id']}/customer-cases")
    assert case_links.status_code == 200, case_links.text
    assert case_links.json()[0]["case"]["id"] == case["id"]
    assert case_links.json()[0]["case"]["version"] == 4
    assert case_links.json()[0]["device_ids"] == [device["id"]]
    linked_conversations = customer.get(f"/api/v1/cases/{case['id']}/conversations")
    assert linked_conversations.status_code == 200, linked_conversations.text
    assert [row["id"] for row in linked_conversations.json()] == [conv2["id"], conv1["id"]]
    assert set(linked_conversations.json()[0]) == {"id", "title", "status", "created_at"}
    assert customer.get(f"/api/v1/devices/{device['id']}/cases").json()[0]["id"] == case["id"]
    assert customer.get(f"/api/v1/conversations/{conv2['id']}/customer-cases").json()[0]["case"]["id"] == case["id"]
    assert customer.get(f"/api/v1/conversations/{conv1['id']}/customer-cases").json()[0]["device_ids"] == [device["id"]]
    assert customer.delete(f"/api/v1/cases/{case['id']}").status_code == 409
    assert customer.delete(f"/api/v1/devices/{device['id']}").status_code == 409


def test_desk_case_summary_sources_and_visibility(app, database_engine):
    owner, staff = login(app), login(app, "staff")
    other, outside = login(app, "customer-b"), login(app, "other-tenant")
    conv = conversation(owner)
    path = f"/api/v1/conversations/{conv['id']}/case-summaries"
    assert staff.get(path).json() == []
    case = owner.post("/api/v1/cases", json={"problem_text": "用户报告无法充电"}).json()
    assert owner.post(f"/api/v1/cases/{case['id']}/conversations", json={
        "conversation_id": conv["id"], "expected_version": case["version"],
    }).status_code == 200
    device = owner.post("/api/v1/devices", json={"model": "Nano"}).json()
    assert owner.post(f"/api/v1/cases/{case['id']}/devices", json={
        "device_id": device["id"], "expected_version": 2,
    }).status_code == 200
    candidate = owner.post(f"/api/v1/devices/{device['id']}/facts", json={
        "expected_device_revision": 1, "fact_key": "port", "value": "USB-C",
    })
    assert candidate.status_code == 201
    with Session(database_engine) as session:
        session.add(CaseEvidence(tenant_id=owner.get("/api/v1/auth/me").json()["tenant_id"],
                                 case_id=case["id"], source="customer:chat", claim_type="USER_STATEMENT",
                                 certainty="LOW", validity="CANDIDATE", summary="插线后无灯"))
        session.commit()
    result = staff.get(path)
    assert result.status_code == 200, result.text
    facts = result.json()[0]["facts"]
    assert {item["source"] for item in facts} >= {"customer:chat", "user_statement"}
    assert all(item["verification"] in ("CANDIDATE", "UNVERIFIED") for item in facts)
    for client in (owner, other, outside):
        assert client.get(path).status_code in (403, 404)


def test_customer_case_link_reads_enforce_resource_ownership_and_return_empty_lists(app):
    owner, other, outside, staff = (login(app), login(app, "customer-b"),
                                    login(app, "other-tenant"), login(app, "staff"))
    conv = conversation(owner)
    case = owner.post("/api/v1/cases", json={"problem_text": "仅为关联读取测试"}).json()

    assert owner.get(f"/api/v1/conversations/{conv['id']}/customer-cases").json() == []
    assert owner.get(f"/api/v1/cases/{case['id']}/conversations").json() == []
    assert staff.get(f"/api/v1/conversations/{conv['id']}/customer-cases").json() == []
    assert staff.get(f"/api/v1/cases/{case['id']}/conversations").json() == []
    for client in (other, outside):
        assert client.get(f"/api/v1/conversations/{conv['id']}/customer-cases").status_code == 404
        assert client.get(f"/api/v1/cases/{case['id']}/conversations").status_code == 404
    anonymous = TestClient(app)
    assert anonymous.get(f"/api/v1/conversations/{conv['id']}/customer-cases").status_code == 401
    assert anonymous.get(f"/api/v1/cases/{case['id']}/conversations").status_code == 401


def test_mode_transition_latest_policy_and_task_claim(app, database_engine):
    owner, staff = login(app), login(app, "staff")
    conv = conversation(owner)
    url = f"/api/v1/conversations/{conv['id']}"
    assert owner.post(f"{url}/mode-transitions", json={
        "target_mode": "HUMAN_LEAD", "reply_policy": "HUMAN_ONLY", "expected_version": 1,
        "reason": "需要人工处理",
    }).status_code == 403
    switched = staff.post(f"{url}/mode-transitions", json={
        "target_mode": "HUMAN_LEAD", "reply_policy": "HUMAN_ONLY", "expected_version": 1,
        "reason": "需要人工处理",
    })
    assert switched.status_code == 200, switched.text
    assert switched.json()["version"] == 2
    assert staff.post(f"{url}/mode-transitions", json={
        "target_mode": "AI_LEAD", "reply_policy": "AI_AUTO", "expected_version": 1,
        "reason": "需要重新开启",
    }).status_code == 409
    task = owner.post(f"{url}/assistance-requests", json={"reason": "请求人工协助"})
    assert task.status_code == 201, task.text
    duplicate = owner.post(f"{url}/assistance-requests", json={"reason": "再次提交相同协助"})
    assert duplicate.status_code == 201 and duplicate.json()["id"] == task.json()["id"]
    assert duplicate.json()["reason"] == task.json()["reason"]
    assert owner.get(f"{url}/tasks").status_code == 403
    customer_tasks = owner.get(f"{url}/customer-assistance")
    assert customer_tasks.status_code == 200
    assert customer_tasks.json()["items"] == [{
        "id": task.json()["id"], "status": "OPEN", "version": 1,
        "created_at": task.json()["created_at"],
    }]
    assert staff.get(f"{url}/customer-assistance").status_code == 403
    assert login(app, "customer-b").get(f"{url}/customer-assistance").status_code == 404
    queue = staff.get("/api/v1/tasks", params={"queue": "OPEN"})
    assert queue.status_code == 200 and queue.json()["items"][0]["id"] == task.json()["id"]
    assert len(staff.get(f"{url}/tasks").json()) == 1
    task_id = task.json()["id"]
    first = staff.post(f"/api/v1/tasks/{task_id}/claim", json={"expected_version": 1})
    assert first.status_code == 200, first.text
    assert first.json()["version"] == 2
    mine = staff.get("/api/v1/tasks", params={"queue": "MINE"})
    assert mine.status_code == 200 and [item["id"] for item in mine.json()["items"]] == [task_id]
    assert staff.get("/api/v1/tasks", params={"queue": "OPEN"}).json()["items"] == []
    assert owner.get(f"{url}/customer-assistance").json()["items"][0]["status"] == "ASSIGNED"
    OutboxDispatcher(database_engine).dispatch_batch(100)
    public_assistance = [event for event in owner.get(f"{url}/event-history").json()["items"]
                         if event["type"] == "assistance.status_changed"]
    assert [(event["data"]["status"], event["visibility"]) for event in public_assistance] == [
        ("OPEN", "PUBLIC"), ("ASSIGNED", "PUBLIC"),
    ]
    assert set(public_assistance[0]["data"]) == {"task_id", "status", "version"}
    assert staff.post(f"/api/v1/tasks/{task_id}/claim", json={"expected_version": 1}).status_code == 409
    restored = staff.post(f"{url}/mode-transitions", json={
        "target_mode": "AI_LEAD", "reply_policy": "AI_AUTO", "expected_version": 2,
        "reason": "人工已处理完毕",
    })
    assert restored.status_code == 200
    assert restored.json()["collaboration_mode"] == "AI_LEAD"


def test_persisted_reply_draft_requires_edit_approval_then_public_send(app, database_engine):
    customer, staff = login(app), login(app, "staff")
    conv = conversation(customer)
    submitted = customer.post(f"/api/v1/conversations/{conv['id']}/messages", json=message_body())
    assert submitted.status_code == 202
    staff_view = staff.get("/api/v1/auth/me").json()
    with Session(database_engine) as session:
        job = session.scalar(select(MessageJob).where(MessageJob.message_id == submitted.json()["message"]["id"]))
        run = AgentRun(tenant_id=UUID(staff_view["tenant_id"]), job_id=job.id, conversation_id=UUID(conv["id"]),
                       message_id=UUID(submitted.json()["message"]["id"]), thread_id="draft-test",
                       lease_token=uuid4(), provider="test", model="test")
        session.add(run)
        session.flush()
        source = Message(tenant_id=run.tenant_id, conversation_id=run.conversation_id, author_kind="AGENT",
                         visibility="INTERNAL", content=[{"type": "text", "text": "AI 初稿内容"}],
                         client_message_id=run.id, request_hash="a" * 64)
        session.add(source)
        session.flush()
        proposal = AgentProposal(tenant_id=run.tenant_id, agent_run_id=run.id, conversation_id=run.conversation_id,
                                 proposal_type="REPLY", idempotency_key="reply-test",
                                 payload={"summary": "测试摘要", "source_message_id": str(source.id)})
        session.add(proposal)
        session.commit()
        proposal_id = proposal.id
    created = staff.post(f"/api/v1/proposals/{proposal_id}/reply-drafts", json={"draft_id": str(uuid4())})
    assert created.status_code == 201, created.text
    draft = created.json()
    assert draft["status"] == "IN_COMPOSER" and draft["content"] == "AI 初稿内容"
    assert staff.patch(f"/api/v1/reply-drafts/{draft['id']}", json={
        "expected_version": 1, "content": "客服编辑后的公开答复",
    }).json()["status"] == "EDITED"
    approved = staff.post(f"/api/v1/reply-drafts/{draft['id']}/approval", json={
        "approval_id": str(uuid4()), "expected_version": 2,
    })
    assert approved.status_code == 200 and approved.json()["status"] == "APPROVED"
    before_send = customer.get(f"/api/v1/conversations/{conv['id']}/messages").json()["items"]
    assert len(before_send) == 1 and before_send[0]["content"][0]["text"] == "我的充电器无法充电"
    key = str(uuid4())
    send = staff.post(f"/api/v1/reply-drafts/{draft['id']}/send", json={
        "client_message_id": key, "expected_version": 3,
    })
    assert send.status_code == 202, send.text
    assert send.json()["message"]["visibility"] == "PUBLIC"
    assert send.json()["message"]["author_kind"] == "STAFF"
    replay = staff.post(f"/api/v1/reply-drafts/{draft['id']}/send", json={
        "client_message_id": key, "expected_version": 3,
    })
    assert replay.status_code == 202 and replay.json()["replayed"] is True
    visible = customer.get(f"/api/v1/conversations/{conv['id']}/messages").json()["items"]
    assert len(visible) == 2
    assert visible[-1]["content"][0]["text"] == "客服编辑后的公开答复"
    assert staff.get(f"/api/v1/conversations/{conv['id']}/reply-drafts").json()[0]["status"] == "SENT"


def test_two_staff_claim_same_version_only_one_wins(app, database_engine):
    owner = login(app)
    conv = conversation(owner)
    task = owner.post(f"/api/v1/conversations/{conv['id']}/assistance-requests",
                      json={"reason": "需要人工协助"}).json()
    tenant_id = owner.get("/api/v1/auth/me").json()["tenant_id"]
    staff = login(app, "staff").get("/api/v1/auth/me").json()
    with Session(database_engine) as session:
        second = StaffUser(display_name="第二位客服", external_subject=f"test:{uuid4()}")
        session.add(second)
        session.flush()
        session.add(TenantMembership(tenant_id=tenant_id, staff_user_id=second.id, role="SUPPORT"))
        session.commit()
        second_id = second.id

    def claim(actor_id):
        with Session(database_engine) as session:
            service = ConversationService(session, Principal(tenant_id=tenant_id, actor_id=actor_id,
                                                            kind="STAFF", display_name="客服", role="SUPPORT"))
            try:
                return service.claim_task(task["id"], ClaimTask(expected_version=1)).assignee_id
            except ServiceError as error:
                return error.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, [staff["actor_id"], second_id]))
    assert sorted(isinstance(result, int) for result in results) == [False, True]
    assert 409 in results


def test_event_history_filters_internal_and_resumes_without_new_job(app, database_engine):
    owner, staff = login(app), login(app, "staff")
    outside = login(app, "other-tenant")
    conv = conversation(owner)
    url = f"/api/v1/conversations/{conv['id']}"
    first = owner.post(f"{url}/messages", json=message_body(text="公开问题"))
    assert first.status_code == 202
    internal = staff.post(f"{url}/messages", json=message_body(text="内部备注", visibility="INTERNAL"))
    assert internal.status_code == 202
    second = staff.post(f"{url}/messages", json=message_body(text="公开答复"))
    assert second.status_code == 202
    with Session(database_engine) as session:
        jobs_before = session.scalar(select(func.count()).select_from(MessageJob).where(
            MessageJob.conversation_id == conv["id"],
        ))
    OutboxDispatcher(database_engine).dispatch_batch(100)
    public = owner.get(f"{url}/event-history").json()["items"]
    all_events = staff.get(f"{url}/event-history").json()["items"]
    assert all(event["visibility"] == "PUBLIC" for event in public)
    assert len(all_events) > len(public)
    assert str(internal.json()["message"]["id"]) not in [
        event["data"].get("message_id") for event in public
    ]
    first_sequence = public[0]["sequence"]
    resumed = owner.get(f"{url}/event-history", params={"after": first_sequence}).json()["items"]
    assert [event["sequence"] for event in resumed] == [
        event["sequence"] for event in public if event["sequence"] > first_sequence
    ]
    assert outside.get(f"{url}/event-history").status_code == 404
    with Session(database_engine) as session:
        jobs_after = session.scalar(select(func.count()).select_from(MessageJob).where(
            MessageJob.conversation_id == conv["id"],
        ))
    assert jobs_after == jobs_before == 1


def test_sse_event_page_reader_revalidates_identity_and_filters_visibility(app, database_engine):
    owner = login(app)
    staff = login(app, "staff")
    conv = conversation(owner)
    url = f"/api/v1/conversations/{conv['id']}"
    public = owner.post(f"{url}/messages", json=message_body(text="客户可见内容"))
    internal = staff.post(f"{url}/messages", json=message_body(text="客服内部内容", visibility="INTERNAL"))
    assert public.status_code == internal.status_code == 202
    OutboxDispatcher(app.state.database_engine).dispatch_batch(100)
    page, query_ms = _read_authorized_event_page(
        database_engine, UUID(conv["id"]), owner.cookies.get("serviceos_session"), 0)
    assert page.items
    assert all(event.visibility == "PUBLIC" for event in page.items)
    assert public.json()["message"]["id"] in [event.data.get("message_id") for event in page.items]
    assert internal.json()["message"]["id"] not in [event.data.get("message_id") for event in page.items]
    assert query_ms >= 0
    owner.post("/api/v1/auth/logout")
    with pytest.raises(ServiceError):
        _read_authorized_event_page(database_engine, UUID(conv["id"]), "revoked-token", 0)


def test_sse_stream_uses_last_event_id_and_skips_internal_sequence_holes(app, database_engine):
    owner, staff = login(app), login(app, "staff")
    conv = conversation(owner)
    url = f"/api/v1/conversations/{conv['id']}"
    first = owner.post(f"{url}/messages", json=message_body(text="first public"))
    internal = staff.post(f"{url}/messages", json=message_body(text="PRIVATE_INTERNAL_SENTINEL", visibility="INTERNAL"))
    latest = owner.post(f"{url}/messages", json=message_body(text="next public"))
    assert first.status_code == internal.status_code == latest.status_code == 202
    OutboxDispatcher(database_engine).dispatch_batch(100)
    history = owner.get(f"{url}/event-history").json()["items"]
    first_event = next(event for event in history
                       if event["data"].get("message_id") == first.json()["message"]["id"])
    latest_event = next(event for event in history
                         if event["data"].get("message_id") == latest.json()["message"]["id"])
    assert latest_event["sequence"] > first_event["sequence"]
    with Session(database_engine) as session:
        actor = auth.authenticated_principal(session, owner.cookies.get("serviceos_session"))

    class QuietRequest:
        app = SimpleNamespace(state=SimpleNamespace(database_engine=database_engine))
        cookies = {"serviceos_session": owner.cookies.get("serviceos_session")}

        async def is_disconnected(self):
            return False

    async def read_next_event():
        response = await stream_events(UUID(conv["id"]), QuietRequest(), actor,
                                       after=0, last_event_id=first_event["sequence"])
        iterator = response.body_iterator
        chunk = await anext(iterator)
        await iterator.aclose()
        return chunk

    chunk = asyncio.run(read_next_event())
    assert chunk.startswith(f"id: {latest_event['sequence']}\n")
    assert latest.json()["message"]["id"] in chunk
    assert internal.json()["message"]["id"] not in chunk


def test_sse_stream_offloads_database_reads_and_logs_disconnect_without_business_ids(
        app, database_engine, caplog):
    owner = login(app)
    conv = conversation(owner)
    response = owner.post(
        f"/api/v1/conversations/{conv['id']}/messages", json=message_body(text="PRIVATE_MESSAGE_BODY_SENTINEL"))
    assert response.status_code == 202
    OutboxDispatcher(database_engine).dispatch_batch(100)
    with Session(database_engine) as session:
        actor = auth.authenticated_principal(session, owner.cookies.get("serviceos_session"))

    class DisconnectingRequest:
        app = SimpleNamespace(state=SimpleNamespace(database_engine=database_engine))
        cookies = {"serviceos_session": owner.cookies.get("serviceos_session")}

        def __init__(self):
            self.checks = 0

        async def is_disconnected(self):
            self.checks += 1
            return self.checks > 1

    async def read_one_chunk():
        stream_response = await stream_events(UUID(conv["id"]), DisconnectingRequest(), actor, after=0,
                                              last_event_id=None)
        assert stream_response.headers["cache-control"] == "no-store"
        iterator = stream_response.body_iterator
        first = await anext(iterator)
        await iterator.aclose()
        return first

    with caplog.at_level(logging.INFO, logger="serviceos.events"):
        chunk = asyncio.run(read_one_chunk())

    assert "data:" in chunk
    record = next(record for record in reversed(caplog.records)
                  if getattr(record, "event_code", None) == "events.stream_closed")
    assert record.close_reason == "disconnected"
    assert record.poll_count == 1
    serialized = SafeJsonFormatter().format(record)
    assert "PRIVATE_MESSAGE_BODY_SENTINEL" not in serialized
    assert conv["id"] not in serialized


def test_sse_poll_load_at_1_10_50_streams_keeps_event_loop_responsive(app, database_engine, monkeypatch, caplog):
    owner = login(app)
    conv = conversation(owner)
    OutboxDispatcher(database_engine).dispatch_batch(100)
    latest = owner.get(f"/api/v1/conversations/{conv['id']}/event-history").json()["next_after"]
    with Session(database_engine) as session:
        actor = auth.authenticated_principal(session, owner.cookies.get("serviceos_session"))
    token = owner.cookies.get("serviceos_session")
    engine = database_engine
    samples: list[float] = []
    original_reader = business_api._read_authorized_event_page
    inject_delay = False

    def measured_reader(*args):
        # Simulate a slow synchronous DB read to verify that it cannot stall the ASGI loop.
        if inject_delay:
            sleep(0.05)
        started = perf_counter()
        result = original_reader(*args)
        samples.append((perf_counter() - started) * 1000)
        return result

    monkeypatch.setattr(business_api, "_read_authorized_event_page", measured_reader)

    class QuietRequest:
        app = SimpleNamespace(state=SimpleNamespace(database_engine=engine))
        cookies = {"serviceos_session": token}

        async def is_disconnected(self):
            return False

    async def open_once():
        response = await stream_events(UUID(conv["id"]), QuietRequest(), actor, after=latest,
                                       last_event_id=latest)
        iterator = response.body_iterator
        first_chunk = await anext(iterator)
        second_chunk = await anext(iterator)
        await iterator.aclose()
        assert ": keepalive" in first_chunk and ": keepalive" in second_chunk

    async def exercise(count, check_loop_responsiveness=False):
        nonlocal inject_delay
        inject_delay = check_loop_responsiveness
        samples.clear()
        beats: list[float] = []
        done = False

        async def heartbeat():
            while not done:
                beats.append(perf_counter())
                await asyncio.sleep(0.005)

        ticker = asyncio.create_task(heartbeat())
        started = perf_counter()
        await asyncio.gather(*(open_once() for _ in range(count)))
        elapsed_ms = (perf_counter() - started) * 1000
        done = True
        await ticker
        gaps_ms = [(right - left) * 1000 for left, right in zip(beats, beats[1:])]
        assert len(samples) == count * 2
        assert gaps_ms and max(gaps_ms) < 500
        ordered = sorted(samples)
        p50 = ordered[(len(ordered) - 1) // 2]
        p95 = ordered[math.ceil(len(ordered) * 0.95) - 1]
        print(
            f"SSE streams={count} read_ms_p50={p50:.2f} read_ms_p95={p95:.2f} "
            f"max_loop_gap_ms={max(gaps_ms):.2f} wall_ms={elapsed_ms:.2f}")

    with caplog.at_level(logging.INFO, logger="serviceos.events"):
        asyncio.run(exercise(1))
        asyncio.run(exercise(10))
        asyncio.run(exercise(50))
        asyncio.run(exercise(50, check_loop_responsiveness=True))
    closed = [record for record in caplog.records
              if getattr(record, "event_code", None) == "events.stream_closed"]
    assert len(closed) == 111
    assert all(record.poll_count == 2 and record.empty_poll_count == 2 for record in closed)
    assert business_api._active_streams == 0


def test_ui_revision_isolation_and_low_risk_intent(app, database_engine):
    owner, staff = login(app), login(app, "staff")
    outside = login(app, "other-tenant")
    conv = conversation(owner)
    url = f"/api/v1/conversations/{conv['id']}"
    public = owner.post(f"{url}/ui-document/refresh")
    assert public.status_code == 200, public.text
    doc = public.json()
    assert doc["revision"] == 1 and doc["visibility"] == "PUBLIC"
    assert doc["components"][0]["type"] == "ActionBar"
    assert owner.get(f"{url}/ui-document").json()["ui_id"] == doc["ui_id"]
    internal = staff.post(f"{url}/ui-document/refresh")
    assert internal.status_code == 200, internal.text
    assert internal.json()["visibility"] == "INTERNAL"
    assert staff.get(f"{url}/ui-document").json()["ui_id"] != doc["ui_id"]
    assert owner.get(f"{url}/ui-document").json()["ui_id"] == doc["ui_id"]
    assert outside.get(f"{url}/ui-document").status_code == 404
    body = {"client_action_id": str(uuid4()), "ui_id": doc["ui_id"], "revision": 1,
            "action_id": "request-human-assistance", "input": {"reason": "请求客服协助"},
            "expected_conversation_version": 1}
    first = owner.post(f"{url}/ui-actions", json=body)
    assert first.status_code == 200, first.text
    assert first.json()["replayed"] is False
    replay = owner.post(f"{url}/ui-actions", json=body)
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    assert replay.json()["task_id"] == first.json()["task_id"]
    second_action = {**body, "client_action_id": str(uuid4())}
    reused = owner.post(f"{url}/ui-actions", json=second_action)
    assert reused.status_code == 200 and reused.json()["task_id"] == first.json()["task_id"]
    assert owner.get(f"{url}/customer-assistance").json()["items"] and len(
        owner.get(f"{url}/customer-assistance").json()["items"]) == 1
    changed = {**body, "input": {"reason": "不同原因"}}
    assert owner.post(f"{url}/ui-actions", json=changed).status_code == 409
    assert staff.post(f"{url}/ui-actions", json={**body, "client_action_id": str(uuid4())}).status_code == 403
    switched = staff.post(f"{url}/mode-transitions", json={
        "target_mode": "HUMAN_LEAD", "reply_policy": "HUMAN_ONLY",
        "expected_version": 1, "reason": "人工已接管",
    })
    assert switched.status_code == 200
    refreshed = owner.post(f"{url}/ui-document/refresh")
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["ui_id"] == doc["ui_id"]
    assert refreshed.json()["revision"] == 2
    stale = {**body, "client_action_id": str(uuid4())}
    assert owner.post(f"{url}/ui-actions", json=stale).status_code == 409
    OutboxDispatcher(database_engine).dispatch_batch(100)
    assert all(event["visibility"] == "PUBLIC" for event in owner.get(f"{url}/event-history").json()["items"])
    assert any(event["type"] == "ui.document.published" and event["visibility"] == "INTERNAL"
               for event in staff.get(f"{url}/event-history").json()["items"])


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
            ).order_by(OutboxEvent.created_at, OutboxEvent.id)).all()
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

