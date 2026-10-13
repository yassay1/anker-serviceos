from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from serviceos_api.persistence.database import build_engine


def pytest_addoption(parser):
    parser.addoption("--require-postgres", action="store_true", help="Fail when PostgreSQL integration configuration is absent")


def migration_config(engine) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["database_url"] = engine.url.render_as_string(hide_password=False)
    return config


@pytest.fixture(scope="session")
def database_engine(request):
    import os

    value = os.getenv("SERVICEOS_TEST_DATABASE_URL")
    if not value:
        if request.config.getoption("--require-postgres"):
            pytest.fail("SERVICEOS_TEST_DATABASE_URL is required for PostgreSQL acceptance.")
        pytest.skip("PostgreSQL integration requires SERVICEOS_TEST_DATABASE_URL; no SQLite fallback.")
    url = make_url(value)
    if url.drivername != "postgresql+psycopg":
        pytest.fail("Tests require postgresql+psycopg.")
    name = f"serviceos_test_{uuid4().hex}"
    assert name.startswith("serviceos_test_") and name.replace("_", "").isalnum()
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT", hide_parameters=True)
    engine = None
    created = False
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        created = True
        engine = build_engine(url.set(database=name).render_as_string(hide_password=False))
        command.upgrade(migration_config(engine), "head")
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            # Only the database created by this fixture can be dropped.
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE "{name}"'))
        admin.dispose()


@pytest.fixture
def db_session(database_engine):
    with database_engine.connect() as connection:
        transaction = connection.begin()
        with Session(connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()
