import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker


def configured_database_url() -> str:
    # Keep the product database separate from the legacy prototype's root .env.
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    value = os.getenv("SERVICEOS_DATABASE_URL", "")
    if not value:
        raise RuntimeError("Set SERVICEOS_DATABASE_URL before database commands.")
    return value


def build_engine(url: str | None = None) -> Engine:
    value = url or configured_database_url()
    parsed = make_url(value)
    if parsed.drivername != "postgresql+psycopg":
        raise ValueError("The V1 database requires postgresql+psycopg.")
    return create_engine(parsed, pool_pre_ping=True, hide_parameters=True)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
