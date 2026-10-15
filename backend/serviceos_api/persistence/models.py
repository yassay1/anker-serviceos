"""V1 business entities, isolated from Agent checkpoints and legacy Case JSON."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index,
    Integer, MetaData, String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

BUSINESS_SCHEMA = "serviceos"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })


class Record:
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )


class TenantRecord(Record):
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey(f"{BUSINESS_SCHEMA}.tenants.id"), nullable=False,
    )


def tenant_args(*constraints):
    return (UniqueConstraint("tenant_id", "id"), *constraints, {"schema": BUSINESS_SCHEMA})


def tenant_reference(column: str, target: str, target_column: str = "id"):
    return ForeignKeyConstraint(
        ["tenant_id", column],
        [f"{BUSINESS_SCHEMA}.{target}.tenant_id", f"{BUSINESS_SCHEMA}.{target}.{target_column}"],
    )


class Tenant(Record, Base):
    __tablename__ = "tenants"
    __table_args__ = {"schema": BUSINESS_SCHEMA}
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(160))


class Customer(TenantRecord, Base):
    __tablename__ = "customers"
    __table_args__ = tenant_args(UniqueConstraint("tenant_id", "external_subject"))
    display_name: Mapped[str] = mapped_column(String(160))
    external_subject: Mapped[str | None] = mapped_column(String(240))


class StaffUser(Record, Base):
    __tablename__ = "staff_users"
    __table_args__ = {"schema": BUSINESS_SCHEMA}
    display_name: Mapped[str] = mapped_column(String(160))
    external_subject: Mapped[str | None] = mapped_column(String(240), unique=True)


class TenantMembership(TenantRecord, Base):
    __tablename__ = "tenant_memberships"
    __table_args__ = tenant_args(
        UniqueConstraint("tenant_id", "staff_user_id"),
        CheckConstraint("role IN ('SUPPORT','SUPERVISOR','ADMIN')", name="role_values"),
    )
    staff_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey(f"{BUSINESS_SCHEMA}.staff_users.id"),
    )
    role: Mapped[str] = mapped_column(String(24), default="SUPPORT", server_default="SUPPORT")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class DevicePassport(TenantRecord, Base):
    __tablename__ = "device_passports"
    __table_args__ = tenant_args(
        tenant_reference("customer_id", "customers"),
        CheckConstraint("identity_status IN ('UNVERIFIED','VERIFIED')", name="identity_values"),
        CheckConstraint(
            "(model IS NOT NULL AND length(trim(model)) > 0) OR "
            "(serial_number IS NOT NULL AND length(trim(serial_number)) > 0)",
            name="identity_material_required",
        ),
        CheckConstraint(
            "identity_status <> 'VERIFIED' OR (verified_by IS NOT NULL AND verified_at IS NOT NULL)",
            name="verified_identity_source",
        ),
        CheckConstraint("revision >= 1", name="revision_positive"),
        Index("ix_devices_customer", "tenant_id", "customer_id"),
    )
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    model: Mapped[str | None] = mapped_column(String(160))
    serial_number: Mapped[str | None] = mapped_column(String(160))
    identity_status: Mapped[str] = mapped_column(String(24), default="UNVERIFIED", server_default="UNVERIFIED")
    identity_source: Mapped[str] = mapped_column(String(240))
    verified_by: Mapped[str | None] = mapped_column(String(160))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ServiceCase(TenantRecord, Base):
    __tablename__ = "service_cases"
    __table_args__ = tenant_args(
        tenant_reference("customer_id", "customers"),
        CheckConstraint(
            "status IN ('OPEN','IN_PROGRESS','WAITING_CUSTOMER','WAITING_EXTERNAL','RESOLVED','CLOSED')",
            name="status_values",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_cases_customer", "tenant_id", "customer_id"),
    )
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    problem_text: Mapped[str] = mapped_column(Text)
    user_goal: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="OPEN", server_default="OPEN")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Conversation(TenantRecord, Base):
    __tablename__ = "conversations"
    __table_args__ = tenant_args(
        tenant_reference("customer_id", "customers"),
        CheckConstraint("status IN ('ACTIVE','ARCHIVED')", name="status_values"),
        CheckConstraint("collaboration_mode IN ('AI_LEAD','CO_SERVICE','HUMAN_LEAD')", name="mode_values"),
        CheckConstraint("reply_policy IN ('AI_AUTO','AI_REVIEW_REQUIRED','HUMAN_ONLY')", name="policy_values"),
        CheckConstraint("collaboration_mode <> 'HUMAN_LEAD' OR reply_policy = 'HUMAN_ONLY'", name="human_reply_only"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_conversations_customer", "tenant_id", "customer_id"),
    )
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    channel: Mapped[str] = mapped_column(String(32), default="WEB", server_default="WEB")
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE", server_default="ACTIVE")
    collaboration_mode: Mapped[str] = mapped_column(String(24), default="AI_LEAD", server_default="AI_LEAD")
    reply_policy: Mapped[str] = mapped_column(String(24), default="AI_AUTO", server_default="AI_AUTO")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class CaseDevice(Base):
    __tablename__ = "case_devices"
    __table_args__ = (
        tenant_reference("case_id", "service_cases"),
        tenant_reference("device_id", "device_passports"),
        Index("uq_case_devices_primary", "tenant_id", "case_id", unique=True, postgresql_where=text("is_primary")),
        {"schema": BUSINESS_SCHEMA},
    )
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    device_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    role: Mapped[str] = mapped_column(String(32), default="AFFECTED", server_default="AFFECTED")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CaseConversation(Base):
    __tablename__ = "case_conversations"
    __table_args__ = (
        tenant_reference("case_id", "service_cases"),
        tenant_reference("conversation_id", "conversations"),
        {"schema": BUSINESS_SCHEMA},
    )
    tenant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CaseEvidence(TenantRecord, Base):
    __tablename__ = "case_evidence"
    __table_args__ = tenant_args(
        tenant_reference("case_id", "service_cases"),
        CheckConstraint("claim_type IN ('USER_STATEMENT','OBSERVATION','TOOL_RESULT','HYPOTHESIS')", name="claim_values"),
        CheckConstraint("certainty IN ('LOW','MEDIUM','HIGH')", name="certainty_values"),
        CheckConstraint("validity IN ('CANDIDATE','VERIFIED','RETRACTED')", name="validity_values"),
        CheckConstraint("claim_type <> 'HYPOTHESIS' OR validity <> 'VERIFIED'", name="hypothesis_not_fact"),
        CheckConstraint("validity <> 'VERIFIED' OR (verified_at IS NOT NULL AND verified_by IS NOT NULL)", name="verification_source"),
    )
    case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    source: Mapped[str] = mapped_column(String(240))
    claim_type: Mapped[str] = mapped_column(String(32))
    certainty: Mapped[str] = mapped_column(String(16), default="MEDIUM", server_default="MEDIUM")
    validity: Mapped[str] = mapped_column(String(24), default="CANDIDATE", server_default="CANDIDATE")
    summary: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[str | None] = mapped_column(String(160))


class CaseImageEvidence(TenantRecord, Base):
    """Image metadata and private object reference for a case."""

    __tablename__ = "case_image_evidence"
    __table_args__ = tenant_args(
        tenant_reference("case_id", "service_cases"),
        tenant_reference("author_customer_id", "customers"),
        tenant_reference("author_staff_id", "tenant_memberships", "staff_user_id"),
        UniqueConstraint("tenant_id", "case_id", "client_evidence_id"),
        CheckConstraint("visibility IN ('PUBLIC','INTERNAL')", name="visibility_values"),
        CheckConstraint("media_type IN ('image/jpeg','image/png','image/webp')", name="media_values"),
        CheckConstraint("byte_size >= 1 AND byte_size <= 10485760", name="byte_size_bounds"),
        CheckConstraint("inspection_status IN ('PENDING','CLEAN','REJECTED')", name="inspection_values"),
        CheckConstraint("verification IN ('UNVERIFIED','VERIFIED','RETRACTED')", name="verification_values"),
        CheckConstraint("source_kind IN ('CUSTOMER','STAFF')", name="source_values"),
        CheckConstraint(
            "(source_kind = 'CUSTOMER' AND author_customer_id IS NOT NULL AND author_staff_id IS NULL) OR "
            "(source_kind = 'STAFF' AND author_staff_id IS NOT NULL AND author_customer_id IS NULL)",
            name="author_identity",
        ),
        CheckConstraint(
            "(inspection_status = 'REJECTED' AND rejection_code IS NOT NULL) OR "
            "(inspection_status IN ('PENDING','CLEAN') AND rejection_code IS NULL AND storage_key IS NOT NULL)",
            name="inspection_payload",
        ),
        Index("ix_case_image_evidence_case", "tenant_id", "case_id", "created_at", "id"),
    )
    case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    client_evidence_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    file_digest: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    visibility: Mapped[str] = mapped_column(String(16), default="PUBLIC", server_default="PUBLIC")
    media_type: Mapped[str] = mapped_column(String(32))
    byte_size: Mapped[int] = mapped_column(Integer)
    inspection_status: Mapped[str] = mapped_column(String(16), default="PENDING", server_default="PENDING")
    verification: Mapped[str] = mapped_column(String(16), default="UNVERIFIED", server_default="UNVERIFIED")
    source_kind: Mapped[str] = mapped_column(String(16))
    author_customer_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    author_staff_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    storage_key: Mapped[str | None] = mapped_column(String(160))
    rejection_code: Mapped[str | None] = mapped_column(String(80))


class EvidenceInspectionJob(TenantRecord, Base):
    __tablename__ = "evidence_inspection_jobs"
    __table_args__ = tenant_args(
        tenant_reference("evidence_id", "case_image_evidence"),
        UniqueConstraint("tenant_id", "evidence_id"),
        CheckConstraint("status IN ('QUEUED','RUNNING','COMPLETED','FAILED')", name="status_values"),
        CheckConstraint("attempt_count >= 0 AND max_attempts >= 1 AND attempt_count <= max_attempts", name="attempt_bounds"),
        Index("ix_evidence_inspection_jobs_ready", "status", "available_at", "created_at"),
    )
    evidence_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(24), default="QUEUED", server_default="QUEUED")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    lease_owner: Mapped[str | None] = mapped_column(String(120))
    lease_token: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80))


class CaseAction(TenantRecord, Base):
    """Authorized business intent and its actual simulated operation receipt."""

    __tablename__ = "case_actions"
    __table_args__ = tenant_args(
        tenant_reference("case_id", "service_cases"),
        tenant_reference("requested_by", "tenant_memberships", "staff_user_id"),
        tenant_reference("source_proposal_id", "agent_proposals"),
        UniqueConstraint("tenant_id", "case_id", "client_action_id"),
        CheckConstraint("action_kind = 'MOCK_SERVICE_REQUEST'", name="kind_values"),
        CheckConstraint("adapter = 'MOCK'", name="adapter_values"),
        CheckConstraint("status IN ('WAITING_APPROVAL','APPROVED','EXECUTING','UNKNOWN','SUCCEEDED','FAILED','REJECTED')", name="status_values"),
        CheckConstraint("version >= 1 AND attempt_count >= 0", name="version_attempt_positive"),
        CheckConstraint("(receipt_result IS NULL AND receipt_reference IS NULL AND receipt_at IS NULL) OR "
                        "(receipt_result IN ('SUCCEEDED','FAILED') AND receipt_reference IS NOT NULL AND receipt_at IS NOT NULL)",
                        name="receipt_complete"),
        CheckConstraint("status NOT IN ('SUCCEEDED','FAILED') OR receipt_result = status", name="terminal_has_receipt"),
        Index("ix_case_actions_ready", "status", "available_at", "created_at"),
    )
    case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    client_action_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    request_hash: Mapped[str] = mapped_column(String(64))
    action_kind: Mapped[str] = mapped_column(String(40))
    adapter: Mapped[str] = mapped_column(String(16), default="MOCK", server_default="MOCK")
    status: Mapped[str] = mapped_column(String(24), default="WAITING_APPROVAL", server_default="WAITING_APPROVAL")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    requested_by: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    source_proposal_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reason: Mapped[str] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    lease_token: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    receipt_reference: Mapped[str | None] = mapped_column(String(160))
    receipt_result: Mapped[str | None] = mapped_column(String(16))
    receipt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80))


class CaseActionApproval(TenantRecord, Base):
    __tablename__ = "case_action_approvals"
    __table_args__ = tenant_args(
        tenant_reference("action_id", "case_actions"),
        tenant_reference("decided_by", "tenant_memberships", "staff_user_id"),
        UniqueConstraint("tenant_id", "action_id"),
        UniqueConstraint("tenant_id", "decision_id"),
        CheckConstraint("status IN ('PENDING','APPROVED','REJECTED')", name="status_values"),
        CheckConstraint("version >= 1", name="version_positive"),
    )
    action_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(16), default="PENDING", server_default="PENDING")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    decision_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    decision_hash: Mapped[str | None] = mapped_column(String(64))
    decided_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MockServiceOperation(TenantRecord, Base):
    """Durable local stand-in for a separate service endpoint, keyed by action ID."""

    __tablename__ = "mock_service_operations"
    __table_args__ = tenant_args(
        tenant_reference("action_id", "case_actions"),
        UniqueConstraint("tenant_id", "action_id"),
        UniqueConstraint("tenant_id", "external_reference"),
        CheckConstraint("result IN ('SUCCEEDED','FAILED')", name="result_values"),
    )
    action_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    external_reference: Mapped[str] = mapped_column(String(160))
    result: Mapped[str] = mapped_column(String(16))


class ResolutionContract(TenantRecord, Base):
    """Conditions frozen for one service action before its outcome is observed."""

    __tablename__ = "resolution_contracts"
    __table_args__ = tenant_args(
        tenant_reference("case_id", "service_cases"),
        tenant_reference("action_id", "case_actions"),
        UniqueConstraint("tenant_id", "action_id"),
        CheckConstraint("version >= 1", name="version_positive"),
    )
    case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    action_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    conditions: Mapped[list[str]] = mapped_column(JSONB)


class CaseVerification(TenantRecord, Base):
    """Customer observation and the server's decision at the time it was recorded."""

    __tablename__ = "case_verifications"
    __table_args__ = tenant_args(
        tenant_reference("case_id", "service_cases"),
        tenant_reference("contract_id", "resolution_contracts"),
        tenant_reference("customer_id", "customers"),
        UniqueConstraint("tenant_id", "case_id", "client_verification_id"),
        CheckConstraint("observed_result IN ('WORKING','NOT_WORKING','UNCERTAIN')", name="observation_values"),
        CheckConstraint("decision IN ('PENDING','VERIFIED_RESOLVED','NOT_RESOLVED')", name="decision_values"),
    )
    case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    contract_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    client_verification_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    request_hash: Mapped[str] = mapped_column(String(64))
    observed_result: Mapped[str] = mapped_column(String(16))
    decision: Mapped[str] = mapped_column(String(24))
    note: Mapped[str] = mapped_column(Text)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    case_status: Mapped[str] = mapped_column(String(24))


