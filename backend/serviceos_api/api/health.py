from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

router = APIRouter(prefix="/api/v1", tags=["health"])


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    service: Literal["serviceos-api"]
    version: str


@router.get("/health", response_model=HealthResponse, operation_id="read_health")
def read_health() -> HealthResponse:
    """API liveness only; does not assert database or Agent readiness."""
    return HealthResponse(status="ok", service="serviceos-api", version="0.1.0")
