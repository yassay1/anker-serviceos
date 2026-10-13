from fastapi.testclient import TestClient

from serviceos_api.main import create_app
from serviceos_api.settings import Settings


def test_health_contract_and_response_agree():
    with TestClient(create_app(settings=Settings())) as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "serviceos-api", "version": "0.1.0"}
        schema = client.get("/openapi.json").json()
        assert "/api/v1/health" in schema["paths"]
        assert "/api/v1/conversations/{id}/messages" in schema["paths"]
        assert schema["paths"]["/api/v1/health"]["get"]["operationId"] == "read_health"


def test_business_requires_configured_auth_and_agent_is_not_exposed():
    with TestClient(create_app(settings=Settings())) as client:
        for route in ("conversations", "cases", "devices"):
            response = client.post(f"/api/v1/{route}", json={})
            assert response.status_code == 401
        assert client.post("/api/v1/agent-runs", json={}).status_code == 404
        assert client.post("/api/v1/local-auth/login", json={}).status_code == 404
        assert client.post("/api/v1/health").status_code == 405
