"""Explicit setup command for the isolated LangGraph checkpoint schema."""

from serviceos_api.agents.runtime import setup_checkpoint_schema


if __name__ == "__main__":
    setup_checkpoint_schema()
    print("LangGraph checkpoint schema initialized.")