class ExperienceCandidate(TenantRecord, Base):
    """A human-curated, non-authoritative lesson from one verified resolution."""
    __tablename__ = "experience_candidates"
    __table_args__ = tenant_args(
        tenant_reference("source_case_id", "service_cases"),
        tenant_reference("source_verification_id", "case_verifications"),
        UniqueConstraint("tenant_id", "source_verification_id"),
        CheckConstraint("status IN ('DRAFT','PENDING_REVIEW','APPROVED','REJECTED','REVOKED')", name="status_values"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_experience_candidates_status", "tenant_id", "status", "updated_at"),
    )
    source_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    source_verification_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    content: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", server_default="DRAFT")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    authored_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExperienceReview(TenantRecord, Base):
    """Append-only supervisor decisions for candidate review and revocation."""
    __tablename__ = "experience_reviews"
    __table_args__ = tenant_args(
        tenant_reference("candidate_id", "experience_candidates"),
        tenant_reference("reviewer_id", "tenant_memberships", "staff_user_id"),
        UniqueConstraint("tenant_id", "candidate_id", "decision_id"),
        CheckConstraint("decision IN ('APPROVED','REJECTED','REVOKED')", name="decision_values"),
        CheckConstraint("candidate_version >= 1", name="candidate_version_positive"),
    )
    candidate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    reviewer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    decision_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    candidate_version: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(16))
    request_hash: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)


