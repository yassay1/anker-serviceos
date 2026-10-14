import importlib
import json
import time
from pathlib import Path

import pytest
import yaml
from sqlalchemy.engine import make_url

from serviceos_api.operations import require_demo_target, summarize_metrics
from serviceos_api.settings import Settings
from serviceos_api.worker.health import ROLES, heartbeat_path, is_healthy, mark_healthy


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def worker_roles(compose_name):
    """Map each declared worker service to the role its healthcheck actually polls."""
    compose = yaml.safe_load((REPOSITORY_ROOT / compose_name).read_text(encoding="utf-8"))
    roles = {}
    for name, service in compose.get("services", {}).items():
        modules = [str(part) for part in service.get("command", []) if str(part).startswith("serviceos_api.worker.")]
        if not modules:
            continue
        test = service.get("healthcheck", {}).get("test")
        assert isinstance(test, list) and "serviceos_api.worker.health" in test, \
            f"{compose_name}:{name} runs a worker without a heartbeat healthcheck"
        roles[name] = (modules[0], test[test.index("--role") + 1])
    assert roles, f"{compose_name} declares no worker service"
    return roles


@pytest.mark.parametrize("compose_name", ["compose.yaml", "compose.production.yaml"])
def test_worker_healthchecks_match_the_role_their_module_actually_publishes(compose_name):
    """A container healthcheck is useless if the worker never writes that heartbeat."""
    for name, (module_name, role) in worker_roles(compose_name).items():
        module = importlib.import_module(module_name)
        assert module.ROLE == role, f"{compose_name}:{name} checks role {role} but {module_name} publishes {module.ROLE}"
        assert role in ROLES


def test_local_compose_runs_every_provider_free_worker():
    """The local integration environment must cover the roles that need no model provider."""
    roles = {role for _, role in worker_roles("compose.yaml").values()}
    assert roles == set(ROLES)


def test_demo_target_rejects_production_general_databases_and_remote_hosts():
    local = Settings(environment="test", auth_mode="local", local_password="test")
    require_demo_target(make_url("postgresql+psycopg://a:b@127.0.0.1/serviceos_dev"), local, "serviceos_demo_test")
    for name, host, settings in [("serviceos_dev", "127.0.0.1", local), ("serviceos_demo_test", "db.example.com", local), ("serviceos_demo_test", "127.0.0.1", Settings())]:
        with pytest.raises(ValueError):
            require_demo_target(make_url(f"postgresql+psycopg://a:b@{host}/postgres"), settings, name)


def test_metrics_ignore_raw_text_and_report_unmeasured(tmp_path):
    path = tmp_path / "metrics.jsonl"
    rows = [{"event": "http.completed", "method": "POST", "route": "/api/v1/conversations/{id}/messages", "duration_ms": i, "status_code": 500 if i == 20 else 202} for i in range(1, 21)]
    path.write_text("secret raw text\n" + "\n".join(json.dumps(row) for row in rows))
    result = summarize_metrics(path)
    assert result["metrics"]["http_accept_ms"] == {"samples": 20, "p50": 10, "p95": 19}
    assert result["error_rate"] == .05
    assert "model_ttft_ms" in result["unmeasured"]
    assert "secret" not in json.dumps(result)


def test_worker_health_requires_fresh_successful_poll(monkeypatch, tmp_path):
    monkeypatch.setattr("serviceos_api.worker.health.tempfile.gettempdir", lambda: str(tmp_path))
    assert not is_healthy("outbox")
    mark_healthy("outbox")
    assert is_healthy("outbox")
    heartbeat_path("outbox").write_text(str(time.time() - 999))
    assert not is_healthy("outbox")
    with pytest.raises(ValueError):
        heartbeat_path("../other-file")
