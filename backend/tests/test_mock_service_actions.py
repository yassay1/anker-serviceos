"""The simulated operation is separate from approval and remains auditable after uncertainty."""

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from serviceos_api.application.actions import ServiceActionService
from serviceos_api.application.agent_services import AgentToolService
from serviceos_api.application.auth import Principal
from serviceos_api.application.contracts import ActionApprovalDecision, MockActionRequest
from serviceos_api.application.errors import ServiceError
from serviceos_api.bootstrap_local import seed_local_accounts
from serviceos_api.integrations.mock_service_adapter import MockServiceAdapter
from serviceos_api.main import create_app
from serviceos_api.persistence.models import (
    AgentRun, CaseAction, CaseActionApproval, MockServiceOperation, OutboxEvent, ServiceCase,
)
from serviceos_api.settings import Settings
from serviceos_api.worker.actions import MockActionWorker
from test_business_api import login
from test_worker_runtime import seed_message


@pytest.fixture
def app(database_engine):
    with Session(database_engine) as session:
        seed_local_accounts(session)
    return create_app(database_engine=database_engine, settings=Settings(
        environment="test", auth_mode="local", local_password="test-only-password",
    ))


def case_for(client):
    response = client.post("/api/v1/cases", json={"problem_text": "模拟售后请求场景"})
    assert response.status_code == 201, response.text
    return response.json()


def request_action(client, case, *, key=None, version=None, reason="需要模拟售后服务申请。"):
    return client.post(f"/api/v1/cases/{case['id']}/action-requests", json={
        "client_action_id": str(key or uuid4()),
        "expected_case_version": version if version is not None else case["version"],
        "action_kind": "MOCK_SERVICE_REQUEST", "remedy_type": "REPAIR", "reason": reason,
    })


def defer_other_actions(engine, action_id):
    with Session(engine) as session:
        session.execute(update(CaseAction).where(CaseAction.id != action_id,
                                                CaseAction.status.in_(("APPROVED", "UNKNOWN"))).values(
            available_at=datetime.now(timezone.utc) + timedelta(days=1)))
        session.commit()


def approve(client, approval_id, decision="APPROVED", key=None, version=1):
    return client.post(f"/api/v1/approvals/{approval_id}/decisions", json={
        "decision_id": str(key or uuid4()), "expected_version": version,
        "decision": decision, "reason": "已核对模拟操作条件",
    })


def test_request_approval_receipt_and_replay(app, database_engine):
    customer = login(app)
    staff = login(app, "staff")
    supervisor = login(app, "supervisor")
    case = case_for(customer)
    key = uuid4()
    assert request_action(customer, case, key=key).status_code == 403
    first = request_action(staff, case, key=key)
    assert first.status_code == 202, first.text
    action = first.json()
    assert action["status"] == "WAITING_APPROVAL"
    assert action["adapter"] == "MOCK" and action["receipt"] is None
    assert request_action(staff, case, key=key).json()["id"] == action["id"]
    conflict = request_action(staff, case, key=key, reason="另一项售后请求")
    assert conflict.status_code == 409 and conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    stale = request_action(staff, case, version=case["version"])
    assert stale.status_code == 409 and stale.json()["code"] == "STALE_VERSION"
    assert approve(staff, action["approval_id"]).status_code == 403
    decision_key = uuid4()
    approved = approve(supervisor, action["approval_id"], key=decision_key)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert approve(supervisor, action["approval_id"], key=decision_key).json() == approved.json()
    assert approve(supervisor, action["approval_id"]).status_code == 409
    defer_other_actions(database_engine, UUID(action["id"]))
    worker = MockActionWorker(database_engine, app.state.settings)
    assert worker.run_once()
    assert not worker.run_once()
    visible = customer.get(f"/api/v1/actions/{action['id']}")
    assert visible.status_code == 200
    assert visible.json()["status"] == "SUCCEEDED"
    assert visible.json()["receipt"]["adapter"] == "MOCK"
    assert visible.json()["receipt"]["external_reference"].startswith("MOCK-")
    assert visible.json()["reason"] is None and visible.json()["requested_by"] is None
    assert staff.get(f"/api/v1/actions/{action['id']}").json()["reason"] == "需要模拟售后服务申请。"
    with Session(database_engine) as session:
        assert session.scalar(select(func.count()).select_from(MockServiceOperation).where(
            MockServiceOperation.action_id == UUID(action["id"]))) == 1


