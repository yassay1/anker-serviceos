"""Isolated knowledge pipeline schema: documents, versions, segments, embeddings, jobs."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0017_knowledge_retrieval"
down_revision: Union[str, Sequence[str], None] = "0016_diagnostic_answers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "serviceos_knowledge"
DIMENSIONS = 1024
DOCUMENT_STATUS_CHECK = "status IN ('UPLOADED','CONVERTED','CHUNKED','EMBEDDED','STORED','FAILED')"


class _Vector(sa.types.UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kw) -> str:
        return f"vector({DIMENSIONS})"


def upgrade() -> None:
    # Requires a role allowed to create extensions; on RDS see docs/operations.md.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(sa.schema.CreateSchema(SCHEMA))
    op.create_table(
        "knowledge_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("source_kind", sa.String(length=24), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=True),
        sa.Column("media_type", sa.String(length=120), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("split_type", sa.String(length=24), nullable=False),
        sa.Column("sheet_overrides", JSONB(), nullable=False),
        sa.Column("uploaded_by_staff_id", UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint("content_hash", name="uq_knowledge_documents_content_hash"),
        sa.CheckConstraint("source_kind IN ('seed_corpus', 'manual', 'upload')",
                           name=op.f("ck_knowledge_documents_source_kind")),
        sa.CheckConstraint(DOCUMENT_STATUS_CHECK, name=op.f("ck_knowledge_documents_status")),
        sa.CheckConstraint("split_type IN ('ROW', 'MARKDOWN_HEADER', 'LENGTH', 'IMAGE')",
                           name=op.f("ck_knowledge_documents_split_type")),
        schema=SCHEMA,
    )
    op.create_table(
        "knowledge_document_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("document_id", UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.UniqueConstraint("document_id", "version", name="uq_knowledge_document_versions_doc_version"),
        sa.CheckConstraint(DOCUMENT_STATUS_CHECK, name=op.f("ck_knowledge_document_versions_status")),
        sa.ForeignKeyConstraint(
            ["document_id"], [f"{SCHEMA}.knowledge_documents.id"],
            name="fk_knowledge_document_versions_document_id_knowledge_documents", ondelete="CASCADE",
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "knowledge_segments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("document_id", UUID(as_uuid=True), nullable=False),
        sa.Column("version_id", UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("parent_segment_id", UUID(as_uuid=True), nullable=True),
        sa.Column("skip_embedding", sa.Boolean(), nullable=False),
        sa.Column("entry_key", sa.String(length=160), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("models", JSONB(), nullable=False),
        sa.Column("directories", JSONB(), nullable=False),
        sa.Column("pdt", sa.String(length=80), nullable=True),
        sa.Column("source_status", sa.String(length=32), nullable=False),
        sa.Column("consumer_visible", sa.String(length=32), nullable=False),
        sa.Column("applicability", sa.String(length=160), nullable=False),
        sa.Column("curation", JSONB(), nullable=False),
        sa.Column("attrs", JSONB(), nullable=False),
        sa.Column("image_key", sa.Text(), nullable=True),
        sa.Column("search_vector", postgresql.TSVECTOR, sa.Computed(
            "to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(content, ''))",
            persisted=True), nullable=False),
        sa.UniqueConstraint("entry_key", name="uq_knowledge_segments_entry_key"),
        sa.CheckConstraint("source_status <> ''", name=op.f("ck_knowledge_segments_source_status")),
        sa.ForeignKeyConstraint(
            ["document_id"], [f"{SCHEMA}.knowledge_documents.id"],
            name="fk_knowledge_segments_document_id_knowledge_documents", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"], [f"{SCHEMA}.knowledge_document_versions.id"],
            name="fk_knowledge_segments_version_id_knowledge_document_versions", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_segment_id"], [f"{SCHEMA}.knowledge_segments.id"],
            name="fk_knowledge_segments_parent_segment_id_knowledge_segments", ondelete="SET NULL",
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "knowledge_embeddings",
        sa.Column("segment_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding", _Vector(), nullable=False),
        sa.Column("embedded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["segment_id"], [f"{SCHEMA}.knowledge_segments.id"],
            name="fk_knowledge_embeddings_segment_id_knowledge_segments", ondelete="CASCADE",
        ),
        sa.CheckConstraint(f"dimensions = {DIMENSIONS}", name=op.f("ck_knowledge_embeddings_dimensions")),
        schema=SCHEMA,
    )
    op.create_table(
        "knowledge_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("document_id", UUID(as_uuid=True), nullable=False),
        sa.Column("version_id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("lease_owner", sa.String(length=80), nullable=True),
        sa.Column("lease_token", UUID(as_uuid=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.UniqueConstraint("document_id", "version_id", name="uq_knowledge_jobs_doc_version"),
        sa.CheckConstraint("status IN ('QUEUED','RUNNING','COMPLETED','FAILED')",
                           name=op.f("ck_knowledge_jobs_status")),
        sa.ForeignKeyConstraint(
            ["document_id"], [f"{SCHEMA}.knowledge_documents.id"],
            name="fk_knowledge_jobs_document_id_knowledge_documents", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"], [f"{SCHEMA}.knowledge_document_versions.id"],
            name="fk_knowledge_jobs_version_id_knowledge_document_versions", ondelete="CASCADE",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_knowledge_segments_search_vector", "knowledge_segments", ["search_vector"],
                    postgresql_using="gin", schema=SCHEMA)
    op.create_index("ix_knowledge_segments_content_trgm", "knowledge_segments", ["content"],
                    postgresql_using="gin", postgresql_ops={"content": "gin_trgm_ops"}, schema=SCHEMA)
    op.create_index("ix_knowledge_segments_models", "knowledge_segments", ["models"],
                    postgresql_using="gin", schema=SCHEMA)
    op.create_index("ix_knowledge_jobs_ready", "knowledge_jobs", ["status", "available_at"], schema=SCHEMA)
    op.create_index("ix_knowledge_embeddings_hnsw", "knowledge_embeddings", ["embedding"],
                    postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"}, schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("knowledge_jobs", schema=SCHEMA)
    op.drop_table("knowledge_embeddings", schema=SCHEMA)
    op.drop_table("knowledge_segments", schema=SCHEMA)
    op.drop_table("knowledge_document_versions", schema=SCHEMA)
    op.drop_table("knowledge_documents", schema=SCHEMA)
    op.execute(sa.schema.DropSchema(SCHEMA))
