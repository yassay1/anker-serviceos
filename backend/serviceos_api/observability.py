import json
import logging
import time
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse


class SafeJsonFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event_code", "application.log"),
        }
        for key in (
            "request_id", "method", "route", "status_code", "duration_ms", "error_code", "exception_type",
            "exception_symbol",
            "active_connections", "poll_count", "empty_poll_count", "event_count", "total_query_ms",
            "max_event_age_ms", "close_reason", "event_type", "outbox_delay_ms",
        ):
            value = getattr(record, key, None)
            if value is not None:
                entry[key] = value
        return json.dumps(entry, ensure_ascii=False, separators=(",", ":"))


def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(SafeJsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True


async def observe_request(request: Request, call_next):
    request_id = str(uuid4())
    started = time.perf_counter()
    error_code = None
    try:
        response = await call_next(request)
    except Exception as error:
        error_code = "unhandled_error"
        logging.getLogger("serviceos.http").error("", extra={
            "event_code": "http.unhandled_error", "request_id": request_id,
            "method": request.method, "route": getattr(request.scope.get("route"), "path", "unmatched"),
            "error_code": error_code, "exception_type": type(error).__name__,
        })
        response = JSONResponse(status_code=500, content={"detail": "服务暂时不可用，请稍后重试。", "request_id": request_id})
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers["Server-Timing"] = f"app;dur={duration_ms}"
    route = getattr(request.scope.get("route"), "path", "unmatched")
    logging.getLogger("serviceos.http").info("", extra={
        "event_code": "http.completed", "request_id": request_id,
        "method": request.method, "route": route,
        "status_code": response.status_code, "duration_ms": duration_ms,
        "error_code": error_code,
    })
    return response
