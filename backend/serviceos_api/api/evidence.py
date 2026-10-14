"""HTTP routes for controlled case image evidence."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from serviceos_api.api.dependencies import get_actor, get_session
from serviceos_api.application.contracts import EvidencePage, EvidenceRead, ServiceErrorBody, UploadEvidence
from serviceos_api.application.errors import ServiceError
from serviceos_api.application.evidence import EvidenceService
from serviceos_api.application.image_safety import PROPOSAL_MAX_IMAGE_BYTES

router = APIRouter(prefix="/api/v1")


def get_evidence_service(actor=Depends(get_actor), session: Session = Depends(get_session)):
    return EvidenceService(session, actor)


EvidenceBusiness = Annotated[EvidenceService, Depends(get_evidence_service)]
_ERRORS = {
    401: {"model": ServiceErrorBody, "description": "Not authenticated"},
    403: {"model": ServiceErrorBody, "description": "Actor cannot upload evidence"},
    404: {"model": ServiceErrorBody, "description": "Case not found or hidden"},
    409: {"model": ServiceErrorBody, "description": "Stale case version or idempotency conflict"},
    413: {"model": ServiceErrorBody, "description": "File exceeds size limit"},
    415: {"model": ServiceErrorBody, "description": "Unsupported media type"},
    422: {"model": ServiceErrorBody, "description": "Invalid metadata or unsafe file"},
    503: {"model": ServiceErrorBody, "description": "Storage or inspection unavailable"},
}


@router.get("/cases/{id}/evidence", response_model=EvidencePage, tags=["evidence"],
            operation_id="list_case_evidence", responses=_ERRORS)
def list_case_evidence(id: UUID, service: EvidenceBusiness, cursor: UUID | None = None,
                       limit: int = Query(default=50, ge=1, le=100)):
    return service.list_evidence(id, cursor, limit)


@router.post("/cases/{id}/evidence", response_model=EvidenceRead, status_code=202, tags=["evidence"],
             operation_id="upload_case_evidence", responses=_ERRORS)
async def upload_case_evidence(
    id: UUID,
    service: EvidenceBusiness,
    client_evidence_id: Annotated[UUID, Form()],
    expected_case_version: Annotated[int, Form(ge=1)],
    file: Annotated[UploadFile, File()],
    visibility: Annotated[Literal["PUBLIC", "INTERNAL"], Form()] = "PUBLIC",
):
    try:
        command = UploadEvidence(
            client_evidence_id=client_evidence_id,
            expected_case_version=expected_case_version,
            visibility=visibility,
        )
    except ValidationError as error:
        raise ServiceError(422, "图片证据元数据不正确。", code="INVALID_EVIDENCE") from error
    payload = await file.read(PROPOSAL_MAX_IMAGE_BYTES + 1)
    declared = file.content_type
    return EvidenceRead.model_validate(service.upload(id, command, payload, declared))


@router.get("/cases/{id}/evidence/{evidence_id}/content", tags=["evidence"],
            operation_id="read_case_evidence_content", responses={
                200: {"content": {
                    "image/jpeg": {"schema": {"type": "string", "format": "binary"}},
                    "image/png": {"schema": {"type": "string", "format": "binary"}},
                    "image/webp": {"schema": {"type": "string", "format": "binary"}},
                }, "description": "Authorized inspected image; Cache-Control no-store"},
                401: _ERRORS[401],
                404: {"model": ServiceErrorBody, "description": "Evidence not found, hidden or not yet safe to serve"},
            })
def read_case_evidence_content(id: UUID, evidence_id: UUID, service: EvidenceBusiness):
    payload, media_type = service.read_content(id, evidence_id)
    return Response(content=payload, media_type=media_type, headers={"Cache-Control": "no-store"})
