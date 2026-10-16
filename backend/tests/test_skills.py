from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from serviceos_api.api.dependencies import get_actor, get_session
from serviceos_api.api.skills import router
from serviceos_api.agents.runtime import build_system_prompt
from serviceos_api.application.agent_services import AgentContextBuilder, AgentToolService
from serviceos_api.application.auth import Principal
from serviceos_api.application.errors import ServiceError
from serviceos_api.application.skills import (
    ServiceExpressionSignal,
    SkillService,
    needs_service_expression_guidance,
)
from serviceos_api.persistence.models import AgentRun, Message, StaffUser, Tenant
from test_worker_runtime import seed_message


def active_skill_run(session):
    tenant, customer, conversation, message, job, _ = seed_message(session)
    token = uuid4()
    job.status = "RUNNING"
    job.attempt_count = 1
    job.lease_token = token
    job.lease_expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    run = AgentRun(tenant_id=tenant.id, job_id=job.id, conversation_id=conversation.id,
                   message_id=message.id, thread_id=str(conversation.id), lease_token=token,
                   provider="test", model="test")
    session.add(run)
    session.flush()
    return tenant, customer, conversation, message, job, run


def tool_service(session, tenant, conversation, run):
    return AgentToolService(session, tenant.id, conversation.id, run.id, run.lease_token)


def test_skill_load_is_internal_bounded_idempotent_and_has_authorized_source(db_session):
    tenant, _, conversation, message, _, run = active_skill_run(db_session)
    run.result_payload = {"preserved": "audit"}
    service = tool_service(db_session, tenant, conversation, run)
    first = service.load_skill("diagnose-no-charge", "1.0.0")
    assert service.load_skill("diagnose-no-charge", "1.0.0").payload == first.payload
    assert first.status == "LOADED" and len(first.payload["instructions"]) <= 2000
    assert first.payload["allowed_tools"] == ["lookup_manual"]
    db_session.refresh(run)
    entries = run.result_payload["skill_executions"]
    assert run.result_payload["preserved"] == "audit"
    assert len(entries) == 1 and entries[0]["visibility"] == "INTERNAL"
    assert entries[0]["status"] == "LOADED"
    assert entries[0]["source_message_ids"] == [str(message.id)]
    assert "output" not in entries[0] and "instructions" not in entries[0]
    context = AgentContextBuilder(db_session, tenant.id).build(conversation.id, message.id)
    assert [skill["skill_id"] for skill in context["available_skills"]] == ["diagnose-no-charge"]


@pytest.mark.parametrize("skill_id,version,error", [
    ("unknown", "1.0.0", "skill_unavailable"),
    ("diagnose-no-charge", "99", "skill_unavailable"),
    ("emotion-assessment", "1.0.0", "skill_not_callable"),
])
def test_unknown_or_prepared_skill_never_writes_execution(db_session, skill_id, version, error):
    tenant, _, conversation, _, _, run = active_skill_run(db_session)
    with pytest.raises(ValueError, match=error):
        tool_service(db_session, tenant, conversation, run).load_skill(skill_id, version)
    assert not run.result_payload


@pytest.mark.parametrize("invalid", ["expired", "token", "run", "tenant", "conversation", "archived", "source"])
def test_skill_loading_and_manual_lookup_are_fenced(db_session, invalid):
    tenant, _, conversation, message, job, run = active_skill_run(db_session)
    service = tool_service(db_session, tenant, conversation, run)
    if invalid == "expired":
        job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    elif invalid == "token":
        job.lease_token = uuid4()
    elif invalid == "run":
        run.status = "COMPLETED"
    elif invalid == "tenant":
        service.tenant_id = uuid4()
    elif invalid == "conversation":
        service.conversation_id = uuid4()
    elif invalid == "archived":
        conversation.status = "ARCHIVED"
    else:
        # A customer message is PUBLIC by constraint, so an authorized source cannot be forged by
        # flipping its visibility. Repoint the run at an internal staff note instead.
        staff = db_session.scalar(select(StaffUser).where(StaffUser.external_subject == "local:staff"))
        note = Message(tenant_id=tenant.id, conversation_id=conversation.id, author_kind="STAFF",
                       author_staff_id=staff.id, visibility="INTERNAL",
                       content=[{"type": "text", "text": "内部备注"}])
        db_session.add(note)
        db_session.flush()
        message, job.message_id, run.message_id = note, note.id, note.id
    db_session.flush()
    for operation in (lambda: service.load_skill("diagnose-no-charge", "1.0.0"),
                      lambda: service.lookup_manual("private query")):
        with pytest.raises(ValueError):
            operation()
    assert not run.result_payload


def emotion_data():
    return dict(valence="negative", cue="frustration", evidence="explicit",
                source_message_ids=[uuid4()])


