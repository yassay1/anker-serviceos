"""Actual customer-observed outcome verification routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from serviceos_api.api.dependencies import get_actor, get_session
from serviceos_api.application.contracts import (
    ResolutionContractRead, ServiceErrorBody, VerificationRead, VerificationRequest,
)
from serviceos_api.application.verification import VerificationService
from serviceos_api.application.errors import ServiceError

router = APIRouter(prefix="/api/v1")


def get_verification_service(request: Request, actor=Depends(get_actor), session: Session = Depends(get_session)):
    if request.app.state.settings.environment not in ("development", "test"):
        raise ServiceError(503, "模拟售后核验仅在开发和测试环境提供。", code="MOCK_VERIFICATION_UNAVAILABLE")
    return VerificationService(session, actor)


VerificationBusiness = Annotated[VerificationService, Depends(get_verification_service)]


@router.get("/cases/{id}/resolution-contract", response_model=ResolutionContractRead,
            tags=["verifications"], operation_id="read_case_resolution_contract")
def read_case_resolution_contract(id: UUID, service: VerificationBusiness):
    return service.read_contract(id)


@router.get("/cases/{id}/verifications", response_model=list[VerificationRead],
            tags=["verifications"], operation_id="list_case_verifications")
def list_case_verifications(id: UUID, service: VerificationBusiness):
    return service.list_verifications(id)


@router.post("/cases/{id}/verifications", response_model=VerificationRead, status_code=201,
             tags=["verifications"], operation_id="record_case_verification",
             responses={401: {"model": ServiceErrorBody}, 403: {"model": ServiceErrorBody},
                        404: {"model": ServiceErrorBody}, 409: {"model": ServiceErrorBody},
                        422: {"model": ServiceErrorBody}})
def record_case_verification(id: UUID, body: VerificationRequest, service: VerificationBusiness):
    return service.record(id, body)