def test_agent_request_is_audited_pending_until_supervisor_and_mock_worker(app, database_engine):
    with Session(database_engine) as session:
        tenant, _, conversation, message, job, case = seed_message(session, with_case=True)
        case_id = case.id
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
        tool = AgentToolService(session, tenant.id, conversation.id, run.id, token,
                                settings=Settings(environment="test"))
        result = tool.request_mock_service_action("RESHIP", "客户明确请求补寄，需主管核对缺件情况。")
        assert result.status == "RECORDED"
        payload = result.to_model_value()
        assert payload["status"] == "WAITING_APPROVAL" and payload["adapter"] == "MOCK"
        action_id = UUID(payload["action_id"])
        action = session.get(CaseAction, action_id)
        assert action.case_id == case.id and action.requested_by is None
        assert action.requested_by_agent_run_id == run.id
        assert tool.request_mock_service_action(
            "RESHIP", "客户明确请求补寄，需主管核对缺件情况。",
        ).to_model_value()["action_id"] == str(action_id)
        assert tool.request_mock_service_action("RESHIP", "改写后的第二个请求").status == "REJECTED"
        assert session.scalar(select(func.count()).select_from(CaseAction).where(
            CaseAction.requested_by_agent_run_id == run.id)) == 1
        assert session.scalar(select(func.count()).select_from(MockServiceOperation).where(
            MockServiceOperation.action_id == action_id)) == 0

    supervisor = login(app, "supervisor")
    assert approve(supervisor, payload["approval_id"]).status_code == 200
    defer_other_actions(database_engine, action_id)
    worker = MockActionWorker(database_engine, app.state.settings)
    assert worker.run_once()
    with Session(database_engine) as session:
        action = session.get(CaseAction, action_id)
        assert action.status == "SUCCEEDED" and action.receipt_reference.startswith("MOCK-")
        assert action.requested_by_agent_run_id is not None
        assert session.get(ServiceCase, case_id).status != "RESOLVED"
        assert session.scalar(select(func.count()).select_from(MockServiceOperation).where(
            MockServiceOperation.action_id == action_id)) == 1


@pytest.mark.parametrize("with_case,environment", [(False, "test"), (True, "production")])
def test_agent_mock_request_rejects_missing_case_or_non_demo_environment(
    app, database_engine, with_case, environment,
):
    with Session(database_engine) as session:
        tenant, _, conversation, message, job, case = seed_message(session, with_case=with_case)
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
        service = AgentToolService(session, tenant.id, conversation.id, run.id, token,
                                   settings=Settings(environment=environment))
        result = service.request_mock_service_action("RESHIP", "客户明确请求补寄。")
        assert result.status == "REJECTED"
        assert session.scalar(select(func.count()).select_from(CaseAction).where(
            CaseAction.requested_by_agent_run_id == run.id)) == 0


def test_approval_rejection_and_self_approval_do_not_execute(app, database_engine):
    customer = login(app)
    staff = login(app, "staff")
    supervisor = login(app, "supervisor")
    case = case_for(customer)
    action = request_action(supervisor, case).json()
    assert approve(supervisor, action["approval_id"]).status_code == 403
    rejected = approve(staff, action["approval_id"], "REJECTED")
    assert rejected.status_code == 403  # SUPPORT cannot decide even when rejecting.
    other_case = case_for(customer)
    other_action = request_action(staff, other_case).json()
    assert approve(supervisor, other_action["approval_id"], "REJECTED").status_code == 200
    assert staff.get(f"/api/v1/actions/{other_action['id']}").json()["status"] == "REJECTED"
    with Session(database_engine) as session:
        assert session.scalar(select(func.count()).select_from(MockServiceOperation).where(
            MockServiceOperation.action_id == UUID(other_action["id"]))) == 0


