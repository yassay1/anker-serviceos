"""Curated and staff-uploaded knowledge store, isolated from business and checkpoint schemas.

Documents flow through an explicit pipeline (UPLOADED -> CONVERTED -> CHUNKED ->
EMBEDDED/STORED, or FAILED) driven by lease-based worker jobs. Segments are the
single chunk store for seeds, local manuals and uploads; parents carry
``skip_embedding`` and are only used to expand child hits at retrieval time.
Nothing here is a DeviceFact, a policy, or a business record.
"""

from datetime import datetime
from types import MappingProxyType
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean, CheckConstraint, Computed, DateTime, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UserDefinedType

from serviceos_api.persistence.models import Base

KNOWLEDGE_SCHEMA = "serviceos_knowledge"

# Fixed by migration 0017 (vector(1024)); changing it requires a new migration.
EMBEDDING_DIMENSIONS = 1024

DOCUMENT_STATUSES = ("UPLOADED", "CONVERTED", "CHUNKED", "EMBEDDED", "STORED", "FAILED")
SOURCE_KINDS = ("seed_corpus", "manual", "upload")
SPLIT_TYPES = ("ROW", "MARKDOWN_HEADER", "LENGTH", "IMAGE")
SHEET_SEMANTICS = ("ORDER", "DEALER", "QA", "ROW", "IMAGE")

MANUAL_APPLICABILITY = MappingProxyType({
    "diagnose-no-charge.md": ("generic_no_charge", ()),
    "a1229-ports.md": ("VERIFIED_MODEL_A1229", ("a1229",)),
    "eufy-s1-pro-heating-metric.md": ("VERIFIED_MODEL_T8D04", ("t8d04",)),
})


class Vector(UserDefinedType):
    """Minimal pgvector column type; Python values are '[0.1,...]' literals."""

    cache_ok = True

    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS):
        self.dimensions = dimensions

    def get_col_spec(self, **kw) -> str:
        return f"vector({self.dimensions})"


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        CheckConstraint("source_kind IN ('seed_corpus', 'manual', 'upload')",
                        name="ck_knowledge_documents_source_kind"),
        CheckConstraint("status IN ('UPLOADED','CONVERTED','CHUNKED','EMBEDDED','STORED','FAILED')",
                        name="ck_knowledge_documents_status"),
        CheckConstraint("split_type IN ('ROW', 'MARKDOWN_HEADER', 'LENGTH', 'IMAGE')",
                        name="ck_knowledge_documents_split_type"),
        {"schema": KNOWLEDGE_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
    source_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str | None] = mapped_column(Text)
    media_type: Mapped[str | None] = mapped_column(String(120))
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="UPLOADED")
    error_code: Mapped[str | None] = mapped_column(String(80))
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    split_type: Mapped[str] = mapped_column(String(24), nullable=False, default="ROW")
    sheet_overrides: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    uploaded_by_staff_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))


class KnowledgeDocumentVersion(Base):
    __tablename__ = "knowledge_document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version", name="uq_knowledge_document_versions_doc_version"),
        CheckConstraint("status IN ('UPLOADED','CONVERTED','CHUNKED','EMBEDDED','STORED','FAILED')",
                        name="ck_knowledge_document_versions_status"),
        {"schema": KNOWLEDGE_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{KNOWLEDGE_SCHEMA}.knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="UPLOADED")
    error_code: Mapped[str | None] = mapped_column(String(80))


class KnowledgeSegment(Base):
    __tablename__ = "knowledge_segments"
    __table_args__ = (
        UniqueConstraint("entry_key", name="uq_knowledge_segments_entry_key"),
        CheckConstraint("source_status <> ''", name="ck_knowledge_segments_source_status"),
        Index("ix_knowledge_segments_search_vector", "search_vector", postgresql_using="gin"),
        Index("ix_knowledge_segments_content_trgm", "content", postgresql_using="gin",
              postgresql_ops={"content": "gin_trgm_ops"}),
        Index("ix_knowledge_segments_models", "models", postgresql_using="gin"),
        {"schema": KNOWLEDGE_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{KNOWLEDGE_SCHEMA}.knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{KNOWLEDGE_SCHEMA}.knowledge_document_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_segment_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{KNOWLEDGE_SCHEMA}.knowledge_segments.id", ondelete="SET NULL"),
    )
    skip_embedding: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    entry_key: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # Casefolded applicable model codes; an empty list means generic material.
    models: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    directories: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    pdt: Mapped[str | None] = mapped_column(String(80))
    source_status: Mapped[str] = mapped_column(String(32), nullable=False)
    consumer_visible: Mapped[str] = mapped_column(String(32), nullable=False)
    applicability: Mapped[str] = mapped_column(String(160), nullable=False)
    curation: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Structured facets for deterministic typed-tool lookups (order/dealer/etc).
    attrs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # When set, the embedding source is this object-storage image, not the text.
    image_key: Mapped[str | None] = mapped_column(Text)
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(content, ''))",
                           persisted=True), nullable=False)


class KnowledgeEmbedding(Base):
    __tablename__ = "knowledge_embeddings"
    __table_args__ = (
        CheckConstraint(f"dimensions = {EMBEDDING_DIMENSIONS}", name="ck_knowledge_embeddings_dimensions"),
        Index("ix_knowledge_embeddings_hnsw", "embedding", postgresql_using="hnsw",
              postgresql_ops={"embedding": "vector_cosine_ops"}),
        {"schema": KNOWLEDGE_SCHEMA},
    )

    segment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{KNOWLEDGE_SCHEMA}.knowledge_segments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[str] = mapped_column(Vector(), nullable=False)
    embedded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeJob(Base):
    """Lease-driven pipeline job; mirrors the inspection job lease pattern."""

    __tablename__ = "knowledge_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('QUEUED','RUNNING','COMPLETED','FAILED')",
                        name="ck_knowledge_jobs_status"),
        UniqueConstraint("document_id", "version_id", name="uq_knowledge_jobs_doc_version"),
        Index("ix_knowledge_jobs_ready", "status", "available_at"),
        {"schema": KNOWLEDGE_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{KNOWLEDGE_SCHEMA}.knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(f"{KNOWLEDGE_SCHEMA}.knowledge_document_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="QUEUED")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    lease_owner: Mapped[str | None] = mapped_column(String(80))
    lease_token: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
