import asyncio
import json
import logging

from fastapi import Request
from fastapi.testclient import TestClient

from serviceos_api.main import create_app
from serviceos_api.observability import SafeJsonFormatter, observe_request
from serviceos_api.settings import Settings


def test_json_logs_never_serialize_arbitrary_message_or_exception():
    record = logging.LogRecord("serviceos.http", logging.ERROR, "", 1,
                               "password=secret chat=private serial=ABC", (), None)
    record.event_code = "http.completed"
    record.duration_ms = 10.1
    record.status_code = 503
    record.path = "/api/v1/conversations/private-id?token=secret"
    record.exception_type = "RuntimeError"
    result = json.loads(SafeJsonFormatter().format(record))
    assert result["event"] == "http.completed"
    assert result["duration_ms"] == 10.1
    assert result["exception_type"] == "RuntimeError"
    assert "secret" not in json.dumps(result)
    assert "private" not in json.dumps(result)
    assert "ABC" not in json.dumps(result)


def test_unhandled_request_records_safe_exception_type_and_request_id(caplog):
    request = Request({"type": "http", "method": "GET", "path": "/test-crash", "headers": []})

    async def crash(_request):
        raise RuntimeError("secret-key raw user message")

    with caplog.at_level(logging.ERROR, logger="serviceos.http"):
        response = asyncio.run(observe_request(request, crash))

    assert response.status_code == 500
    event = next(record for record in caplog.records if getattr(record, "event_code", None) == "http.unhandled_error")
    assert event.exception_type == "RuntimeError"
    assert event.request_id == response.headers["X-Request-ID"]
    assert "secret-key" not in SafeJsonFormatter().format(event)


def test_http_request_id_is_server_generated_and_errors_are_redacted(caplog):
    app = create_app(settings=Settings())

    @app.get("/test-crash")
    def crash():
        raise RuntimeError("secret-key raw user message")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/test-crash", headers={"x-request-id": "secret-injected"})
        assert response.status_code == 500
        assert "secret" not in response.text
        assert response.headers["x-request-id"] != "secret-injected"