@pytest.mark.parametrize("result", ["SUCCEEDED", "FAILED", "REJECTED"])
def test_terminal_action_receipt_cannot_bypass_result_verification(app, database_engine, result):
    customer = login(app)
    staff = login(app, "staff")
    supervisor = login(app, "supervisor")
    case = case_for(customer)
    action = request_action(staff, case).json()
    decision = "REJECTED" if result == "REJECTED" else "APPROVED"
    assert approve(supervisor, action["approval_id"], decision).status_code == 200
    if result != "REJECTED":
        action_id = UUID(action["id"])
        defer_other_actions(database_engine, action_id)
        settings = replace(app.state.settings, mock_action_result=result)
        assert MockActionWorker(database_engine, settings).run_once()
        assert staff.get(f"/api/v1/actions/{action_id}").json()["status"] == result
    current = staff.get(f"/api/v1/cases/{case['id']}").json()
    progress = staff.post(f"/api/v1/cases/{case['id']}/transitions", json={
        "target_status": "IN_PROGRESS", "expected_version": current["version"], "reason": "开始服务",
    })
    assert progress.status_code == 200, progress.text
    blocked = staff.post(f"/api/v1/cases/{case['id']}/transitions", json={
        "target_status": "RESOLVED", "expected_version": progress.json()["version"], "reason": "回执不等于核验",
    })
    assert blocked.status_code == 409 and blocked.json()["code"] == "VERIFICATION_REQUIRED"
    assert staff.get(f"/api/v1/cases/{case['id']}").json()["status"] == "IN_PROGRESS"


def test_failed_mock_receipt_and_unknown_reconcile_without_second_operation(app, database_engine, caplog, monkeypatch):
    customer = login(app)
    staff = login(app, "staff")
    supervisor = login(app, "supervisor")
    case = case_for(customer)
    action = request_action(staff, case).json()
    assert approve(supervisor, action["approval_id"]).status_code == 200
    action_id = UUID(action["id"])
    defer_other_actions(database_engine, action_id)
    failed_settings = replace(app.state.settings, mock_action_result="FAILED")
    adapter = MockServiceAdapter(database_engine, failed_settings)
    # Capture raw records independently of app and Alembic logging configuration.
    action_logger = logging.getLogger("serviceos.actions")
    monkeypatch.setattr(action_logger, "handlers", [caplog.handler])
    monkeypatch.setattr(action_logger, "disabled", False)
    monkeypatch.setattr(action_logger, "propagate", False)

    class LostResponse:
        def execute(self, tenant_id, current_action_id):
            adapter.execute(tenant_id, current_action_id)
            raise TimeoutError("response lost after mock commit")

        def lookup(self, tenant_id, current_action_id):
            return adapter.lookup(tenant_id, current_action_id)

    worker = MockActionWorker(database_engine, failed_settings, LostResponse())
    assert worker.run_once()
    assert staff.get(f"/api/v1/actions/{action_id}").json()["status"] == "UNKNOWN"
    with Session(database_engine) as session:
        row = session.get(CaseAction, action_id)
        row.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    assert worker.run_once()
    resolved = staff.get(f"/api/v1/actions/{action_id}").json()
    assert resolved["status"] == "FAILED" and resolved["receipt"]["result"] == "FAILED"
    with Session(database_engine) as session:
        assert session.scalar(select(func.count()).select_from(MockServiceOperation).where(
            MockServiceOperation.action_id == action_id)) == 1
        assert session.scalar(select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.type == "action.state_changed", OutboxEvent.data["action_id"].astext == str(action_id))) == 1
    assert "response lost after mock commit" not in caplog.text
    records = [record for record in caplog.records if record.name == "serviceos.actions"]
    assert len(records) == 1 and records[0].exc_info is None
    assert "mock_outcome_unknown" in records[0].getMessage()
    assert records[0].error_code == "mock_outcome_unknown"


