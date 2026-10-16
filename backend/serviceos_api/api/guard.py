"""Staff-only publication guard review and policy registry reads."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from serviceos_api.api.dependencies import get_actor, get_session
from serviceos_api.application.contracts import (
    GuardDecisionPage, GuardDecisionRead, GuardStatsRead, PolicyRead, ServiceErrorBody,
)
from serviceos_api.application.guard_service import GuardService

router = APIRouter(prefix="/api/v1", tags=["guard"])


def get_guard_service(actor=Depends(get_actor), session: Session = Depends(get_session)):
    return GuardService(session, actor)


Guard = Annotated[GuardService, Depends(get_guard_service)]
_ERRORS = {
    401: {"model": ServiceErrorBody, "description": "Not authenticated"},
    403: {"model": ServiceErrorBody, "description": "Actor cannot access guard records"},
    404: {"model": ServiceErrorBody, "description": "Guard decision not found"},
    409: {"model": ServiceErrorBody, "description": "Decision state forbids the operation"},
}


@router.get("/guard/decisions", response_model=GuardDecisionPage,
            operation_id="list_guard_decisions", responses=_ERRORS)
def list_guard_decisions(service: Guard, response: Response,
                         cursor: UUID | None = Query(default=None),
                         limit: int = Query(default=50, ge=1, le=100)):
    response.headers["Cache-Control"] = "no-store"
    return service.decisions(cursor, limit)


@router.get("/guard/stats", response_model=GuardStatsRead,
            operation_id="read_guard_stats", responses=_ERRORS)
def read_guard_stats(service: Guard, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return service.stats()


@router.get("/guard/decisions/{decision_id}", response_model=GuardDecisionRead,
            operation_id="read_guard_decision", responses=_ERRORS)
def read_guard_decision(decision_id: UUID, service: Guard, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return service.decision(decision_id)


@router.post("/guard/decisions/{decision_id}/override", response_model=GuardDecisionRead,
             operation_id="override_guard_decision", responses=_ERRORS)
def override_guard_decision(decision_id: UUID, service: Guard):
    return service.override(decision_id)


@router.get("/policies", response_model=list[PolicyRead],
            operation_id="list_service_policies", responses=_ERRORS)
def list_service_policies(service: Guard, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return service.policies()
