"""Manual backend-only real-provider probe for the Agent -> approval -> Mock flow.

Run only against the disposable local PostgreSQL on 127.0.0.1:55433 after migrations,
local account seeding, checkpoint setup, and knowledge ingestion. This script invokes
the real FastAPI routes, MessageWorker/AgentRuntime, approval service, and MockActionWorker.
It never calls an Anker service; the only service action is explicitly MOCK.
"""

from __future__ import annotations

import json
import os
import time
from uuid import uuid4

from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url

from serviceos_api.bootstrap_local import seed_local_accounts
from serviceos_api.main import create_app
from serviceos_api.persistence.database import build_engine, configured_database_url
from serviceos_api.persistence.models import AgentRun, CaseAction, Message, PublicationGuardDecision
from serviceos_api.settings import Settings
from serviceos_api.worker.actions import MockActionWorker
from serviceos_api.worker.runtime import MessageWorker


SCENARIO = (
    "Product Name: Omni E25; Problem Code: 3212 - The mop is stuck. "
    "I tried the suggested cleaning, but no blockage is visible. A repeated cracking "
    "sound happens after mop cleaning and the vacuum cannot start. "
    "Please open a repair request for me."
)


def require_probe_environment(settings: Settings) -> None:
    if os.getenv("SERVICEOS_LIVE_AGENT_PROBE") != "1":
        raise SystemExit("Set SERVICEOS_LIVE_AGENT_PROBE=1 to run this manual probe.")
    if settings.environment not in ("development", "test") or not settings.local_auth_enabled:
        raise SystemExit("The probe requires development/test environment and local auth.")
    if not settings.llm_configured:
        raise SystemExit("The probe requires an explicitly configured local LLM provider.")
    url = make_url(configured_database_url())
    if url.host not in ("127.0.0.1", "localhost") or url.port != 55433 or url.database != "serviceos_dev":
        raise SystemExit("Refusing to run outside the disposable local database at 127.0.0.1:55433/serviceos_dev.")


def login(client: TestClient, username: str, password: str) -> None:
    response = client.post("/api/v1/local-auth/login", json={"username": username, "password": password})
    if response.status_code != 200:
        raise RuntimeError(f"local login failed for {username}: HTTP {response.status_code}")


def require_status(response, expected: int, label: str) -> dict:
    if response.status_code != expected:
        raise RuntimeError(f"{label} returned HTTP {response.status_code}: {response.text[:500]}")
    return response.json() if response.content else {}