def test_expired_execution_without_receipt_stays_unknown_and_case_cannot_resolve(app, database_engine):
    customer = login(app)
    staff = login(app, "staff")
    supervisor = login(app, "supervisor")
    case = case_for(customer)
    action = request_action(staff, case).json()
    assert approve(supervisor, action["approval_id"]).status_code == 200
    action_id = UUID(action["id"])
    defer_other_actions(database_engine, action_id)
    worker = MockActionWorker(database_engine, app.state.settings)
    lease = worker.claim_one()
    assert lease and not lease.reconcile_only
    with Session(database_engine) as session:
        row = session.get(CaseAction, action_id)
        row.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    assert worker.run_once()
    with Session(database_engine) as session:
        row = session.get(CaseAction, action_id)
        assert row.status == "UNKNOWN" and row.receipt_reference is None
        assert session.scalar(select(func.count()).select_from(MockServiceOperation).where(
            MockServiceOperation.action_id == action_id)) == 0
    current = staff.get(f"/api/v1/cases/{case['id']}").json()
    progress = staff.post(f"/api/v1/cases/{case['id']}/transitions", json={
        "target_status": "IN_PROGRESS", "expected_version": current["version"], "reason": "开始服务",
    })
    assert progress.status_code == 200, progress.text
    blocked = staff.post(f"/api/v1/cases/{case['id']}/transitions", json={
        "target_status": "RESOLVED", "expected_version": progress.json()["version"], "reason": "尚未对账",
    })
    assert blocked.status_code == 409 and blocked.json()["code"] == "ACTION_UNSETTLED"


def test_customer_and_tenant_isolation_and_no_production_mock(database_engine, app):
    customer = login(app)
    other_customer = login(app, "customer-b")
    other_tenant = login(app, "other-tenant")
    staff = login(app, "staff")
    case = case_for(customer)
    action = request_action(staff, case).json()
    assert customer.get(f"/api/v1/actions/{action['id']}").status_code == 200
    assert other_customer.get(f"/api/v1/actions/{action['id']}").status_code == 404
    assert other_tenant.get(f"/api/v1/actions/{action['id']}").status_code == 404
    assert customer.get(f"/api/v1/cases/{case['id']}/approvals").status_code == 403
    with pytest.raises(RuntimeError, match="disabled"):
        MockServiceAdapter(database_engine, Settings(environment="production"))


