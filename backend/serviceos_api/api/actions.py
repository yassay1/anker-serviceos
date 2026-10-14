"""Actual HTTP operations for the explicitly simulated service-action slice."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from serviceos_api.api.dependencies import get_actor, get_session
from serviceos_api.application.actions import ServiceActionService
from serviceos_api.application.errors import ServiceError
from serviceos_api.application.contracts import (
    ActionApprovalDecision, ActionApprovalRead, CaseActionRead, MockActionRequest, ServiceErrorBody,
)

router = APIRouter(prefix="/api/v1")


def get_action_service(request: Request, actor=Depends(get_actor), session: Session = Depends(get_session)):
    if request.app.state.settings.environment not in ("development", "test"):
        raise ServiceError(503, "模拟售后动作仅在开发和测试环境提供。", code="MOCK_ACTION_UNAVAILABLE")
    return ServiceActionService(session, actor)


Actions = Annotated[ServiceActionService, Depends(get_action_service)]


@router.post("/cases/{id}/action-requests", response_model=CaseActionRead, status_code=202,
             tags=["actions"], operation_id="request_mock_case_action",
             responses={401: {"model": ServiceErrorBody}, 403: {"model": ServiceErrorBody},
                        404: {"model": ServiceErrorBody}, 409: {"model": ServiceErrorBody}})
def request_mock_case_action(id: UUID, body: MockActionRequest, service: Actions):
    return service.request(id, body)


@router.get("/cases/{id}/actions", response_model=list[CaseActionRead], tags=["actions"],
            operation_id="list_case_actions")
def list_case_actions(id: UUID, service: Actions):
    return service.list_actions(id)


@router.get("/actions/{id}", response_model=CaseActionRead, tags=["actions"],
            operation_id="read_case_action")
def read_case_action(id: UUID, service: Actions):
    return service.read_action(id)


@router.get("/cases/{id}/approvals", response_model=list[ActionApprovalRead], tags=["approvals"],
            operation_id="list_case_action_approvals")
def list_case_action_approvals(id: UUID, service: Actions):
    return service.list_approvals(id)


@router.post("/approvals/{id}/decisions", response_model=ActionApprovalRead, tags=["approvals"],
             operation_id="decide_action_approval",
             responses={401: {"model": ServiceErrorBody}, 403: {"model": ServiceErrorBody},
                        404: {"model": ServiceErrorBody}, 409: {"model": ServiceErrorBody}})
def decide_action_approval(id: UUID, body: ActionApprovalDecision, service: Actions):
    return service.decide(id, body)