def test_prepared_emotion_signal_contract_is_coarse():
    result = ServiceExpressionSignal(**emotion_data())
    assert result.valence == "negative"
    assert result.cue == "frustration"
    assert result.evidence == "explicit"


@pytest.mark.parametrize("patch", [
    {"source_message_ids": []}, {"source_message_ids": [uuid4(), uuid4()]},
    {"valence": "angry"}, {"cue": "rage"}, {"evidence": "0.99"},
    {"raw_reasoning": "private"}, {"recommended_strategy": "refund"},
])
def test_emotion_contract_rejects_unbounded_or_authorizing_fields(patch):
    with pytest.raises(ValidationError):
        ServiceExpressionSignal(**(emotion_data() | patch))


@pytest.mark.parametrize("text,expected", [
    ("你们一直没解决，我很失望", True),
    ("我看不懂这一步", True),
    ("担心继续充电会不会有问题", True),
    ("谢谢，已经解决了", False),
    ("设备序列号是 ABC123", False),
])
def test_service_expression_guidance_gate_is_lightweight(text, expected):
    assert needs_service_expression_guidance(text) is expected


def test_service_expression_guidance_is_only_injected_for_triggered_turns():
    neutral = build_system_prompt("设备序列号是 ABC123")
    triggered = build_system_prompt("你们一直没解决，我很失望")
    assert "当前轮回复指导" not in neutral
    assert "当前轮回复指导" in triggered
    assert "不虚构时限" in triggered


def test_staff_skill_api_enforces_pagination_tenant_and_safe_projection(db_session):
    tenant, customer, conversation, _, _, run = active_skill_run(db_session)
    tool_service(db_session, tenant, conversation, run).load_skill("diagnose-no-charge", "1.0.0")
    first_run = run.id
    # Add a second legitimate execution in a second customer turn in this conversation.
    from serviceos_api.persistence.models import MessageJob
    message = Message(tenant_id=tenant.id, conversation_id=conversation.id, author_kind="CUSTOMER",
                      author_customer_id=customer.id, visibility="PUBLIC", content=[{"type": "text", "text": "follow up"}])
    db_session.add(message)
    db_session.flush()
    job = MessageJob(tenant_id=tenant.id, conversation_id=conversation.id, message_id=message.id,
                     status="RUNNING", lease_token=uuid4(), attempt_count=1,
                     lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5))
    db_session.add(job)
    db_session.flush()
    second = AgentRun(tenant_id=tenant.id, job_id=job.id, conversation_id=conversation.id,
                      message_id=message.id, thread_id=str(conversation.id), lease_token=job.lease_token,
                      provider="test", model="test", created_at=run.created_at + timedelta(seconds=1))
    db_session.add(second)
    db_session.flush()
    tool_service(db_session, tenant, conversation, second).load_skill("diagnose-no-charge", "1.0.0")
    payload = dict(run.result_payload)
    payload["skill_executions"] = [dict(payload["skill_executions"][0], raw_reasoning="DO NOT LEAK")]
    run.result_payload = payload
    db_session.flush()

    actor = Principal(tenant.id, uuid4(), "STAFF", "客服", "SUPPORT")
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_actor] = lambda: actor
    app.dependency_overrides[get_session] = lambda: db_session

    @app.exception_handler(ServiceError)
    async def handle_error(_, error):
        return JSONResponse({"detail": str(error)}, status_code=error.status)

    with TestClient(app) as client:
        catalog = client.get("/api/v1/skills")
        assert catalog.status_code == 200
        assert {item["skill_id"]: item["availability"] for item in catalog.json()["items"]} == {
            "diagnose-no-charge": "AVAILABLE", "emotion-assessment": "PREPARED"}
        endpoint = f"/api/v1/conversations/{conversation.id}/skill-executions"
        first = client.get(endpoint, params={"limit": 1})
        assert first.status_code == 200 and "DO NOT LEAK" not in first.text
        assert first.json()["items"][0]["run_id"] == str(first_run)
        following = client.get(endpoint, params={"limit": 1, "after": first.json()["next_after"]})
        assert following.json()["items"][0]["run_id"] == str(second.id)
        assert following.json()["next_after"] is None
        assert client.get(endpoint, params={"limit": 101}).status_code == 422
        assert client.get(endpoint, params={"after": "bad"}).status_code == 422
        other = db_session.scalar(select(Tenant).where(Tenant.slug == "local-demo-b"))
        actor = Principal(other.id, uuid4(), "STAFF", "其他租户客服", "SUPPORT")
        assert client.get(endpoint).status_code == 404
        actor = Principal(tenant.id, customer.id, "CUSTOMER", "客户")
        assert client.get(endpoint).status_code == 403
        assert client.get("/api/v1/skills").status_code == 403
    assert SkillService(db_session, Principal(tenant.id, uuid4(), "STAFF", "客服")).executions(
        conversation.id, limit=100).items