class DeviceFact(TenantRecord, Base):
    __tablename__ = "device_facts"
    __table_args__ = tenant_args(
        tenant_reference("device_id", "device_passports"),
        tenant_reference("source_case_id", "service_cases"),
        tenant_reference("archived_by", "tenant_memberships", "staff_user_id"),
        UniqueConstraint("tenant_id", "device_id", "client_fact_id"),
        CheckConstraint("validity IN ('CANDIDATE','VERIFIED','RETRACTED')", name="validity_values"),
        CheckConstraint("source_kind IN ('USER','MODEL','TOOL','HUMAN')", name="source_values"),
        CheckConstraint(
            "validity <> 'VERIFIED' OR (verified_by IS NOT NULL AND verified_at IS NOT NULL "
            "AND verifier_kind IS NOT NULL AND verifier_kind IN ('HUMAN','TRUSTED_TOOL'))",
            name="verification_source",
        ),
        CheckConstraint(
            "validity <> 'RETRACTED' OR (retracted_at IS NOT NULL AND retraction_reason IS NOT NULL)",
            name="retraction_source",
        ),
        CheckConstraint("revision >= 1", name="revision_positive"),
        Index("ix_device_facts_device", "tenant_id", "device_id"),
    )
    device_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    client_fact_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    source_case_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    fact_key: Mapped[str] = mapped_column(String(120))
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(24))
    source: Mapped[str] = mapped_column(String(240))
    validity: Mapped[str] = mapped_column(String(24), default="CANDIDATE", server_default="CANDIDATE")
    verifier_kind: Mapped[str | None] = mapped_column(String(24))
    verified_by: Mapped[str | None] = mapped_column(String(160))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retraction_reason: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class Message(TenantRecord, Base):
    __tablename__ = "messages"
    __table_args__ = tenant_args(
        tenant_reference("conversation_id", "conversations"),
        tenant_reference("author_customer_id", "customers"),
        tenant_reference("author_staff_id", "tenant_memberships", "staff_user_id"),
        tenant_reference("related_case_id", "service_cases"),
        UniqueConstraint("tenant_id", "conversation_id", "client_message_id"),
        CheckConstraint("visibility IN ('PUBLIC','INTERNAL')", name="visibility_values"),
        CheckConstraint("jsonb_typeof(content) = 'array' AND jsonb_array_length(content) > 0", name="content_array"),
        CheckConstraint(
            "(author_kind = 'CUSTOMER' AND author_customer_id IS NOT NULL AND author_staff_id IS NULL AND visibility = 'PUBLIC') OR "
            "(author_kind = 'STAFF' AND author_staff_id IS NOT NULL AND author_customer_id IS NULL) OR "
            "(author_kind IN ('AGENT','SYSTEM') AND author_customer_id IS NULL AND author_staff_id IS NULL)",
            name="author_identity",
        ),
        CheckConstraint("client_message_id IS NULL OR request_hash IS NOT NULL", name="idempotency_hash"),
        Index("ix_messages_conversation", "tenant_id", "conversation_id", "created_at", "id"),
    )
    conversation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    author_kind: Mapped[str] = mapped_column(String(24))
    author_customer_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    author_staff_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    visibility: Mapped[str] = mapped_column(String(16), default="PUBLIC", server_default="PUBLIC")
    content: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    related_case_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    client_message_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    request_hash: Mapped[str | None] = mapped_column(String(64))


