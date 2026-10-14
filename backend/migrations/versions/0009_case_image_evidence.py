"""Controlled image evidence and local inspection jobs."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0009_case_image_evidence"
down_revision: Union[str, Sequence[str], None] = "0008_reply_review"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "serviceos"


def upgrade() -> None:
    op.create_table(
        "case_image_evidence",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", UUID(as_uuid=True), nullable=False),
        sa.Column("client_evidence_id", UUID(as_uuid=True), nullable=False),
        sa.Column("file_digest", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("visibility", sa.String(16), server_default="PUBLIC", nullable=False),
        sa.Column("media_type", sa.String(32), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("inspection_status", sa.String(16), server_default="PENDING", nullable=False),
        sa.Column("verification", sa.String(16), server_default="UNVERIFIED", nullable=False),
        sa.Column("source_kind", sa.String(16), nullable=False),
        sa.Column("author_customer_id", UUID(as_uuid=True)),
        sa.Column("author_staff_id", UUID(as_uuid=True)),
        sa.Column("storage_key", sa.String(160)),
        sa.Column("rejection_code", sa.String(80)),
        sa.CheckConstraint("visibility IN ('PUBLIC','INTERNAL')", name="ck_case_image_evidence_visibility_values"),
        sa.CheckConstraint("media_type IN ('image/jpeg','image/png','image/webp')", name="ck_case_image_evidence_media_values"),
        sa.CheckConstraint("byte_size >= 1 AND byte_size <= 10485760", name="ck_case_image_evidence_byte_size_bounds"),
        sa.CheckConstraint("inspection_status IN ('PENDING','CLEAN','REJECTED')", name="ck_case_image_evidence_inspection_values"),
        sa.CheckConstraint("verification IN ('UNVERIFIED','VERIFIED','RETRACTED')", name="ck_case_image_evidence_verification_values"),
        sa.CheckConstraint("source_kind IN ('CUSTOMER','STAFF')", name="ck_case_image_evidence_source_values"),
        sa.CheckConstraint(
            "(source_kind = 'CUSTOMER' AND author_customer_id IS NOT NULL AND author_staff_id IS NULL) OR "
            "(source_kind = 'STAFF' AND author_staff_id IS NOT NULL AND author_customer_id IS NULL)",
            name="ck_case_image_evidence_author_identity",
        ),
        sa.CheckConstraint(
            "(inspection_status = 'REJECTED' AND rejection_code IS NOT NULL) OR "
            "(inspection_status IN ('PENDING','CLEAN') AND rejection_code IS NULL AND storage_key IS NOT NULL)",
            name="ck_case_image_evidence_inspection_payload",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], [f"{SCHEMA}.tenants.id"], name="fk_case_image_evidence_tenant_id_tenants"),
        sa.ForeignKeyConstraint(["tenant_id", "case_id"], [f"{SCHEMA}.service_cases.tenant_id", f"{SCHEMA}.service_cases.id"],
                                name="fk_case_image_evidence_tenant_id_service_cases"),
        sa.ForeignKeyConstraint(["tenant_id", "author_customer_id"], [f"{SCHEMA}.customers.tenant_id", f"{SCHEMA}.customers.id"],
                                name="fk_case_image_evidence_tenant_id_customers"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "author_staff_id"],
            [f"{SCHEMA}.tenant_memberships.tenant_id", f"{SCHEMA}.tenant_memberships.staff_user_id"],
            name="fk_case_image_evidence_tenant_id_tenant_memberships",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_case_image_evidence_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "case_id", "client_evidence_id",
                            name="uq_case_image_evidence_tenant_id_case_id_client_evidence_id"),
        schema=SCHEMA,
    )
    op.create_index("ix_case_image_evidence_case", "case_image_evidence",
                    ["tenant_id", "case_id", "created_at", "id"], schema=SCHEMA)
    op.create_table(
        "evidence_inspection_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_id", UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(24), server_default="QUEUED", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="5", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("lease_owner", sa.String(120)),
        sa.Column("lease_token", UUID(as_uuid=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(80)),
        sa.CheckConstraint("status IN ('QUEUED','RUNNING','COMPLETED','FAILED')", name="ck_evidence_inspection_jobs_status_values"),
        sa.CheckConstraint(
            "attempt_count >= 0 AND max_attempts >= 1 AND attempt_count <= max_attempts",
            name="ck_evidence_inspection_jobs_attempt_bounds",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], [f"{SCHEMA}.tenants.id"], name="fk_evidence_inspection_jobs_tenant_id_tenants"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "evidence_id"],
            [f"{SCHEMA}.case_image_evidence.tenant_id", f"{SCHEMA}.case_image_evidence.id"],
            name="fk_evidence_inspection_jobs_tenant_id_case_image_evidence",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_evidence_inspection_jobs_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "evidence_id", name="uq_evidence_inspection_jobs_tenant_id_evidence_id"),
        schema=SCHEMA,
    )
    op.create_index("ix_evidence_inspection_jobs_ready", "evidence_inspection_jobs",
                    ["status", "available_at", "created_at"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_evidence_inspection_jobs_ready", table_name="evidence_inspection_jobs", schema=SCHEMA)
    op.drop_table("evidence_inspection_jobs", schema=SCHEMA)
    op.drop_index("ix_case_image_evidence_case", table_name="case_image_evidence", schema=SCHEMA)
    op.drop_table("case_image_evidence", schema=SCHEMA)
