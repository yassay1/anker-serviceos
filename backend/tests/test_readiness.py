import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from serviceos_api.main import create_app
from serviceos_api.settings import Settings, environment_secret


def test_readiness_reports_database_and_provider_separately(database_engine):
    settings = Settings(environment="test", auth_mode="local", local_password="test-only")
    with TestClient(create_app(database_engine=database_engine, settings=settings)) as client:
        response = client.get("/api/v1/readiness")
        assert response.status_code == 200
        assert response.json()["components"]["database"] == "ready"
        assert response.json()["components"]["schema"] == "ready"
        assert response.json()["components"]["provider"] == "not_configured"
        assert response.json()["production_ready"] is False


def test_readiness_database_failure_is_safe(monkeypatch):
    monkeypatch.setenv("SERVICEOS_ENV", "production")
    monkeypatch.setenv("SERVICEOS_DATABASE_URL", "postgresql+psycopg://secret-user:secret-password@127.0.0.1:1/private-db")
    with TestClient(create_app(settings=Settings())) as client:
        assert client.get("/api/v1/health").status_code == 200
        response = client.get("/api/v1/readiness")
        assert response.status_code == 503
        assert "secret" not in response.text
        assert "private-db" not in response.text


def test_readiness_rejects_schema_drift(database_engine):
    with database_engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(text("UPDATE serviceos_alembic_version SET version_num='stale_revision'"))
        from serviceos_api.api.health import database_readiness
        assert database_readiness(connection)["schema"] == "outdated"
        transaction.rollback()


def test_production_rejects_local_auth_configuration():
    with pytest.raises(ValueError, match="production"):
        Settings(environment="production", auth_mode="local", local_password="not-for-production")


def test_local_container_network_is_explicit_not_forwarded(database_engine):
    settings = Settings(environment="development", auth_mode="local", local_password="test-only",
                        local_auth_networks=("172.30.85.0/24",))
    app = create_app(database_engine=database_engine, settings=settings)
    with TestClient(app, client=("172.30.85.2", 1234)) as client:
        assert client.get("/api/v1/auth/me").status_code == 401
    with TestClient(app, client=("8.8.8.8", 1234)) as client:
        response = client.get("/api/v1/auth/me", headers={"x-forwarded-for": "127.0.0.1"})
        assert response.status_code == 403


def test_origins_and_secret_files(monkeypatch, tmp_path):
    secret = tmp_path / "secret"
    secret.write_text("private-value\n")
    monkeypatch.setenv("SERVICEOS_LLM_API_KEY_FILE", str(secret))
    monkeypatch.delenv("SERVICEOS_LLM_API_KEY", raising=False)
    assert environment_secret("SERVICEOS_LLM_API_KEY") == "private-value"
    monkeypatch.setenv("SERVICEOS_LLM_API_KEY", "conflicting-value")
    with pytest.raises(ValueError, match="both"):
        environment_secret("SERVICEOS_LLM_API_KEY")
    with pytest.raises(ValueError):
        Settings(allowed_origins=("*",))
    with pytest.raises(ValueError):
        Settings(environment="test", local_auth_networks=("0.0.0.0/0",))


def test_secrets_are_not_in_settings_repr():
    settings = Settings(local_password="secret-local", llm_api_key="secret-key")
    assert "secret-local" not in repr(settings)
    assert "secret-key" not in repr(settings)
