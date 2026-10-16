"""Staff-only knowledge document upload and pipeline status routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from serviceos_api.api.dependencies import get_actor, get_session
from serviceos_api.application.contracts import (
    KnowledgeDocumentDetail, KnowledgeDocumentRead, KnowledgePage, KnowledgeSearchRead,
    KnowledgeStatsRead, KnowledgeUploadResult, ServiceErrorBody,
)
from serviceos_api.application.errors import ServiceError
from serviceos_api.application.knowledge_pipeline import MAX_UPLOAD_BYTES, KnowledgePipelineService
from serviceos_api.application.evidence_storage import EvidenceStorageFailure
from serviceos_api.integrations.local_evidence_storage import evidence_storage_from_settings

router = APIRouter(prefix="/api/v1", tags=["knowledge"])


def get_knowledge_service(request: Request, actor=Depends(get_actor), session: Session = Depends(get_session)):
    try:
        storage = evidence_storage_from_settings(request.app.state.settings)
    except EvidenceStorageFailure as error:
        raise ServiceError(503, "知识存储暂不可用。", code="KNOWLEDGE_STORAGE_UNAVAILABLE") from error
    return KnowledgePipelineService(session, actor, storage)


KnowledgeBusiness = Annotated[KnowledgePipelineService, Depends(get_knowledge_service)]
_ERRORS = {
    401: {"model": ServiceErrorBody, "description": "Not authenticated"},
    403: {"model": ServiceErrorBody, "description": "Actor cannot manage knowledge documents"},
    404: {"model": ServiceErrorBody, "description": "Knowledge document not found"},
    409: {"model": ServiceErrorBody, "description": "Document state forbids the operation"},
    413: {"model": ServiceErrorBody, "description": "File exceeds size limit"},
    415: {"model": ServiceErrorBody, "description": "Unsupported knowledge file type"},
    503: {"model": ServiceErrorBody, "description": "Knowledge storage unavailable"},
}


@router.get("/knowledge/search", response_model=list[KnowledgeSearchRead],
            operation_id="search_knowledge", responses=_ERRORS)
def search_knowledge(service: KnowledgeBusiness, response: Response,
                     q: str = Query(min_length=1, max_length=500),
                     limit: int = Query(default=10, ge=1, le=20)):
    response.headers["Cache-Control"] = "no-store"
    return service.search(q, limit)


@router.get("/knowledge/stats", response_model=KnowledgeStatsRead,
            operation_id="read_knowledge_stats", responses=_ERRORS)
def read_knowledge_stats(service: KnowledgeBusiness, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return service.stats()


@router.get("/knowledge/documents", response_model=KnowledgePage,
            operation_id="list_knowledge_documents", responses=_ERRORS)
def list_knowledge_documents(service: KnowledgeBusiness, response: Response,
                             cursor: UUID | None = Query(default=None),
                             limit: int = Query(default=50, ge=1, le=100)):
    response.headers["Cache-Control"] = "no-store"
    return service.list_documents(cursor, limit)


@router.get("/knowledge/documents/{document_id}", response_model=KnowledgeDocumentDetail,
            operation_id="get_knowledge_document", responses=_ERRORS)
def get_knowledge_document(document_id: UUID, service: KnowledgeBusiness, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return service.get_document(document_id)


@router.post("/knowledge/documents", response_model=KnowledgeUploadResult, status_code=201,
             operation_id="upload_knowledge_document", responses=_ERRORS)
async def upload_knowledge_document(
    service: KnowledgeBusiness,
    response: Response,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form(max_length=200)] = "",
    sheet_overrides: Annotated[str, Form(max_length=2000)] = "",
):
    import json as _json

    overrides = None
    if sheet_overrides.strip():
        try:
            parsed = _json.loads(sheet_overrides)
        except ValueError as error:
            raise ServiceError(422, "sheet_overrides 需为 JSON 对象。",
                               code="INVALID_SHEET_OVERRIDE") from error
        if not isinstance(parsed, dict):
            raise ServiceError(422, "sheet_overrides 需为 JSON 对象。", code="INVALID_SHEET_OVERRIDE")
        overrides = {str(key): str(value) for key, value in parsed.items()}
    payload = await file.read(MAX_UPLOAD_BYTES + 1)
    document, deduplicated = service.upload(file.filename or "upload", payload, title or None,
                                            sheet_overrides=overrides)
    if deduplicated:
        response.status_code = 200
    return KnowledgeUploadResult(document=document, deduplicated=deduplicated)


@router.post("/knowledge/documents/{document_id}/reprocess", response_model=KnowledgeDocumentRead,
             operation_id="reprocess_knowledge_document", responses=_ERRORS)
def reprocess_knowledge_document(document_id: UUID, service: KnowledgeBusiness):
    return service.reprocess(document_id)