class AuthSession(TenantRecord, Base):
    __tablename__ = "auth_sessions"
    __table_args__ = tenant_args(
        tenant_reference("customer_id", "customers"),
        tenant_reference("staff_user_id", "tenant_memberships", "staff_user_id"),
        CheckConstraint(
            "(customer_id IS NOT NULL AND staff_user_id IS NULL) OR "
            "(staff_user_id IS NOT NULL AND customer_id IS NULL)", name="one_actor",
        ),
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    customer_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    staff_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MessageJob(TenantRecord, Base):
    __tablename__ = "message_jobs"
    __table_args__ = tenant_args(
        tenant_reference("message_id", "messages"),
        tenant_reference("conversation_id", "conversations"),
        UniqueConstraint("tenant_id", "message_id"),
        CheckConstraint("status IN ('QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED')", name="status_values"),
        CheckConstraint("attempt_count >= 0 AND max_attempts >= 1 AND attempt_count <= max_attempts", name="attempt_bounds"),
        Index("ix_message_jobs_ready", "status", "available_at", "created_at"),
    )
    message_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    conversation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(24), default="QUEUED", server_default="QUEUED")
    kind: Mapped[str] = mapped_column(String(48), default="PROCESS_USER_MESSAGE", server_default="PROCESS_USER_MESSAGE")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    lease_owner: Mapped[str | None] = mapped_column(String(120))
    lease_token: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80))


