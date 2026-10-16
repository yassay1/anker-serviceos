"""Persist bounded Diagnostic Agent tasks and invocation identities."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0015_diagnostic_tasks"
down_revision: Union[str, Sequence[str], None] = "0014_experience_candidates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "serviceos"


def upgrade() -> None:
    op.create_table(
        "diagnostic_tasks",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("conversation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_message_id", UUID(as_uuid=True), nullable=False),
        sa.Column("parent_agent_run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="QUEUED", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("input_payload", JSONB(), nullable=False),
        sa.Column("result_payload", JSONB(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], [f"{SCHEMA}.tenants.id"], name="fk_diagnostic_tasks_tenant_id_tenants"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            [f"{SCHEMA}.conversations.tenant_id", f"{SCHEMA}.conversations.id"],
            name="fk_diagnostic_tasks_tenant_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_message_id"],
            [f"{SCHEMA}.messages.tenant_id", f"{SCHEMA}.messages.id"],
            name="fk_diagnostic_tasks_tenant_source_message",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_agent_run_id"],
            [f"{SCHEMA}.agent_runs.tenant_id", f"{SCHEMA}.agent_runs.id"],
            name="fk_diagnostic_tasks_tenant_parent_run",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "case_id"],
            [f"{SCHEMA}.service_cases.tenant_id", f"{SCHEMA}.service_cases.id"],
            name="fk_diagnostic_tasks_tenant_case",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_diagnostic_tasks"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_diagnostic_tasks_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "parent_agent_run_id",
                            name="uq_diagnostic_tasks_tenant_id_parent_agent_run_id"),
        sa.CheckConstraint(
            "status IN ('QUEUED','RUNNING','WAITING_CUSTOMER','WAITING_STAFF','COMPLETED','FAILED','CANCELLED','EXPIRED')",
            name="ck_diagnostic_tasks_status_values",
        ),
        sa.CheckConstraint("version >= 1", name="ck_diagnostic_tasks_version_positive"),
        schema=SCHEMA,
    )
    op.create_index("ix_diagnostic_tasks_conversation", "diagnostic_tasks",
                    ["tenant_id", "conversation_id", "created_at"], schema=SCHEMA)
    op.create_index("ix_diagnostic_tasks_status_deadline", "diagnostic_tasks",
                    ["tenant_id", "status", "expires_at"], schema=SCHEMA)

    op.create_table(
        "specialist_runs",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("diagnostic_task_id", UUID(as_uuid=True), nullable=False),
        sa.Column("parent_agent_run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("checkpoint_thread_id", sa.String(length=160), nullable=False),
        sa.Column("attempt", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(length=24), server_default="QUEUED", nullable=False),
        sa.Column("lease_token", UUID(as_uuid=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("result_payload", JSONB(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], [f"{SCHEMA}.tenants.id"], name="fk_specialist_runs_tenant_id_tenants"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "diagnostic_task_id"],
            [f"{SCHEMA}.diagnostic_tasks.tenant_id", f"{SCHEMA}.diagnostic_tasks.id"],
            name="fk_specialist_runs_tenant_diagnostic_task",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_agent_run_id"],
            [f"{SCHEMA}.agent_runs.tenant_id", f"{SCHEMA}.agent_runs.id"],
            name="fk_specialist_runs_tenant_parent_run",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_specialist_runs"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_specialist_runs_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "diagnostic_task_id", "attempt",
                            name="uq_specialist_runs_tenant_id_diagnostic_task_id_attempt"),
        sa.UniqueConstraint("tenant_id", "checkpoint_thread_id",
                            name="uq_specialist_runs_tenant_id_checkpoint_thread_id"),
        sa.CheckConstraint("status IN ('QUEUED','RUNNING','COMPLETED','FAILED','INTERRUPTED')",
                           name="ck_specialist_runs_status_values"),
        sa.CheckConstraint("attempt >= 1", name="ck_specialist_runs_attempt_positive"),
        schema=SCHEMA,
    )
    op.create_index("ix_specialist_runs_task", "specialist_runs",
                    ["tenant_id", "diagnostic_task_id", "created_at"], schema=SCHEMA)
    op.create_index(
        "uq_specialist_runs_one_active_task", "specialist_runs",
        ["tenant_id", "diagnostic_task_id"], unique=True, schema=SCHEMA,
        postgresql_where=sa.text("status IN ('QUEUED','RUNNING')"),
    )


def downgrade() -> None:
    op.drop_index("uq_specialist_runs_one_active_task", table_name="specialist_runs", schema=SCHEMA)
    op.drop_index("ix_specialist_runs_task", table_name="specialist_runs", schema=SCHEMA)
    op.drop_table("specialist_runs", schema=SCHEMA)
    op.drop_index("ix_diagnostic_tasks_status_deadline", table_name="diagnostic_tasks", schema=SCHEMA)
    op.drop_index("ix_diagnostic_tasks_conversation", table_name="diagnostic_tasks", schema=SCHEMA)
    op.drop_table("diagnostic_tasks", schema=SCHEMA)