def test_concurrent_case_version_and_mock_adapter_key(database_engine, app):
    customer = login(app)
    first_staff = login(app, "staff")
    second_staff = login(app, "staff")
    supervisor = login(app, "supervisor")
    case = case_for(customer)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda client: request_action(client, case), (first_staff, second_staff)))
    assert sorted(response.status_code for response in outcomes) == [202, 409]
    action = next(response.json() for response in outcomes if response.status_code == 202)
    assert approve(supervisor, action["approval_id"]).status_code == 200
    actor = supervisor.get("/api/v1/auth/me").json()
    adapter = MockServiceAdapter(database_engine, app.state.settings)
    action_id = UUID(action["id"])
    tenant_id = UUID(actor["tenant_id"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(lambda _: adapter.execute(tenant_id, action_id), range(2)))
    assert receipts[0] == receipts[1]
    with Session(database_engine) as session:
        assert session.scalar(select(func.count()).select_from(MockServiceOperation).where(
            MockServiceOperation.action_id == action_id)) == 1


def verification_body(case_version, *, key=None, result="WORKING", contract_version=1, note="客户已测试并确认"):
    return {
        "client_verification_id": str(key or uuid4()),
        "expected_case_version": case_version,
        "expected_resolution_contract_version": contract_version,
        "observed_result": result, "evidence_ids": [], "note": note,
    }


def test_confirmed_mock_receipt_and_customer_observation_resolve_once(app, database_engine):
    customer = login(app)
    staff = login(app, "staff")
    supervisor = login(app, "supervisor")
    other = login(app, "customer-b")
    case = case_for(customer)
    action = request_action(staff, case).json()
    path = f"/api/v1/cases/{case['id']}"
    contract = customer.get(f"{path}/resolution-contract")
    assert contract.status_code == 200
    assert contract.json()["action_id"] == action["id"]
    assert contract.json()["conditions"] == ["模拟服务请求收到成功回执", "客户明确确认问题已解决"]
    assert other.get(f"{path}/resolution-contract").status_code == 404
    assert staff.post(f"{path}/verifications", json=verification_body(2)).status_code == 403
    assert other.post(f"{path}/verifications", json=verification_body(2)).status_code == 404
    assert approve(supervisor, action["approval_id"]).status_code == 200
    action_id = UUID(action["id"])
    defer_other_actions(database_engine, action_id)
    assert MockActionWorker(database_engine, app.state.settings).run_once()
    current = customer.get(path).json()
    stale = customer.post(f"{path}/verifications", json=verification_body(case["version"]))
    assert stale.status_code == 409 and stale.json()["code"] == "STALE_VERSION"
    wrong_contract = customer.post(f"{path}/verifications", json=verification_body(
        current["version"], contract_version=2))
    assert wrong_contract.status_code == 409 and wrong_contract.json()["code"] == "STALE_CONTRACT"
    hidden_evidence = customer.post(f"{path}/verifications", json={
        **verification_body(current["version"]), "evidence_ids": [str(uuid4())],
    })
    assert hidden_evidence.status_code == 404 and hidden_evidence.json()["code"] == "EVIDENCE_NOT_AVAILABLE"
    key = uuid4()
    body = verification_body(current["version"], key=key)
    result = customer.post(f"{path}/verifications", json=body)
    assert result.status_code == 201, result.text
    assert result.json()["decision"] == "VERIFIED_RESOLVED"
    assert result.json()["case_status"] == "RESOLVED"
    assert customer.get(path).json()["status"] == "RESOLVED"
    assert customer.post(f"{path}/verifications", json=body).json() == result.json()
    changed = {**body, "observed_result": "NOT_WORKING"}
    conflict = customer.post(f"{path}/verifications", json=changed)
    assert conflict.status_code == 409 and conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    listed = customer.get(f"{path}/verifications")
    assert listed.status_code == 200 and len(listed.json()) == 1
    assert other.get(f"{path}/verifications").status_code == 404


@pytest.mark.parametrize("action_result", ["APPROVED", "FAILED", "REJECTED", "UNKNOWN"])
def test_receipt_not_successful_never_resolves_case(app, database_engine, action_result):
    customer = login(app)
    staff = login(app, "staff")
    supervisor = login(app, "supervisor")
    case = case_for(customer)
    action = request_action(staff, case).json()
    path = f"/api/v1/cases/{case['id']}"
    decision = "REJECTED" if action_result == "REJECTED" else "APPROVED"
    assert approve(supervisor, action["approval_id"], decision).status_code == 200
    if action_result in ("FAILED", "UNKNOWN"):
        action_id = UUID(action["id"])
        defer_other_actions(database_engine, action_id)
        settings = replace(app.state.settings, mock_action_result="FAILED")
        if action_result == "FAILED":
            assert MockActionWorker(database_engine, settings).run_once()
        else:
            lease = MockActionWorker(database_engine, settings).claim_one()
            assert lease is not None
            with Session(database_engine) as session:
                row = session.get(CaseAction, action_id)
                row.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
                session.commit()
            assert MockActionWorker(database_engine, settings).run_once()
    version = customer.get(path).json()["version"]
    pending = customer.post(f"{path}/verifications", json=verification_body(version))
    assert pending.status_code == 201, pending.text
    assert pending.json()["decision"] == "PENDING"
    assert customer.get(path).json()["status"] != "RESOLVED"
    version = customer.get(path).json()["version"]
    not_working = customer.post(f"{path}/verifications", json=verification_body(
        version, result="NOT_WORKING", note="尝试后仍未恢复"))
    assert not_working.status_code == 201
    assert not_working.json()["decision"] == "NOT_RESOLVED"
    assert customer.get(path).json()["status"] == "IN_PROGRESS"


def test_newer_rejected_action_cannot_use_older_success_receipt(app, database_engine):
    customer = login(app)
    staff = login(app, "staff")
    supervisor = login(app, "supervisor")
    case = case_for(customer)
    first = request_action(staff, case).json()
    assert approve(supervisor, first["approval_id"]).status_code == 200
    defer_other_actions(database_engine, UUID(first["id"]))
    assert MockActionWorker(database_engine, app.state.settings).run_once()
    current = customer.get(f"/api/v1/cases/{case['id']}").json()
    second = request_action(staff, current).json()
    assert approve(supervisor, second["approval_id"], "REJECTED").status_code == 200
    path = f"/api/v1/cases/{case['id']}"
    contract = customer.get(f"{path}/resolution-contract").json()
    assert contract["action_id"] == second["id"]
    current = customer.get(path).json()
    observed = customer.post(f"{path}/verifications", json=verification_body(current["version"]))
    assert observed.status_code == 201 and observed.json()["decision"] == "PENDING"
    assert customer.get(path).json()["status"] != "RESOLVED"


@pytest.mark.parametrize("older_status", ["WAITING_APPROVAL", "APPROVED", "EXECUTING", "UNKNOWN"])
def test_latest_success_cannot_resolve_with_older_unsettled_action(app, database_engine, older_status):
    customer = login(app)
    staff = login(app, "staff")
    supervisor = login(app, "supervisor")
    case = case_for(customer)
    older = request_action(staff, case).json()
    older_id = UUID(older["id"])
    if older_status != "WAITING_APPROVAL":
        assert approve(supervisor, older["approval_id"]).status_code == 200
    worker = MockActionWorker(database_engine, app.state.settings)
    if older_status in ("EXECUTING", "UNKNOWN"):
        defer_other_actions(database_engine, older_id)
        lease = worker.claim_one()
        assert lease and lease.action_id == older_id
        if older_status == "UNKNOWN":
            worker._finish(lease, None)
    path = f"/api/v1/cases/{case['id']}"
    latest = request_action(staff, customer.get(path).json()).json()
    assert approve(supervisor, latest["approval_id"]).status_code == 200
    defer_other_actions(database_engine, UUID(latest["id"]))
    assert worker.run_once()
    assert customer.get(f"/api/v1/actions/{latest['id']}").json()["status"] == "SUCCEEDED"
    assert customer.get(f"/api/v1/actions/{older_id}").json()["status"] == older_status
    current = customer.get(path).json()
    body = verification_body(current["version"])
    pending = customer.post(f"{path}/verifications", json=body)
    assert pending.status_code == 201, pending.text
    assert pending.json()["decision"] == "PENDING"
    assert customer.get(path).json()["status"] == current["status"]
    assert customer.post(f"{path}/verifications", json=body).json() == pending.json()
    current = customer.get(path).json()
    not_working = customer.post(f"{path}/verifications", json=verification_body(
        current["version"], result="NOT_WORKING"))
    assert not_working.status_code == 201, not_working.text
    assert not_working.json()["decision"] == "NOT_RESOLVED"
    assert customer.get(path).json()["status"] == "IN_PROGRESS"
    with Session(database_engine) as session:
        assert session.get(ServiceCase, UUID(case["id"])).resolved_at is None


def test_unknown_reconciliation_lease_cannot_be_stolen_before_expiry(app, database_engine):
    customer = login(app)
    staff = login(app, "staff")
    supervisor = login(app, "supervisor")
    action = request_action(staff, case_for(customer)).json()
    assert approve(supervisor, action["approval_id"]).status_code == 200
    action_id = UUID(action["id"])
    defer_other_actions(database_engine, action_id)
    adapter = MockServiceAdapter(database_engine, app.state.settings)
    execute_calls = 0

    class LostResponse:
        def execute(self, tenant_id, current_action_id):
            nonlocal execute_calls
            execute_calls += 1
            adapter.execute(tenant_id, current_action_id)
            raise TimeoutError("lost response")

        def lookup(self, tenant_id, current_action_id):
            return adapter.lookup(tenant_id, current_action_id)

    first = MockActionWorker(database_engine, app.state.settings, LostResponse())
    second = MockActionWorker(database_engine, app.state.settings, LostResponse())
    assert first.run_once()
    with Session(database_engine) as session:
        action = session.get(CaseAction, action_id)
        assert action.status == "UNKNOWN" and action.lease_expires_at is None
        action.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    lease = first.claim_one()
    assert lease and lease.action_id == action_id and lease.reconcile_only
    assert second.claim_one() is None
    with Session(database_engine) as session:
        action = session.get(CaseAction, action_id)
        assert action.lease_token == lease.token and action.attempt_count == 2
        action.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
    recovered = second.claim_one()
    assert recovered and recovered.reconcile_only and recovered.token != lease.token
    assert first.claim_one() is None
    first.process(lease)  # A late result from the old owner cannot clear the new lease.
    with Session(database_engine) as session:
        assert session.get(CaseAction, action_id).lease_token == recovered.token
    second.process(recovered)
    assert execute_calls == 1
    with Session(database_engine) as session:
        action = session.get(CaseAction, action_id)
        assert action.status == "SUCCEEDED" and action.lease_token is None
        assert session.scalar(select(func.count()).select_from(MockServiceOperation).where(
            MockServiceOperation.action_id == action_id)) == 1
        assert session.scalar(select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.type == "action.state_changed", OutboxEvent.data["action_id"].astext == str(action_id))) == 1


