import json
import logging

from fastapi.testclient import TestClient

from serviceos_api.main import create_app
from serviceos_api.observability import SafeJsonFormatter
from serviceos_api.settings import Settings


def test_json_logs_never_serialize_arbitrary_message_or_exception():
    record = logging.LogRecord("serviceos.http", logging.ERROR, "", 1,
                               "password=secret chat=private serial=ABC", (), None)
    record.event_code = "http.completed"
    record.duration_ms = 10.1
    record.status_code = 503
    record.path = "/api/v1/conversations/private-id?token=secret"
    result = json.loads(SafeJsonFormatter().format(record))
    assert result["event"] == "http.completed"
    assert result["duration_ms"] == 10.1
    assert "secret" not in json.dumps(result)
    assert "private" not in json.dumps(result)
    assert "ABC" not in json.dumps(result)


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
