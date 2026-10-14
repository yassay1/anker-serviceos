import importlib
import pkgutil

from fastapi.testclient import TestClient

import serviceos_api.api
from serviceos_api.main import create_app
from serviceos_api.settings import Settings


def test_every_api_router_module_is_mounted_on_the_real_application():
    """A router that only tests mount themselves would be unreachable in production."""
    modules = sorted(module.name for module in pkgutil.iter_modules(serviceos_api.api.__path__))
    assert modules, "no API router modules were discovered"
    with TestClient(create_app(settings=Settings())) as client:
        paths = client.get("/openapi.json").json()["paths"]
    for name in modules:
        router = getattr(importlib.import_module(f"serviceos_api.api.{name}"), "router", None)
        if router is None:
            continue
        for route in router.routes:
            assert route.path in paths, f"serviceos_api.api.{name} is not mounted: {route.path} is missing"


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
