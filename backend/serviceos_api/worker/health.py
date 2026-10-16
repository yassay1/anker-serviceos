import argparse
import logging
import os
import signal
import tempfile
import threading
import time
from pathlib import Path

from serviceos_api.observability import configure_logging

ROLES = ("inspection", "actions", "followups", "outbox", "agent", "knowledge")


def heartbeat_path(role: str) -> Path:
    if role not in ROLES:
        raise ValueError("Unsupported worker role.")
    return Path(tempfile.gettempdir()) / f"serviceos-{role}.heartbeat"


def mark_healthy(role: str) -> None:
    path = heartbeat_path(role)
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(str(time.time()), encoding="ascii")
    os.replace(temporary, path)


def is_healthy(role: str, max_age: float = 120) -> bool:
    try:
        age = time.time() - float(heartbeat_path(role).read_text(encoding="ascii"))
        return 0 <= age <= max_age
    except (OSError, ValueError):
        return False


def run_loop(role: str, operation) -> None:
    configure_logging()
    stop = threading.Event()
    previous = {}
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.signal(sig, lambda *_: stop.set())
    heartbeat_path(role).unlink(missing_ok=True)
    logger = logging.getLogger(f"serviceos.{role}")
    try:
        while not stop.is_set():
            try:
                worked = operation()
                mark_healthy(role)
            except Exception:
                logger.error("", extra={"event_code": "worker.poll_failed", "error_code": "worker_poll_failed"})
                stop.wait(5)
            else:
                if not worked:
                    stop.wait(1)
    finally:
        heartbeat_path(role).unlink(missing_ok=True)
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=ROLES, required=True)
    parser.add_argument("--max-age", type=int, default=120)
    args = parser.parse_args()
    raise SystemExit(0 if is_healthy(args.role, args.max_age) else 1)


if __name__ == "__main__":
    main()