class OutboxEvent(TenantRecord, Base):
    __tablename__ = "outbox_events"
    __table_args__ = tenant_args(
        tenant_reference("conversation_id", "conversations"),
        CheckConstraint("visibility IN ('PUBLIC','INTERNAL')", name="visibility_values"),
        CheckConstraint("attempt_count >= 0 AND max_attempts >= 1 AND attempt_count <= max_attempts", name="attempt_bounds"),
        Index("ix_outbox_events_ready", "published_at", "available_at", "created_at"),
    )
    conversation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    type: Mapped[str] = mapped_column(String(80))
    visibility: Mapped[str] = mapped_column(String(16))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, default=8, server_default="8")
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    lease_owner: Mapped[str | None] = mapped_column(String(120))
    lease_token: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    dead_lettered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentRun(TenantRecord, Base):
    __tablename__ = "agent_runs"
    __table_args__ = tenant_args(
        tenant_reference("job_id", "message_jobs"),
        tenant_reference("conversation_id", "conversations"),
        tenant_reference("message_id", "messages"),
        UniqueConstraint("tenant_id", "message_id"),
        CheckConstraint("status IN ('RUNNING','WAITING_APPROVAL','COMPLETED','FAILED','CANCELLED')", name="status_values"),
        CheckConstraint("step_count >= 0", name="steps_nonnegative"),
        Index("ix_agent_runs_conversation", "tenant_id", "conversation_id", "created_at"),
    )
    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    conversation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    message_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    thread_id: Mapped[str] = mapped_column(String(160))
    lease_token: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(24), default="RUNNING", server_default="RUNNING")
    provider: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(160))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    step_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(80))
    result_text: Mapped[str | None] = mapped_column(Text)
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class AgentProposal(TenantRecord, Base):
    __tablename__ = "agent_proposals"
    __table_args__ = tenant_args(
        tenant_reference("agent_run_id", "agent_runs"),
        tenant_reference("conversation_id", "conversations"),
        UniqueConstraint("tenant_id", "agent_run_id", "idempotency_key"),
        CheckConstraint("proposal_type IN ('MISSING_EVIDENCE','ACTION','REPLY')", name="type_values"),
        CheckConstraint("status IN ('DRAFT','APPROVED','REJECTED')", name="status_values"),
        CheckConstraint("visibility = 'INTERNAL'", name="internal_only"),
    )
    agent_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    conversation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    proposal_type: Mapped[str] = mapped_column(String(32))
    idempotency_key: Mapped[str] = mapped_column(String(120))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", server_default="DRAFT")
    visibility: Mapped[str] = mapped_column(String(16), default="INTERNAL", server_default="INTERNAL")
    decision_key: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    decision_hash: Mapped[str | None] = mapped_column(String(64))
    decided_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)


