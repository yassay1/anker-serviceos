import argparse
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from serviceos_api.application.auth import Principal
from serviceos_api.application.contracts import AttachConversation, AttachDevice, CreateCase, CreateConversation, CreateDevice, SendMessage
from serviceos_api.application.business import BusinessService
from serviceos_api.application.services import ConversationService
from serviceos_api.bootstrap_local import seed_local_accounts
from serviceos_api.integrations.local_evidence_storage import evidence_storage_from_settings
from serviceos_api.persistence.database import build_engine
from serviceos_api.persistence.models import CaseImageEvidence, Conversation, Customer, DevicePassport, ServiceCase, Tenant
from serviceos_api.settings import Settings

DEMO_NAME = re.compile(r"serviceos_demo_[a-z0-9_]{1,32}\Z")
MARKER = "serviceos-owned-demo-v1"


def require_demo_target(url, settings: Settings, name: str):
    hosts = ("127.0.0.1", "localhost") + (("postgres",) if settings.allow_container_bootstrap else ())
    if not settings.local_auth_enabled or url.host not in hosts or not DEMO_NAME.fullmatch(name):
        raise ValueError("Demo operations require explicit local authentication and a serviceos_demo_* database.")
    if settings.evidence_storage_backend != "local":
        raise ValueError("Demo cleanup cannot target cloud evidence storage.")


def seed_scenario(engine) -> dict:
    with Session(engine, expire_on_commit=False) as session:
        seed_local_accounts(session)
        tenant = session.scalar(select(Tenant).where(Tenant.slug == "local-demo-a"))
        customer = session.scalar(select(Customer).where(Customer.tenant_id == tenant.id, Customer.external_subject == "local:customer-a"))
        actor = Principal(tenant.id, customer.id, "CUSTOMER", customer.display_name)
        service = BusinessService(session, actor)
        case = service.create(ServiceCase, CreateCase(problem_text="【本地演示】充电宝连接后无法充电，待确认型号与接口。", user_goal="完成安全排查，必要时模拟提交服务申请。"))
        conversation = service.create(Conversation, CreateConversation())
        device = service.create(DevicePassport, CreateDevice(model="A1229（演示用户陈述，未核验）"))
        case = service.attach(case.id, AttachConversation(conversation_id=conversation.id, expected_version=case.version), Conversation)
        service.attach(case.id, AttachDevice(device_id=device.id, expected_version=case.version, role="AFFECTED", is_primary=True), DevicePassport)
        ConversationService(session, actor).send_message(conversation.id, SendMessage(
            client_message_id=uuid4(), content=[{"type": "text", "text": "【本地演示数据】连接充电器后没有变化，请先帮我确认应补充哪些信息。"}],
            visibility="PUBLIC", related_case_id=case.id))
        return {"conversation_id": str(conversation.id), "case_id": str(case.id), "device_id": str(device.id)}


def initialize_demo(source_engine, settings: Settings, name: str) -> dict:
    require_demo_target(source_engine.url, settings, name)
    admin = create_engine(source_engine.url.set(database="postgres"), isolation_level="AUTOCOMMIT", hide_parameters=True)
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        admin.dispose()
    engine = build_engine(source_engine.url.set(database=name).render_as_string(hide_password=False))
    try:
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        config.attributes["database_url"] = engine.url.render_as_string(hide_password=False)
        command.upgrade(config, "head")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE public.serviceos_demo_marker (value text PRIMARY KEY)"))
            connection.execute(text("INSERT INTO public.serviceos_demo_marker(value) VALUES (:marker)"), {"marker": MARKER})
        return {"database": name, **seed_scenario(engine)}
    finally:
        engine.dispose()


def cleanup_demo(source_engine, settings: Settings, name: str, confirmation: str | None) -> dict:
    require_demo_target(source_engine.url, settings, name)
    if source_engine.url.database == name:
        raise ValueError("Point the maintenance connection at a different database before cleanup.")
    engine = build_engine(source_engine.url.set(database=name).render_as_string(hide_password=False))
    try:
        with engine.connect() as connection:
            marker = connection.execute(text("SELECT value FROM public.serviceos_demo_marker")).scalar_one()
            if marker != MARKER:
                raise ValueError("Database is not marked as an owned demo.")
            active = connection.execute(text("SELECT count(*) FROM pg_stat_activity WHERE datname=:name AND pid<>pg_backend_pid()"), {"name": name}).scalar_one()
            if active:
                raise ValueError("Stop all clients and workers before demo cleanup; no processes will be terminated.")
            keys = list(connection.execute(select(CaseImageEvidence.storage_key).where(CaseImageEvidence.storage_key.is_not(None))).scalars())
        if confirmation != name:
            return {"database": name, "evidence_objects": len(keys), "dry_run": True}
        storage = evidence_storage_from_settings(settings)
        for key in keys:
            storage.delete(key)
    finally:
        engine.dispose()
    admin = create_engine(source_engine.url.set(database="postgres"), isolation_level="AUTOCOMMIT", hide_parameters=True)
    try:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}"'))
    finally:
        admin.dispose()
    return {"database": name, "deleted": True}


def summarize_metrics(path: Path) -> dict:
    timings = defaultdict(list)
    requests = errors = 0
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                record = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(record, dict):
                continue
            if record.get("event") == "http.completed":
                requests += 1
                errors += int(isinstance(record.get("status_code"), int) and record["status_code"] >= 500)
                duration = record.get("duration_ms")
                if isinstance(duration, (float, int)) and math.isfinite(duration) and 0 <= duration and len(timings["http_request_ms"]) < 100000:
                    timings["http_request_ms"].append(duration)
                    if record.get("method") == "POST" and record.get("route", "").endswith("/messages"):
                        timings["http_accept_ms"].append(duration)
    result = {}
    for key, values in timings.items():
        values.sort()
        if values:
            result[key] = {"samples": len(values), "p50": values[math.ceil(len(values) * .5) - 1], "p95": values[math.ceil(len(values) * .95) - 1]}
    return {"metrics": result, "requests": requests, "error_rate": errors / requests if requests else None,
            "unmeasured": ["queue_delay_ms", "agent_first_progress_ms", "model_ttft_ms", "tool_latency_ms", "ui_action_completion_ms"]}


def main():
    parser = argparse.ArgumentParser(description="Guarded local demo lifecycle and sanitized metric summaries.")
    sub = parser.add_subparsers(dest="operation", required=True)
    for name in ("init", "reset"):
        sub.add_parser(name).add_argument("--name")
    clean = sub.add_parser("clean")
    clean.add_argument("--name", required=True)
    clean.add_argument("--confirm")
    sub.add_parser("metrics").add_argument("--log", required=True)
    args = parser.parse_args()
    if args.operation == "metrics":
        print(json.dumps(summarize_metrics(Path(args.log)), ensure_ascii=False))
        return
    settings = Settings.from_environment()
    engine = build_engine()
    try:
        if args.operation == "clean":
            result = cleanup_demo(engine, settings, args.name, args.confirm)
        else:
            name = args.name or f"serviceos_demo_{datetime.now(timezone.utc):%Y%m%d}_{uuid4().hex[:8]}"
            result = initialize_demo(engine, settings, name)
            if args.operation == "reset":
                result["previous_data_preserved"] = True
        print(json.dumps(result, ensure_ascii=False))
    except Exception:
        raise SystemExit("Demo operation failed; existing data was not forcibly removed. Check local configuration, target marker and active connections.") from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