def principal_for(client):
    me = client.get("/api/v1/auth/me").json()
    return Principal(tenant_id=UUID(me["tenant_id"]), actor_id=UUID(me["actor_id"]),
                     kind=me["kind"], display_name=me["display_name"], role=me["role"])


def test_concurrent_request_replay_and_approval_use_consistent_locks(app, database_engine):
    customer = login(app)
    staff = login(app, "staff")
    supervisor = login(app, "supervisor")
    case = case_for(customer)
    key = uuid4()
    action = request_action(staff, case, key=key).json()
    staff_actor, supervisor_actor = principal_for(staff), principal_for(supervisor)
    barrier = Barrier(2)

    def perform(replay):
        with Session(database_engine) as session:
            session.execute(text("SET LOCAL lock_timeout = '5s'"))
            session.execute(text("SET LOCAL statement_timeout = '10s'"))
            service = ServiceActionService(session, staff_actor if replay else supervisor_actor)
            resource = service.resource

            def synchronized_resource(model, id_, lock=False):
                if model is ServiceCase and lock and not replay:
                    barrier.wait(timeout=5)
                result = resource(model, id_, lock=lock)
                if model is ServiceCase and lock and replay:
                    barrier.wait(timeout=5)
                return result

            service.resource = synchronized_resource
            if replay:
                return service.request(UUID(case["id"]), MockActionRequest(
                    client_action_id=key, expected_case_version=case["version"],
                    action_kind="MOCK_SERVICE_REQUEST", remedy_type="REPAIR",
                    reason="需要模拟售后服务申请。",
                ))
            return service.decide(UUID(action["approval_id"]), ActionApprovalDecision(
                decision_id=uuid4(), expected_version=1, decision="APPROVED", reason="已核对模拟操作条件",
            ))

    with ThreadPoolExecutor(max_workers=2) as pool:
        replay = pool.submit(perform, True)
        approval = pool.submit(perform, False)
        assert replay.result(timeout=15).id == UUID(action["id"])
        assert approval.result(timeout=15).status == "APPROVED"
    with Session(database_engine) as session:
        assert session.get(CaseAction, UUID(action["id"])).status == "APPROVED"
        assert session.scalar(select(func.count()).select_from(CaseAction).where(
            CaseAction.case_id == UUID(case["id"]))) == 1
        assert session.scalar(select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.type == "action.approval_decided",
            OutboxEvent.data["action_id"].astext == action["id"])) == 1


