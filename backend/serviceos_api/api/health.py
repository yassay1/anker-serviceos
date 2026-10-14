from pathlib import Path
from typing import Literal

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from serviceos_api.persistence.database import build_engine

router = APIRouter(prefix="/api/v1", tags=["health"])


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok"]
    service: Literal["serviceos-api"]
    version: str


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ready", "not_ready"]
    production_ready: bool
    components: dict[str, str]


@router.get("/health", response_model=HealthResponse, operation_id="read_health")
def read_health() -> HealthResponse:
    return HealthResponse(status="ok", service="serviceos-api", version="0.1.0")


def database_readiness(connection) -> dict[str, str]:
    connection.execute(text("SELECT 1"))
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    expected = set(ScriptDirectory.from_config(config).get_heads())
    present = set(connection.execute(text("SELECT version_num FROM public.serviceos_alembic_version")).scalars())
    return {"database": "ready", "schema": "ready" if expected == present else "outdated"}


@router.get("/readiness", response_model=ReadinessResponse, responses={503: {"model": ReadinessResponse}}, operation_id="read_readiness")
def read_readiness(request: Request, response: Response) -> ReadinessResponse:
    settings = request.app.state.settings
    components = {"database": "unavailable", "schema": "unavailable"}
    try:
        if request.app.state.database_engine is None:
            request.app.state.database_engine = build_engine()
            request.app.state.owns_engine = True
        with request.app.state.database_engine.connect() as connection:
            components.update(database_readiness(connection))
    except (RuntimeError, ValueError, SQLAlchemyError):
        pass
    components["auth"] = "local_development" if settings.local_auth_enabled else "not_configured"
    components["provider"] = "configured_unverified" if settings.llm_configured else "not_configured"
    components["storage"] = "not_configured"
    if settings.evidence_storage_backend == "s3" and settings.s3_bucket and settings.s3_region:
        components["storage"] = "configured_unverified"
    elif settings.evidence_storage_backend == "local" and settings.environment in ("development", "test"):
        components["storage"] = "local_development"
    ready = (components["database"] == "ready" and components["schema"] == "ready"
             and settings.local_auth_enabled and components["storage"] != "not_configured")
    response.status_code = 200 if ready else 503
    response.headers["Cache-Control"] = "no-store"
    return ReadinessResponse(status="ready" if ready else "not_ready", production_ready=False, components=components)