class ServiceTask(TenantRecord, Base):
    __tablename__ = "service_tasks"
    __table_args__ = tenant_args(
        tenant_reference("conversation_id", "conversations"),
        tenant_reference("case_id", "service_cases"),
        tenant_reference("requester_customer_id", "customers"),
        CheckConstraint("status IN ('OPEN','ASSIGNED','CLOSED')", name="status_values"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_service_tasks_conversation", "tenant_id", "conversation_id", "created_at"),
    )
    conversation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    case_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    requester_customer_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="OPEN", server_default="OPEN")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class FollowUpConsent(TenantRecord, Base):
    __tablename__ = "follow_up_consents"
    __table_args__ = tenant_args(
        tenant_reference("case_id", "service_cases"),
        tenant_reference("customer_id", "customers"),
        UniqueConstraint("tenant_id", "case_id", "client_consent_id"),
    )
    case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    client_consent_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    request_hash: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[str] = mapped_column(String(1000))


class FollowUpJob(TenantRecord, Base):
    __tablename__ = "follow_up_jobs"
    __table_args__ = tenant_args(
        tenant_reference("case_id", "service_cases"),
        tenant_reference("consent_record_id", "follow_up_consents"),
        tenant_reference("conversation_id", "conversations"),
        tenant_reference("task_id", "service_tasks"),
        tenant_reference("scheduled_by", "tenant_memberships", "staff_user_id"),
        UniqueConstraint("tenant_id", "case_id", "client_follow_up_id"),
        UniqueConstraint("tenant_id", "consent_record_id"),
        CheckConstraint("status IN ('SCHEDULED','DUE','CANCELLED')", name="status_values"),
        Index("ix_follow_up_jobs_due", "status", "due_at"),
    )
    case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    consent_record_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    conversation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    client_follow_up_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    request_hash: Mapped[str] = mapped_column(String(64))
    scheduled_by: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    purpose: Mapped[str] = mapped_column(String(1000))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="SCHEDULED", server_default="SCHEDULED")
    task_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskAssignment(TenantRecord, Base):
    __tablename__ = "task_assignments"
    __table_args__ = tenant_args(
        tenant_reference("task_id", "service_tasks"),
        tenant_reference("staff_user_id", "tenant_memberships", "staff_user_id"),
        Index("uq_task_assignments_active", "tenant_id", "task_id", unique=True,
              postgresql_where=text("ended_at IS NULL")),
    )
    task_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    staff_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConversationEvent(TenantRecord, Base):
    __tablename__ = "conversation_events"
    __table_args__ = tenant_args(
        tenant_reference("conversation_id", "conversations"),
        UniqueConstraint("tenant_id", "conversation_id", "sequence"),
        CheckConstraint("sequence >= 1", name="sequence_positive"),
        CheckConstraint("visibility IN ('PUBLIC','INTERNAL')", name="visibility_values"),
        Index("ix_conversation_events_replay", "tenant_id", "conversation_id", "sequence"),
    )
    conversation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    sequence: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(80))
    visibility: Mapped[str] = mapped_column(String(16))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)


