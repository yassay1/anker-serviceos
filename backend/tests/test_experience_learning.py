"""A verified case seeds an auditable experience candidate; only approved lessons are reused."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from serviceos_api.application.agent_services import AgentContextBuilder
from serviceos_api.application.contracts import ExperienceContent, ExperienceDecision
from serviceos_api.application.experience import _request_hash
from serviceos_api.bootstrap_local import seed_local_accounts
from serviceos_api.main import create_app
from serviceos_api.persistence.models import DevicePassport, ExperienceCandidate, ExperienceReview
from serviceos_api.settings import Settings
from test_business_api import login
from test_mock_service_actions import approve, defer_other_actions, request_action, verification_body
from serviceos_api.worker.actions import MockActionWorker


def test_experience_content_normalizes_models_and_rejects_duplicates():
    content = ExperienceContent(
        title="检查供电端",
        issue_type="no-charge",
        applicable_models=[" a3134 "],
        symptoms=["无法充电"],
        steps=["检查线材"],
        success_criteria="客户确认恢复正常",
        failure_exit="型号不匹配时停止并交由客服核查",
    )
    assert content.applicable_models == ["A3134"]
    with pytest.raises(ValueError):
        ExperienceContent(
            title="检查供电端",
            issue_type="no-charge",
            applicable_models=["A3134", " a3134 "],
            symptoms=["无法充电"],
            steps=["检查线材"],
            success_criteria="客户确认恢复正常",
            failure_exit="型号不匹配时停止并交由客服核查",
        )
    with pytest.raises(ValueError):
        ExperienceContent(
            title="   ",
            issue_type="no-charge",
            applicable_models=["A3134"],
            symptoms=["无法充电"],
            steps=["检查线材"],
            success_criteria="客户确认恢复正常",
            failure_exit="型号不匹配时停止并交由客服核查",
        )


def test_experience_review_hash_is_stable_across_idempotency_keys():
    common = {
        "expected_version": 3,
        "decision": "APPROVED",
        "reason": "复核适用范围后批准。",
    }
    first = ExperienceDecision(decision_id=uuid4(), **common)
    replay = ExperienceDecision(decision_id=uuid4(), **common)
    changed = ExperienceDecision(decision_id=uuid4(), **{**common, "reason": "其他理由"})
    assert _request_hash(first) == _request_hash(replay)
    assert _request_hash(first) != _request_hash(changed)


@pytest.fixture
def app(database_engine):
    with Session(database_engine) as session:
        seed_local_accounts(session)
    return create_app(database_engine=database_engine, settings=Settings(
        environment="test", auth_mode="local", local_password="test-only-password",
    ))


def test_verified_case_candidate_review_and_runtime_retrieval(app, database_engine):
    customer = login(app)
    other_customer = login(app, "other-tenant")
    staff = login(app, "staff")
    supervisor = login(app, "supervisor")
    device = customer.post("/api/v1/devices", json={"model": "A3134"}).json()
    case = customer.post("/api/v1/cases", json={"problem_text": "A3134 无法充电"}).json()
    linked_device = customer.post(f"/api/v1/cases/{case['id']}/devices", json={
        "device_id": device["id"], "expected_version": case["version"],
    })
    assert linked_device.status_code == 200, linked_device.text
    with Session(database_engine) as session:
        passport = session.get(DevicePassport, UUID(device["id"]))
        passport.identity_status = "VERIFIED"
        passport.verified_by = "客服核验"
        passport.verified_at = datetime.now(timezone.utc)
        session.commit()

    conversation = customer.post("/api/v1/conversations", json={}).json()
    case = linked_device.json()
    attached = customer.post(f"/api/v1/cases/{case['id']}/conversations", json={
        "conversation_id": conversation["id"], "expected_version": case["version"],
    })
    assert attached.status_code == 200, attached.text
    message = customer.post(f"/api/v1/conversations/{conversation['id']}/messages", json={
        "client_message_id": str(uuid4()), "related_case_id": case["id"],
        "content": [{"type": "text", "text": "A3134 无法充电"}],
    })
    assert message.status_code == 202, message.text
    message_id = message.json()["message"]["id"]

    case = customer.get(f"/api/v1/cases/{case['id']}").json()
    action = request_action(staff, case, version=case["version"]).json()
    assert approve(supervisor, action["approval_id"]).status_code == 200
    action_id = UUID(action["id"])
    defer_other_actions(database_engine, action_id)
    assert MockActionWorker(database_engine, app.state.settings).run_once()
    path = f"/api/v1/cases/{case['id']}"
    current = customer.get(path).json()
    contract = customer.get(path + "/resolution-contract").json()
    verification = verification_body(current["version"], contract_version=contract["version"])
    recorded = customer.post(path + "/verifications", json=verification)
    assert recorded.status_code == 201 and recorded.json()["decision"] == "VERIFIED_RESOLVED"
    assert customer.post(path + "/verifications", json=verification).json() == recorded.json()

    candidates_url = "/api/v1/experience-candidates"
    assert customer.get(candidates_url).status_code == 403
    # The staff gate is on the actor kind, so another tenant's customer is refused the same way
    # rather than served an empty page.
    assert other_customer.get(candidates_url).status_code == 403
    candidates = staff.get(candidates_url + "?status=DRAFT").json()["items"]
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["source_case_id"] == case["id"]
    assert candidate["source_verification_id"] == recorded.json()["id"]
    assert candidate["content"] is None
    # Same actor kind, same gate as the list: the refusal is about the role, so it does not
    # depend on which candidate id is asked for.
    assert other_customer.get(f"{candidates_url}/{candidate['id']}").status_code == 403

    content = {
        "title": "A3134 不充电：先核对供电端与线材",
        "issue_type": "no-charge",
        "applicable_models": ["a3134"],
        "symptoms": ["无法充电", "不充电"],
        "required_evidence": ["确认电源与线材规格"],
        "steps": ["检查电源和线材", "观察设备指示状态"],
        "success_criteria": "客户确认设备恢复正常，且满足当前案例核验条件。",
        "failure_exit": "型号或证据不匹配时停止套用并交由客服核查。",
    }
    submitted = staff.patch(f"{candidates_url}/{candidate['id']}", json={
        "expected_version": candidate["version"], "content": content, "submit_for_review": True,
    })
    assert submitted.status_code == 200, submitted.text
    candidate = submitted.json()
    self_approval = staff.post(f"{candidates_url}/{candidate['id']}/decisions", json={
        "decision_id": str(uuid4()), "expected_version": candidate["version"],
        "decision": "APPROVED", "reason": "同一人不应自审",
    })
    assert self_approval.status_code == 403
    decision = {
        "decision_id": str(uuid4()), "expected_version": candidate["version"],
        "decision": "APPROVED", "reason": "复核来源核验和适用型号后批准。",
    }
    approved = supervisor.post(f"{candidates_url}/{candidate['id']}/decisions", json=decision)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert supervisor.post(f"{candidates_url}/{candidate['id']}/decisions", json=decision).json() == approved.json()
    assert len(supervisor.get(f"{candidates_url}/{candidate['id']}/reviews").json()["items"]) == 1
    with Session(database_engine) as session:
        assert session.scalar(select(ExperienceCandidate.status).where(
            ExperienceCandidate.id == UUID(candidate["id"]))) == "APPROVED"
        assert session.scalar(select(ExperienceReview.decision).where(
            ExperienceReview.candidate_id == UUID(candidate["id"]))) == "APPROVED"

    actor = customer.get("/api/v1/auth/me").json()
    with Session(database_engine) as session:
        context = AgentContextBuilder(session, UUID(actor["tenant_id"])).build(
            UUID(conversation["id"]), UUID(message_id))
        assert len(context["experience_examples"]) == 1
        assert context["experience_examples"][0]["candidate_id"] == candidate["id"]
        assert context["experience_examples"][0]["source_verification_id"] == recorded.json()["id"]
        assert context["experience_examples"][0]["candidate_version"] == approved.json()["version"]
        assert "VERIFIED" not in context["experience_examples"][0]

    # Reopening the source Case invalidates its experience for retrieval.
    resolved_case = customer.get(path).json()
    reopened = staff.post(f"/api/v1/cases/{case['id']}/transitions", json={
        "expected_version": resolved_case["version"], "target_status": "IN_PROGRESS",
        "reason": "同一问题再次出现，重新处理。",
    })
    assert reopened.status_code == 200, reopened.text
    with Session(database_engine) as session:
        context = AgentContextBuilder(session, UUID(actor["tenant_id"])).build(
            UUID(conversation["id"]), UUID(message_id))
        assert context["experience_examples"] == []

    # A later successful resolution must not reactivate the older approved lesson.
    reopened_case = reopened.json()
    second_action = request_action(staff, reopened_case, version=reopened_case["version"]).json()
    assert approve(supervisor, second_action["approval_id"]).status_code == 200
    defer_other_actions(database_engine, UUID(second_action["id"]))
    assert MockActionWorker(database_engine, app.state.settings).run_once()
    current = customer.get(path).json()
    new_contract = customer.get(path + "/resolution-contract").json()
    second_verification = customer.post(path + "/verifications", json=verification_body(
        current["version"], contract_version=new_contract["version"],
    ))
    assert second_verification.status_code == 201
    assert second_verification.json()["decision"] == "VERIFIED_RESOLVED"
    with Session(database_engine) as session:
        context = AgentContextBuilder(session, UUID(actor["tenant_id"])).build(
            UUID(conversation["id"]), UUID(message_id))
        assert context["experience_examples"] == []


def test_unresolved_verification_does_not_seed_experience_candidate(app, database_engine):
    customer = login(app)
    staff = login(app, "staff")
    supervisor = login(app, "supervisor")
    case = customer.post("/api/v1/cases", json={"problem_text": "待核验问题"}).json()
    action = request_action(staff, case, version=case["version"]).json()
    assert approve(supervisor, action["approval_id"]).status_code == 200
    action_id = UUID(action["id"])
    defer_other_actions(database_engine, action_id)
    assert MockActionWorker(database_engine, app.state.settings).run_once()
    current = customer.get(f"/api/v1/cases/{case['id']}").json()
    contract = customer.get(f"/api/v1/cases/{case['id']}/resolution-contract").json()
    body = verification_body(current["version"], result="UNCERTAIN", contract_version=contract["version"])
    result = customer.post(f"/api/v1/cases/{case['id']}/verifications", json=body)
    assert result.status_code == 201 and result.json()["decision"] == "PENDING"
    # Scope to this case: the shared test database also holds candidates from the other tests
    # in this module, and this assertion is about what this UNCERTAIN verification seeded.
    listed = login(app, "supervisor").get("/api/v1/experience-candidates").json()["items"]
    assert all(item["source_case_id"] != case["id"] for item in listed)