def test_approval_refreshes_preloaded_state_after_another_decision(app, database_engine):
    customer = login(app)
    staff = login(app, "staff")
    supervisor = login(app, "supervisor")
    case = case_for(customer)
    action = request_action(staff, case).json()
    with Session(database_engine, expire_on_commit=False) as session:
        cached_case = session.get(ServiceCase, UUID(case["id"]))
        cached_action = session.get(CaseAction, UUID(action["id"]))
        cached_approval = session.get(CaseActionApproval, UUID(action["approval_id"]))
        assert approve(supervisor, action["approval_id"]).status_code == 200
        service = ServiceActionService(session, principal_for(supervisor))
        with pytest.raises(ServiceError) as caught:
            service.decide(cached_approval.id, ActionApprovalDecision(
                decision_id=uuid4(), expected_version=1, decision="REJECTED", reason="旧页面中的不同决定",
            ))
        assert caught.value.code == "APPROVAL_ALREADY_DECIDED"
        assert cached_case.id == UUID(case["id"])
        assert cached_action.status == "APPROVED" and cached_approval.status == "APPROVED"
    assert staff.get(f"/api/v1/actions/{action['id']}").json()["status"] == "APPROVED"


def test_request_replay_refreshes_preloaded_action_after_approval(app, database_engine):
    customer = login(app)
    staff = login(app, "staff")
    supervisor = login(app, "supervisor")
    case = case_for(customer)
    key = uuid4()
    action = request_action(staff, case, key=key).json()
    with Session(database_engine, expire_on_commit=False) as session:
        cached_action = session.get(CaseAction, UUID(action["id"]))
        assert approve(supervisor, action["approval_id"]).status_code == 200
        replay = ServiceActionService(session, principal_for(staff)).request(UUID(case["id"]), MockActionRequest(
            client_action_id=key, expected_case_version=case["version"],
            action_kind="MOCK_SERVICE_REQUEST", remedy_type="REPAIR", reason="需要模拟售后服务申请。",
        ))
        assert replay.id == cached_action.id and replay.status == "APPROVED"


def test_approval_identity_lookup_is_tenant_scoped(app, database_engine):
    customer = login(app)
    staff = login(app, "staff")
    supervisor = login(app, "supervisor")
    outsider = login(app, "other-tenant")
    action = request_action(staff, case_for(customer)).json()
    actor = replace(principal_for(supervisor), tenant_id=UUID(outsider.get("/api/v1/auth/me").json()["tenant_id"]))
    with Session(database_engine) as session:
        service = ServiceActionService(session, actor)
        with pytest.raises(ServiceError) as caught:
            service.decide(UUID(action["approval_id"]), ActionApprovalDecision(
                decision_id=uuid4(), expected_version=1, decision="APPROVED", reason="其他租户尝试审批",
            ))
        assert caught.value.status == 404
    assert staff.get(f"/api/v1/actions/{action['id']}").json()["status"] == "WAITING_APPROVAL"
