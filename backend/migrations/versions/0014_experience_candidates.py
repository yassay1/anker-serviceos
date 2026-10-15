"""Add reviewable, source-linked service experience candidates."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0014_experience_candidates"
down_revision: Union[str, Sequence[str], None] = "0013_case_fact_archive"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "serviceos"


def upgrade() -> None:
    op.create_table(
        "experience_candidates",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("source_case_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_verification_id", UUID(as_uuid=True), nullable=False),
        sa.Column("content", JSONB(), nullable=True),
        sa.Column("status", sa.String(length=24), server_default="DRAFT", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("authored_by", UUID(as_uuid=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], [f"{SCHEMA}.tenants.id"], name="fk_experience_candidates_tenant_id_tenants"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_case_id"], [f"{SCHEMA}.service_cases.tenant_id", f"{SCHEMA}.service_cases.id"],
            name="fk_experience_candidates_tenant_id_service_cases",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_verification_id"],
            [f"{SCHEMA}.case_verifications.tenant_id", f"{SCHEMA}.case_verifications.id"],
            name="fk_experience_candidates_tenant_id_case_verifications",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "authored_by"], [f"{SCHEMA}.tenant_memberships.tenant_id", f"{SCHEMA}.tenant_memberships.staff_user_id"],
            name="fk_experience_candidates_tenant_id_tenant_memberships",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_experience_candidates"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_experience_candidates_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "source_verification_id",
                            name="uq_experience_candidates_tenant_id_source_verification_id"),
        sa.CheckConstraint(
            "status IN ('DRAFT','PENDING_REVIEW','APPROVED','REJECTED','REVOKED')",
            name="ck_experience_candidates_status_values",
        ),
        sa.CheckConstraint("version >= 1", name="ck_experience_candidates_version_positive"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_experience_candidates_status", "experience_candidates", ["tenant_id", "status", "updated_at"], schema=SCHEMA,
    )
    # Existing verified resolutions become empty drafts; customer text is not copied.
    op.execute(sa.text(f"""
        INSERT INTO {SCHEMA}.experience_candidates
            (id, tenant_id, created_at, updated_at, source_case_id, source_verification_id,
             content, status, version)
        SELECT gen_random_uuid(), v.tenant_id, now(), now(), v.case_id, v.id, NULL, 'DRAFT', 1
        FROM {SCHEMA}.case_verifications AS v
        JOIN {SCHEMA}.service_cases AS c
          ON c.tenant_id = v.tenant_id AND c.id = v.case_id
        WHERE v.decision = 'VERIFIED_RESOLVED' AND c.status IN ('RESOLVED','CLOSED')
          AND NOT EXISTS (
              SELECT 1 FROM {SCHEMA}.case_verifications AS newer
              WHERE newer.tenant_id = v.tenant_id AND newer.case_id = v.case_id
                AND (newer.created_at, newer.id) > (v.created_at, v.id)
          )
        ON CONFLICT (tenant_id, source_verification_id) DO NOTHING
    """))
    op.create_table(
        "experience_reviews",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("candidate_id", UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_id", UUID(as_uuid=True), nullable=False),
        sa.Column("decision_id", UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_version", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], [f"{SCHEMA}.tenants.id"], name="fk_experience_reviews_tenant_id_tenants"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "candidate_id"],
            [f"{SCHEMA}.experience_candidates.tenant_id", f"{SCHEMA}.experience_candidates.id"],
            name="fk_experience_reviews_tenant_id_experience_candidates",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "reviewer_id"], [f"{SCHEMA}.tenant_memberships.tenant_id", f"{SCHEMA}.tenant_memberships.staff_user_id"],
            name="fk_experience_reviews_tenant_id_tenant_memberships",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_experience_reviews"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_experience_reviews_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "candidate_id", "decision_id",
                            name="uq_experience_reviews_tenant_id_candidate_id_decision_id"),
        sa.CheckConstraint("decision IN ('APPROVED','REJECTED','REVOKED')", name="ck_experience_reviews_decision_values"),
        sa.CheckConstraint("candidate_version >= 1", name="ck_experience_reviews_candidate_version_positive"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("experience_reviews", schema=SCHEMA)
    op.drop_index("ix_experience_candidates_status", table_name="experience_candidates", schema=SCHEMA)
    op.drop_table("experience_candidates", schema=SCHEMA)
