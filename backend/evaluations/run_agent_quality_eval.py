"""Run the pinned Agent Quality dataset through the real local API and Worker."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import socket
import subprocess
import sys
import time
import uuid
from collections import Counter

import httpx
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATASET = ROOT / "backend" / "evaluations" / "datasets" / "agent-quality-v1.jsonl"
RESULTS_ROOT = ROOT / "backend" / "evaluations" / "results"


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def scrub(text_value: str) -> str:
    value = str(text_value or "")
    for pattern in (
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        r"https?://\S+|www\.\S+",
        r"(?<!\w)\+?\d[\d .()\-/]{6,}\d(?!\w)",
        r"(?<![A-Z0-9])(?=[A-Z0-9-]{6,}(?![A-Z0-9]))(?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{5,}(?![A-Z0-9])",
        r"(?<!\d)\d{5,}(?!\d)",
    ):
        value = re.sub(pattern, "[已脱敏]", value, flags=re.I)
    return value


def load_dataset() -> list[dict]:
    rows = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [row["case_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate_dataset_case_id")
    if any(not row.get("turns") or any(not turn.get("text", "").strip() for turn in row["turns"]) for row in rows):
        raise ValueError("empty_dataset_turn")
    payload = DATASET.read_text(encoding="utf-8")
    pii_patterns = (
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        r"https?://\S+|www\.\S+",
        r"(?<!\d)\d{5,}(?!\d)",
    )
    if any(re.search(pattern, payload, re.I) for pattern in pii_patterns):
        raise ValueError("dataset_pii_scan_failed")
    return rows


def configure_environment(env_file: pathlib.Path, database_override: str | None = None) -> dict:
    values = dotenv_values(env_file)
    for key, value in values.items():
        if key.startswith("SERVICEOS_") and value is not None:
            os.environ.setdefault(key, value)
    required = ("SERVICEOS_LLM_MODEL", "SERVICEOS_LLM_BASE_URL", "SERVICEOS_LLM_API_KEY",
                "SERVICEOS_LOCAL_AUTH_PASSWORD", "SERVICEOS_DATABASE_URL")
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise RuntimeError("required_configuration_missing:" + ",".join(missing))
    # Evaluation uses keyword-only local knowledge retrieval; no embedding request is made.
    # Do not carry a private embedding secret-file path from the source checkout into this worktree.
    for name in ("SERVICEOS_EMBEDDING_API_KEY_FILE", "SERVICEOS_LLM_API_KEY_FILE",
                 "SERVICEOS_LOCAL_AUTH_PASSWORD_FILE"):
        os.environ.pop(name, None)
    os.environ["SERVICEOS_ENV"] = "development"
    os.environ["SERVICEOS_AUTH_MODE"] = "local"
    os.environ["SERVICEOS_PUBLICATION_GUARD"] = "1"
    # Bound repeated paid Provider calls during this dataset run; retry behavior is out of scope.
    os.environ["SERVICEOS_WORKER_MAX_ATTEMPTS"] = "1"
    if database_override:
        os.environ["SERVICEOS_DATABASE_URL"] = database_override
    source_url = make_url(os.environ["SERVICEOS_DATABASE_URL"])
    if source_url.drivername != "postgresql+psycopg" or source_url.host not in ("127.0.0.1", "localhost", "::1"):
        raise RuntimeError("database_target_must_be_local_postgresql")
    llm_url = make_url(os.environ["SERVICEOS_LLM_BASE_URL"])
    return {"model": os.environ["SERVICEOS_LLM_MODEL"], "provider_host": llm_url.host,
            "database_host": source_url.host, "database_port": source_url.port,
            "llm_configured": True}


def create_isolated_database(source_url_text: str) -> tuple[str, str, object]:
    source_url = make_url(source_url_text)
    database_name = "serviceos_agent_eval_" + dt.datetime.now().strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:6]
    admin_url = source_url.set(database="postgres")
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", hide_parameters=True,
                          connect_args={"connect_timeout": 5})
    with admin.connect() as connection:
        exists = connection.execute(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": database_name}).scalar()
        if exists:
            raise RuntimeError("evaluation_database_name_collision")
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    run_url = source_url.set(database=database_name).render_as_string(hide_password=False)
    os.environ["SERVICEOS_DATABASE_URL"] = run_url
    return database_name, run_url, admin


def initialize_database(run_url: str) -> dict:
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    config.attributes["database_url"] = run_url
    command.upgrade(config, "head")
    os.environ["SERVICEOS_DATABASE_URL"] = run_url
    from serviceos_api.agents.runtime import setup_checkpoint_schema
    from serviceos_api.knowledge_ingest import ingest, ingest_policies
    from serviceos_api.persistence.database import build_engine
    from serviceos_api.bootstrap_local import seed_local_accounts

    setup_checkpoint_schema()
    engine = build_engine(run_url)
    try:
        with Session(engine) as session:
            seed_local_accounts(session)
        with Session(engine) as session:
            knowledge = ingest(session)
            policies = ingest_policies(session)
            session.commit()
        with engine.connect() as connection:
            database, host = connection.execute(text("SELECT current_database(), inet_server_addr()::text")).one()
        if database != make_url(run_url).database:
            raise RuntimeError("evaluation_database_identity_mismatch")
        return {"database": database, "server_address": host,
                "knowledge_documents": knowledge["documents"], "knowledge_segments": knowledge["segments"],
                "policy_rows_created": policies["policies_created"]}
    finally:
        engine.dispose()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def db_snapshot(engine, message_id: uuid.UUID, conversation_id: uuid.UUID) -> dict:
    from serviceos_api.persistence.models import AgentProposal, AgentRun, ConversationEvent, MessageJob, SpecialistRun

    with Session(engine) as session:
        job = session.scalar(select(MessageJob).where(MessageJob.message_id == message_id))
        run = session.scalar(select(AgentRun).where(AgentRun.message_id == message_id))
        events = session.scalars(select(ConversationEvent).where(
            ConversationEvent.conversation_id == conversation_id).order_by(ConversationEvent.sequence)).all()
        if job is None:
            return {"job_status": "NOT_FOUND", "agent_run": None, "events": []}
        run_data = None
        if run is not None:
            payload = run.result_payload or {}
            proposals = session.scalars(select(AgentProposal).where(AgentProposal.agent_run_id == run.id)).all()
            specialists = session.scalars(select(SpecialistRun).where(SpecialistRun.parent_agent_run_id == run.id)).all()
            run_data = {"id": str(run.id), "status": run.status, "provider": run.provider, "model": run.model,
                        "started_at": run.started_at.isoformat() if run.started_at else None,
                        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                        "duration_ms": run.duration_ms, "step_count": run.step_count,
                        "input_tokens": run.input_tokens, "output_tokens": run.output_tokens,
                        "error_code": run.error_code,
                        "tool_call_counts": payload.get("tool_call_counts", {}),
                        "execution_termination": payload.get("execution_termination"),
                        "context_metrics": payload.get("context_metrics", {}),
                        "action_proposal_count": len(proposals),
                        "specialist_runs": [{"status": x.status, "duration_ms": x.duration_ms,
                                              "input_tokens": x.input_tokens, "output_tokens": x.output_tokens,
                                              "error_code": x.error_code} for x in specialists]}
        return {"job_status": job.status, "job_attempt_count": job.attempt_count,
                "job_created_at": job.created_at.isoformat() if job.created_at else None,
                "job_completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "job_error_code": job.last_error_code,
                "agent_run": run_data,
                "events": [{"type": x.type, "visibility": x.visibility, "sequence": x.sequence} for x in events]}


def extract_text(message: dict) -> str:
    parts = message.get("content", [])
    return "\n".join(str(part.get("text", "")) for part in parts if isinstance(part, dict) and part.get("text"))


def await_agent(client: httpx.Client, engine, message_id: uuid.UUID, conversation_id: uuid.UUID,
                timeout_seconds: int) -> tuple[dict, list[dict]]:
    deadline = time.monotonic() + timeout_seconds
    last = {}
    while time.monotonic() < deadline:
        last = db_snapshot(engine, message_id, conversation_id)
        if last.get("job_status") in ("COMPLETED", "FAILED", "CANCELLED"):
            break
        time.sleep(1.0)
    else:
        last = {**last, "job_status": "TIMEOUT"}
    public_messages = []
    try:
        response = client.get(f"/api/v1/conversations/{conversation_id}/messages", params={"limit": 100})
        if response.status_code == 200:
            items = response.json().get("items", [])
            public_messages = [item for item in items if item.get("author_kind") in ("AGENT", "SPECIALIST")]
    except httpx.HTTPError:
        pass
    return last, public_messages


def run_turn(client: httpx.Client, engine, conversation_id: uuid.UUID, turn_text: str,
             timeout_seconds: int) -> dict:
    message_id = uuid.uuid4()
    started = time.monotonic()
    started_at = utcnow()
    try:
        response = client.post(f"/api/v1/conversations/{conversation_id}/messages", json={
            "client_message_id": str(uuid.uuid4()),
            "content": [{"type": "text", "text": turn_text}],
            "visibility": "PUBLIC",
        })
        submit_status = response.status_code
        receipt = response.json() if response.status_code == 202 else {}
    except httpx.HTTPError:
        return {"message_id": str(message_id), "submit_status": None, "terminal_state": "HTTP_ERROR",
                "started_at": started_at, "submit_ms": round((time.monotonic() - started) * 1000, 2)}
    if submit_status != 202:
        return {"message_id": str(message_id), "submit_status": submit_status, "terminal_state": "REJECTED",
                "submit_ms": round((time.monotonic() - started) * 1000, 2)}
    accepted_id = receipt.get("message", {}).get("id")
    if accepted_id:
        message_id = uuid.UUID(accepted_id)
    trace, messages = await_agent(client, engine, message_id, conversation_id, timeout_seconds)
    later = [m for m in messages if m.get("created_at", "") >= started_at]
    agent_message = later[-1] if later else None
    answer = scrub(extract_text(agent_message)) if agent_message else None
    return {"message_id": str(message_id), "submit_status": submit_status,
            "processing_state": receipt.get("processing_state"), "submit_ms": round((time.monotonic() - started) * 1000, 2),
            "terminal_state": trace.get("job_status"), "public_reply_visible": bool(agent_message),
            "public_reply_message_id": agent_message.get("id") if agent_message else None,
            "public_reply": answer, "trace": trace}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=False, type=pathlib.Path,
                        help="Existing local backend/.env; values are read silently and never copied to the worktree.")
    parser.add_argument("--timeout-seconds", type=int, default=150)
    parser.add_argument("--repeats", type=int, default=2,
                        help="Additional fresh-conversation runs for three selected multi-turn cases.")
    parser.add_argument("--case-id", action="append", dest="case_ids",
                        help="Run only the named case; may be supplied more than once.")
    parser.add_argument("--worker-log", type=pathlib.Path,
                        help="Optional path for Worker stdout/stderr during a diagnostic run.")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    dataset = load_dataset()
    if args.case_ids:
        requested = set(args.case_ids)
        known = {row["case_id"] for row in dataset}
        if requested - known:
            raise SystemExit("unknown_case_id")
        dataset = [row for row in dataset if row["case_id"] in requested]
    counts = Counter(row["category"] for row in dataset)
    print(json.dumps({"dataset_cases": len(dataset), "multi_turn_cases": sum(len(x["turns"]) > 1 for x in dataset),
                      "category_counts": dict(counts), "dataset_sha256": hashlib.sha256(DATASET.read_bytes()).hexdigest()}))
    if args.validate_only:
        return 0

    if not args.env_file.is_file():
        raise SystemExit("env_file_not_found")
    config_summary = configure_environment(args.env_file)
    database_name, run_url, admin = create_isolated_database(os.environ["SERVICEOS_DATABASE_URL"])
    database_meta = initialize_database(run_url)
    run_stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    result_dir = RESULTS_ROOT / run_stamp
    result_dir.mkdir(parents=True, exist_ok=False)
    result_file = result_dir / "case-results.jsonl"
    meta_file = result_dir / "run-metadata.json"
    engine = create_engine(run_url, pool_pre_ping=True, hide_parameters=True)
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    api = worker = None
    worker_log = None
    meta = {"started_at": utcnow(), "dataset_sha256": hashlib.sha256(DATASET.read_bytes()).hexdigest(),
            "dataset_cases": len(dataset), "repeats": args.repeats, "model": config_summary["model"],
            "provider_host": config_summary["provider_host"], "database": database_name,
            "database_host": config_summary["database_host"], "database_port": config_summary["database_port"],
            "database_setup": database_meta, "api_base": base_url, "timeout_seconds": args.timeout_seconds, "worker_max_attempts_per_message": 1,
            "embedding_enabled": False, "attachments_used": False, "status": "STARTING"}
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    stage = "api_startup"
    try:
        api = subprocess.Popen([sys.executable, "-m", "uvicorn", "serviceos_api.main:app", "--host", "127.0.0.1",
                               "--port", str(port)], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ready_until = time.monotonic() + 45
        while time.monotonic() < ready_until:
            if api.poll() is not None:
                raise RuntimeError("api_process_exited_before_ready")
            try:
                if httpx.get(f"{base_url}/api/v1/health", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        else:
            raise RuntimeError("api_health_timeout")
        if args.worker_log:
            args.worker_log.parent.mkdir(parents=True, exist_ok=True)
            worker_log = args.worker_log.open("w", encoding="utf-8")
        worker = subprocess.Popen([sys.executable, "-m", "serviceos_api.worker.main"], cwd=ROOT, env=env,
                                  stdout=worker_log or subprocess.DEVNULL,
                                  stderr=subprocess.STDOUT if worker_log else subprocess.DEVNULL)
        if worker.poll() is not None:
            raise RuntimeError("agent_worker_exited_on_startup")

        client = httpx.Client(base_url=base_url, timeout=25)
        login = client.post("/api/v1/local-auth/login", json={
            "username": "customer-a", "password": os.environ["SERVICEOS_LOCAL_AUTH_PASSWORD"]})
        if login.status_code != 200:
            raise RuntimeError("local_customer_login_failed")
        stage = "dataset_execution"
        run_plan = [(row, 0) for row in dataset]
        repeat_ids = {"edge-multiturn-troubleshooting", "edge-multiturn-emotion", "edge-multiturn-shipping"}
        for repeat_index in range(1, args.repeats + 1):
            run_plan.extend((row, repeat_index) for row in dataset if row["case_id"] in repeat_ids)

        blocked = False
        with result_file.open("a", encoding="utf-8") as out:
            for case, repeat_index in run_plan:
                if blocked:
                    record = {"case_id": case["case_id"], "repeat_index": repeat_index,
                              "category": case["category"], "status": "NOT_STARTED_PIPELINE_BLOCKED"}
                    out.write(json.dumps(record, ensure_ascii=False) + "\n"); out.flush()
                    continue
                case_started = utcnow()
                create_started = time.monotonic()
                try:
                    response = client.post("/api/v1/conversations", json={})
                    if response.status_code != 201:
                        raise RuntimeError("conversation_create_rejected")
                    conversation_id = uuid.UUID(response.json()["id"])
                    turns=[]
                    for turn_index, turn in enumerate(case["turns"], 1):
                        result = run_turn(client, engine, conversation_id, turn["text"], args.timeout_seconds)
                        result["turn_index"] = turn_index
                        turns.append(result)
                        if result.get("terminal_state") == "TIMEOUT":
                            blocked = True
                            break
                        if worker.poll() is not None:
                            blocked = True
                            break
                        time.sleep(0.5)
                    terminal = "COMPLETED" if turns and all(x.get("terminal_state") == "COMPLETED" for x in turns) else (turns[-1].get("terminal_state", "NO_TURNS") if turns else "FAILED")
                    record = {"case_id": case["case_id"], "repeat_index": repeat_index,
                              "category": case["category"], "conversation_id": str(conversation_id),
                              "started_at": case_started, "setup_ms": round((time.monotonic() - create_started) * 1000, 2),
                              "terminal_state": terminal, "turns": turns}
                except Exception as error:
                    record = {"case_id": case["case_id"], "repeat_index": repeat_index,
                              "category": case["category"], "started_at": case_started,
                              "terminal_state": "HARNESS_ERROR", "error_code": type(error).__name__}
                    if "worker" in str(error).lower() or "api" in str(error).lower():
                        blocked = True
                out.write(json.dumps(record, ensure_ascii=False) + "\n"); out.flush()
                print(json.dumps({"case_id": case["case_id"], "repeat_index": repeat_index,
                                  "terminal_state": record["terminal_state"],
                                  "turns": len(record.get("turns", []))}))
        client.close()
        meta.update({"ended_at": utcnow(), "status": "COMPLETED_WITH_BLOCKED_REMAINDER" if blocked else "COMPLETED",
                     "attempted_runs": sum(1 for _ in result_file.open(encoding="utf-8")),
                     "results_file": str(result_file)})
        return_code = 2 if blocked else 0
    except Exception as error:
        safe_code = str(error) if isinstance(error, RuntimeError) and re.fullmatch(r"[a-z0-9_]+", str(error)) else type(error).__name__
        meta.update({"ended_at": utcnow(), "status": "SETUP_FAILED", "failure_stage": stage, "error_code": safe_code})
        return_code = 2
    finally:
        if worker is not None and worker.poll() is None:
            worker.terminate()
            try: worker.wait(timeout=10)
            except subprocess.TimeoutExpired: worker.kill(); worker.wait(timeout=5)
        if api is not None and api.poll() is None:
            api.terminate()
            try: api.wait(timeout=10)
            except subprocess.TimeoutExpired: api.kill(); api.wait(timeout=5)
        if worker_log is not None:
            worker_log.close()
        engine.dispose()
        meta["ended_at"] = utcnow()
        meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        admin.dispose()
    print(json.dumps({"status": meta["status"], "database": database_name,
                      "results_file": str(result_file), "metadata_file": str(meta_file)}))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