def main() -> None:
    os.environ.setdefault("SERVICEOS_ENV", "test")
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=False)
    settings = Settings.from_environment()
    require_probe_environment(settings)
    engine = build_engine()
    try:
        with Session(engine) as session:
            seed_local_accounts(session)

        app = create_app(database_engine=engine, settings=settings)
        result: dict[str, object] = {
            "scenario_source": "data/reference/hackathon/黑客松智能服务赛题资料.xlsx, complaints sheet row 28",
            "scenario_redacted": "E25 / error 3212 mop blockage; cleaning attempted; repeated cracking; will not start; customer explicitly requests repair",
            "adapter": "MOCK",
            "environment": settings.environment,
        }
        with TestClient(app) as customer, TestClient(app) as supervisor:
            login(customer, "customer-a", settings.local_password)
            login(supervisor, "supervisor", settings.local_password)

            case = require_status(customer.post("/api/v1/cases", json={
                "problem_text": SCENARIO,
                "user_goal": "客户请求提交维修服务申请",
            }), 201, "create case")
            conversation = require_status(customer.post("/api/v1/conversations", json={}), 201,
                                          "create conversation")
            linked = require_status(customer.post(f"/api/v1/cases/{case['id']}/conversations", json={
                "conversation_id": conversation["id"], "expected_version": case["version"],
            }), 200, "link case and conversation")

            message_started = time.perf_counter()
            intake = require_status(customer.post(f"/api/v1/conversations/{conversation['id']}/messages", json={
                "client_message_id": str(uuid4()),
                "related_case_id": case["id"],
                "visibility": "PUBLIC",
                "content": [{"type": "text", "text": SCENARIO}],
            }), 202, "accept customer message")
            result["http_accept_ms"] = round((time.perf_counter() - message_started) * 1000, 2)
            result["case_id"] = case["id"]
            result["conversation_id"] = conversation["id"]
            result["customer_message_id"] = intake["message"]["id"]
            result["case_version_after_link"] = linked["version"]

            agent_started = time.perf_counter()
            if not MessageWorker(engine, settings).run_once():
                raise RuntimeError("Agent Worker did not claim the newly accepted customer message.")
            result["agent_worker_ms"] = round((time.perf_counter() - agent_started) * 1000, 2)

            with Session(engine) as session:
                run = session.scalar(select(AgentRun).where(AgentRun.message_id == intake["message"]["id"]))
                result["agent_run_id"] = str(run.id) if run else None
                result["agent_run_status"] = run.status if run else None
                result["agent_error_code"] = run.error_code if run else None
                result["agent_step_count"] = run.step_count if run else None

            messages = require_status(customer.get(
                f"/api/v1/conversations/{conversation['id']}/messages"), 200, "read conversation messages")
            public_agent_messages = [item for item in messages["items"]
                                     if item["author_kind"] == "AGENT" and item["visibility"] == "PUBLIC"]
            result["public_agent_message_count"] = len(public_agent_messages)
            with Session(engine) as session:
                stored_agent_messages = session.scalars(select(Message).where(
                    Message.conversation_id == conversation["id"], Message.author_kind == "AGENT")).all()
                result["internal_agent_message_count"] = sum(
                    message.visibility == "INTERNAL" for message in stored_agent_messages)
                stored_reply_text = [part.get("text", "") for message in stored_agent_messages
                                     for part in message.content if part.get("type") == "text"]
            result["agent_reply_contains_pending_approval"] = any(
                word in text for text in stored_reply_text for word in ("待审批", "等待审批", "主管审批")
            )
            with Session(engine) as session:
                guard_rows = session.scalars(select(PublicationGuardDecision).where(
                    PublicationGuardDecision.conversation_id == conversation["id"])).all()
                result["publication_guard"] = [{
                    "decision": row.decision,
                    "reason_codes": row.reason_codes,
                    "verifier_status": (row.verifier or {}).get("status"),
                    "unaddressed_request_count": len((row.verifier or {}).get("unaddressed", [])),
                    "ungrounded_promise_count": len((row.verifier or {}).get("promises", [])),
                } for row in guard_rows]

            actions = require_status(customer.get(f"/api/v1/cases/{case['id']}/actions"), 200,
                                     "read case actions")
            if not actions:
                result["agent_action_created"] = False
                print(json.dumps(result, ensure_ascii=False, indent=2))
                raise RuntimeError("Agent completed without creating the explicitly requested Mock repair action.")
            action = actions[0]
            result["action_id"] = action["id"]
            result["approval_id"] = action["approval_id"]
            result["action_status_before_approval"] = action["status"]
            result["action_adapter"] = action["adapter"]
            with Session(engine) as session:
                persisted_action = session.get(CaseAction, action["id"])
                result["agent_action_created"] = bool(
                    run and persisted_action
                    and persisted_action.requested_by_agent_run_id == run.id
                    and persisted_action.requested_by is None
                )
            if action["status"] != "WAITING_APPROVAL" or action["adapter"] != "MOCK":
                raise RuntimeError("Agent action was not safely persisted as WAITING_APPROVAL with MOCK adapter.")

            approval = require_status(supervisor.get(
                f"/api/v1/cases/{case['id']}/approvals"), 200, "read approvals")[0]
            decision = require_status(supervisor.post(f"/api/v1/approvals/{approval['id']}/decisions", json={
                "decision_id": str(uuid4()), "expected_version": approval["version"],
                "decision": "APPROVED", "reason": "演示联调：主管核对后批准模拟维修申请",
            }), 200, "supervisor approval")
            result["approval_status"] = decision["status"]
            result["action_worker_claimed"] = MockActionWorker(engine, settings).run_once()

            completed_action = require_status(customer.get(f"/api/v1/actions/{action['id']}"), 200,
                                              "read action receipt")
            result["action_status_after_worker"] = completed_action["status"]
            result["receipt_adapter"] = completed_action["receipt"]["adapter"] if completed_action["receipt"] else None
            result["receipt_result"] = completed_action["receipt"]["result"] if completed_action["receipt"] else None

            contract = require_status(customer.get(
                f"/api/v1/cases/{case['id']}/resolution-contract"), 200, "read resolution contract")
            latest_case = require_status(customer.get(f"/api/v1/cases/{case['id']}"), 200, "read case before verification")
            verification = require_status(customer.post(f"/api/v1/cases/{case['id']}/verifications", json={
                "client_verification_id": str(uuid4()),
                "expected_case_version": latest_case["version"],
                "expected_resolution_contract_version": contract["version"],
                "observed_result": "WORKING", "evidence_ids": [],
                "note": "演示联调：客户在模拟处理后确认问题已解决",
            }), 201, "customer verification")
            final_case = require_status(customer.get(f"/api/v1/cases/{case['id']}"), 200, "read resolved case")
            result["resolution_contract_conditions"] = contract["conditions"]
            result["verification_id"] = verification["id"]
            result["verification_result"] = verification["observed_result"]
            result["final_case_status"] = final_case["status"]

            if (result["agent_run_status"] != "COMPLETED" or not result["agent_action_created"]
                    or result["approval_status"] != "APPROVED"
                    or result["action_status_after_worker"] != "SUCCEEDED"
                    or result["receipt_adapter"] != "MOCK"
                    or result["final_case_status"] != "RESOLVED"):
                raise RuntimeError("The end-to-end business chain did not reach its expected audited terminal state.")

        result["customer_update_published"] = result["public_agent_message_count"] > 0
        result["probe_passed"] = bool(
            result["customer_update_published"] and result["agent_reply_contains_pending_approval"]
        )
        print(json.dumps(result, ensure_ascii=True, indent=2))
        if not result["probe_passed"]:
            raise RuntimeError(
                "The business action chain completed, but no public Agent reply accurately reported pending approval."
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
