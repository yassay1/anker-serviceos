import argparse

from serviceos_api.persistence.database import build_engine
from serviceos_api.worker.health import run_loop
from serviceos_api.worker.runtime import OutboxDispatcher

# Single source of truth for the container healthcheck role.
ROLE = "outbox"


def main():
    parser = argparse.ArgumentParser(description="Publish durable conversation events without a model provider.")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    engine = build_engine()
    try:
        dispatcher = OutboxDispatcher(engine)
        if args.once:
            dispatcher.dispatch_batch()
        else:
            run_loop(ROLE, dispatcher.dispatch_batch)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
