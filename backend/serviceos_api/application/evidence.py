"""Controlled image evidence. Uploads stay pending until a local safety check."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from serviceos_api.application.contracts import EvidencePage, EvidenceRead, UploadEvidence
from serviceos_api.application.errors import ServiceError
from serviceos_api.application.image_safety import PROPOSAL_MAX_IMAGE_BYTES, PROPOSAL_MEDIA_TYPES, inspect_image, sniff_media_type
from serviceos_api.application.services import BusinessService
from serviceos_api.persistence.models import CaseConversation, CaseImageEvidence, EvidenceInspectionJob, OutboxEvent, ServiceCase


def _request_hash(visibility: str, file_digest: str) -> str:
    payload = json.dumps({"file_digest": file_digest, "visibility": visibility}, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def enqueue_case_events(session: Session, tenant_id: UUID, case_id: UUID, type_: str, data: dict, visibility: str) -> None:
    conversations = session.scalars(select(CaseConversation.conversation_id).where(
        CaseConversation.tenant_id == tenant_id, CaseConversation.case_id == case_id,
    )).all()
    targets = list(conversations) or [None]
    for conversation_id in targets:
        session.add(OutboxEvent(
            tenant_id=tenant_id, conversation_id=conversation_id, type=type_,
            visibility=visibility, data=data,
        ))


def complete_inspection(session: Session, tenant_id: UUID, evidence_id: UUID) -> str:
    """Move PENDING evidence to CLEAN or REJECTED. Repeat calls do not change a terminal result."""
    evidence = session.scalar(select(CaseImageEvidence).where(
        CaseImageEvidence.tenant_id == tenant_id, CaseImageEvidence.id == evidence_id,
    ).with_for_update())
    if evidence is None:
        raise RuntimeError("evidence_missing")
    if evidence.inspection_status != "PENDING":
        return evidence.inspection_status
    reason = inspect_image(evidence.media_type, bytes(evidence.content or b""))
    if reason is None:
        evidence.inspection_status = "CLEAN"
    else:
        evidence.inspection_status = "REJECTED"
        evidence.rejection_code = reason
        evidence.content = None
    enqueue_case_events(session, tenant_id, evidence.case_id, "evidence.inspected", {
        "evidence_id": str(evidence.id), "case_id": str(evidence.case_id),
        "inspection_status": evidence.inspection_status,
    }, evidence.visibility)
    return evidence.inspection_status


class EvidenceService(BusinessService):
    def upload(self, case_id: UUID, command: UploadEvidence, payload: bytes, declared_type: str | None) -> CaseImageEvidence:
        case = self.resource(ServiceCase, case_id, lock=True)
        digest = hashlib.sha256(payload).hexdigest() if payload else ""
        fingerprint = _request_hash(command.visibility, digest)
        existing = self.session.scalar(select(CaseImageEvidence).where(
            CaseImageEvidence.tenant_id == case.tenant_id,
            CaseImageEvidence.case_id == case.id,
            CaseImageEvidence.client_evidence_id == command.client_evidence_id,
        ).with_for_update())
        if existing is not None:
            if existing.request_hash != fingerprint:
                raise ServiceError(409, "同一证据编号不能改成不同的文件或可见性。",
                                    code="IDEMPOTENCY_CONFLICT", current_version=case.version)
            return existing
        if self.actor.kind == "CUSTOMER" and command.visibility != "PUBLIC":
            raise ServiceError(403, "客户只能提交公开图片证据。", code="FORBIDDEN_VISIBILITY")
        if self.actor.kind not in ("CUSTOMER", "STAFF"):
            raise ServiceError(403, "当前身份不能代替客户上传图片。", code="FORBIDDEN_ACTOR")
        self._validate_payload(payload, declared_type)
        if case.version != command.expected_case_version:
            raise ServiceError(409, "案例版本已更新，请刷新后重试。",
                                code="STALE_VERSION", current_version=case.version)
        if case.status == "CLOSED":
            raise ServiceError(409, "已关闭案例不能追加图片证据。", code="CASE_CLOSED", current_version=case.version)
        media_type = sniff_media_type(payload)
        assert media_type is not None
        evidence = CaseImageEvidence(
            tenant_id=case.tenant_id, case_id=case.id, client_evidence_id=command.client_evidence_id,
            file_digest=digest, request_hash=fingerprint, visibility=command.visibility,
            media_type=media_type, byte_size=len(payload), inspection_status="PENDING",
            verification="UNVERIFIED", source_kind=self.actor.kind, content=payload,
            author_customer_id=self.actor.actor_id if self.actor.kind == "CUSTOMER" else None,
            author_staff_id=self.actor.actor_id if self.actor.kind == "STAFF" else None,
        )
        self.session.add(evidence)
        self.session.flush()
        self.session.add(EvidenceInspectionJob(tenant_id=case.tenant_id, evidence_id=evidence.id))
        case.version += 1
        enqueue_case_events(self.session, case.tenant_id, case.id, "evidence.received", {
            "evidence_id": str(evidence.id), "case_id": str(case.id),
            "inspection_status": "PENDING", "case_version": case.version,
        }, evidence.visibility)
        self.session.commit()
        return evidence

    def list_evidence(self, case_id: UUID, cursor: UUID | None, limit: int) -> EvidencePage:
        case = self.resource(ServiceCase, case_id)
        query = select(CaseImageEvidence).where(
            CaseImageEvidence.tenant_id == case.tenant_id, CaseImageEvidence.case_id == case.id,
        )
        if self.actor.kind == "CUSTOMER":
            query = query.where(CaseImageEvidence.visibility == "PUBLIC")
        if cursor is not None:
            current = self.session.scalar(query.where(CaseImageEvidence.id == cursor))
            if current is None:
                raise ServiceError(404, "记录不存在或当前账号无权访问。")
            query = query.where(or_(
                CaseImageEvidence.created_at > current.created_at,
                and_(CaseImageEvidence.created_at == current.created_at, CaseImageEvidence.id > current.id),
            ))
        rows = self.session.scalars(query.order_by(CaseImageEvidence.created_at, CaseImageEvidence.id).limit(limit)).all()
        return EvidencePage(
            items=[EvidenceRead.model_validate(row) for row in rows],
            next_cursor=rows[-1].id if len(rows) == limit else None,
        )

    def read_content(self, case_id: UUID, evidence_id: UUID) -> tuple[bytes, str]:
        case = self.resource(ServiceCase, case_id)
        query = select(CaseImageEvidence).where(
            CaseImageEvidence.tenant_id == case.tenant_id,
            CaseImageEvidence.case_id == case.id,
            CaseImageEvidence.id == evidence_id,
            CaseImageEvidence.inspection_status == "CLEAN",
        )
        if self.actor.kind == "CUSTOMER":
            query = query.where(CaseImageEvidence.visibility == "PUBLIC")
        evidence = self.session.scalar(query)
        if evidence is None or not evidence.content:
            raise ServiceError(404, "图片不存在、无权访问或尚未通过安全检查。")
        return bytes(evidence.content), evidence.media_type

    @staticmethod
    def _validate_payload(payload: bytes, declared_type: str | None) -> None:
        if not payload:
            raise ServiceError(422, "图片内容为空。", code="EMPTY_FILE")
        if len(payload) > PROPOSAL_MAX_IMAGE_BYTES:
            raise ServiceError(413, "图片超过当前提案允许的大小。", code="FILE_TOO_LARGE")
        sniffed = sniff_media_type(payload)
        if sniffed is None:
            raise ServiceError(415, "只接受 JPEG、PNG 或 WebP 图片。", code="UNSUPPORTED_MEDIA")
        normalized = (declared_type or "").split(";", 1)[0].strip().lower()
        if normalized in PROPOSAL_MEDIA_TYPES and normalized != sniffed:
            raise ServiceError(415, "文件内容与声明的图片类型不一致。", code="MEDIA_MISMATCH")
        if normalized and normalized not in PROPOSAL_MEDIA_TYPES and normalized != "application/octet-stream":
            raise ServiceError(415, "只接受 JPEG、PNG 或 WebP 图片。", code="UNSUPPORTED_MEDIA")
