"""Follow-up consent and staff scheduling routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from serviceos_api.api.dependencies import get_actor, get_session
from serviceos_api.application.contracts import (
    FollowUpConsentRead, FollowUpConsentRequest, FollowUpRead, FollowUpRequest, ServiceErrorBody,
)
from serviceos_api.application.followups import FollowUpService

router = APIRouter(prefix="/api/v1")


def get_service(actor=Depends(get_actor), session: Session = Depends(get_session)):
    return FollowUpService(session, actor)


FollowUpBusiness = Annotated[FollowUpService, Depends(get_service)]
ERRORS = {401: {"model": ServiceErrorBody}, 403: {"model": ServiceErrorBody},
          404: {"model": ServiceErrorBody}, 409: {"model": ServiceErrorBody},
          422: {"model": ServiceErrorBody}}


@router.get("/cases/{id}/follow-up-consents", response_model=list[FollowUpConsentRead],
            tags=["follow-ups"], operation_id="list_case_follow_up_consents")
def list_consents(id: UUID, service: FollowUpBusiness):
    return service.list_consents(id)


@router.post("/cases/{id}/follow-up-consents", response_model=FollowUpConsentRead,
             status_code=201, tags=["follow-ups"], operation_id="record_case_follow_up_consent", responses=ERRORS)
def consent(id: UUID, body: FollowUpConsentRequest, service: FollowUpBusiness):
    return service.consent(id, body)


@router.get("/cases/{id}/follow-ups", response_model=list[FollowUpRead],
            tags=["follow-ups"], operation_id="list_case_follow_ups")
def list_jobs(id: UUID, service: FollowUpBusiness):
    return service.list_jobs(id)


@router.post("/cases/{id}/follow-ups", response_model=FollowUpRead,
             status_code=201, tags=["follow-ups"], operation_id="schedule_case_follow_up", responses=ERRORS)
def schedule(id: UUID, body: FollowUpRequest, service: FollowUpBusiness):
    return service.schedule(id, body)