class UIDocument(TenantRecord, Base):
    __tablename__ = "ui_documents"
    __table_args__ = tenant_args(
        tenant_reference("conversation_id", "conversations"),
        tenant_reference("source_agent_run_id", "agent_runs"),
        UniqueConstraint("tenant_id", "ui_id", "revision"),
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint("audience IN ('CUSTOMER','STAFF')", name="audience_values"),
        CheckConstraint("visibility IN ('PUBLIC','INTERNAL')", name="visibility_values"),
        CheckConstraint("status IN ('ACTIVE','SUPERSEDED','EXPIRED','INVALID')", name="status_values"),
        Index("uq_ui_documents_active", "tenant_id", "conversation_id", "audience", unique=True,
              postgresql_where=text("status = 'ACTIVE'")),
    )
    conversation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    ui_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), default=uuid4)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    schema_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    catalog_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    surface: Mapped[str] = mapped_column(String(32))
    audience: Mapped[str] = mapped_column(String(16))
    visibility: Mapped[str] = mapped_column(String(16))
    source_agent_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    context_signature: Mapped[str] = mapped_column(String(64))
    components: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    fallback_text: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE", server_default="ACTIVE")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UIActionInvocation(TenantRecord, Base):
    __tablename__ = "ui_action_invocations"
    __table_args__ = tenant_args(
        tenant_reference("ui_document_id", "ui_documents"),
        tenant_reference("task_id", "service_tasks"),
        UniqueConstraint("tenant_id", "actor_kind", "actor_id", "client_action_id"),
        CheckConstraint("actor_kind IN ('CUSTOMER','STAFF')", name="actor_values"),
        CheckConstraint("status IN ('ACCEPTED','REJECTED')", name="status_values"),
    )
    ui_document_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    client_action_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    actor_kind: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    request_hash: Mapped[str] = mapped_column(String(64))
    action_id: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(16))
    task_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
