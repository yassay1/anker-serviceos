"""Customer consent and scheduled staff follow-up tasks."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0012_follow_up_jobs"
down_revision: Union[str, Sequence[str], None] = "0011_resolution_verification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
SCHEMA = "serviceos"


def common(table):
    return [
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], [f"{SCHEMA}.tenants.id"], name=f"fk_{table}_tenant_id_tenants"),
        sa.UniqueConstraint("tenant_id", "id", name=f"uq_{table}_tenant_id_id"),
    ]


def tenant_fk(table, column, target, target_column="id"):
    return sa.ForeignKeyConstraint(
        ["tenant_id", column], [f"{SCHEMA}.{target}.tenant_id", f"{SCHEMA}.{target}.{target_column}"],
        name=f"fk_{table}_{column}_{target}",
    )


def upgrade() -> None:
    op.create_table(
        "follow_up_consents", *common("follow_up_consents"),
        sa.Column("case_id", UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True), nullable=False),
        sa.Column("client_consent_id", UUID(as_uuid=True), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(1000), nullable=False),
        tenant_fk("follow_up_consents", "case_id", "service_cases"),
        tenant_fk("follow_up_consents", "customer_id", "customers"),
        sa.UniqueConstraint("tenant_id", "case_id", "client_consent_id", name="uq_follow_up_consents_tenant_id_case_id_client_consent_id"),
        schema=SCHEMA,
    )
    op.create_table(
        "follow_up_jobs", *common("follow_up_jobs"),
        sa.Column("case_id", UUID(as_uuid=True), nullable=False),
        sa.Column("consent_record_id", UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("client_follow_up_id", UUID(as_uuid=True), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("scheduled_by", UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(1000), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), server_default="SCHEDULED", nullable=False),
        sa.Column("task_id", UUID(as_uuid=True), nullable=True),
        sa.Column("reminded_at", sa.DateTime(timezone=True), nullable=True),
        tenant_fk("follow_up_jobs", "case_id", "service_cases"),
        tenant_fk("follow_up_jobs", "consent_record_id", "follow_up_consents"),
        tenant_fk("follow_up_jobs", "conversation_id", "conversations"),
        tenant_fk("follow_up_jobs", "scheduled_by", "tenant_memberships", "staff_user_id"),
        tenant_fk("follow_up_jobs", "task_id", "service_tasks"),
        sa.UniqueConstraint("tenant_id", "case_id", "client_follow_up_id", name="uq_follow_up_jobs_tenant_id_case_id_client_follow_up_id"),
        sa.UniqueConstraint("tenant_id", "consent_record_id", name="uq_follow_up_jobs_tenant_id_consent_record_id"),
        sa.CheckConstraint("status IN ('SCHEDULED','DUE','CANCELLED')", name="ck_follow_up_jobs_status_values"),
        schema=SCHEMA,
    )
    op.create_index("ix_follow_up_jobs_due", "follow_up_jobs", ["status", "due_at"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_follow_up_jobs_due", table_name="follow_up_jobs", schema=SCHEMA)
    op.drop_table("follow_up_jobs", schema=SCHEMA)
    op.drop_table("follow_up_consents", schema=SCHEMA)
