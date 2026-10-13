"""Reliable worker leases, audit records, proposals and conversation events."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_agent_worker_runtime"
down_revision: Union[str, Sequence[str], None] = "0002_reliable_intake"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "serviceos"


def upgrade() -> None:
    for table, max_attempts in (("message_jobs", 5), ("outbox_events", 8)):
        op.add_column(table, sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False), schema=SCHEMA)
        op.add_column(table, sa.Column("max_attempts", sa.Integer(), server_default=str(max_attempts), nullable=False), schema=SCHEMA)
        op.add_column(table, sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), schema=SCHEMA)
        op.add_column(table, sa.Column("lease_owner", sa.String(length=120), nullable=True), schema=SCHEMA)
        op.add_column(table, sa.Column("lease_token", postgresql.UUID(as_uuid=True), nullable=True), schema=SCHEMA)
        op.add_column(table, sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)
        op.add_column(table, sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)
        op.add_column(table, sa.Column("last_error_code", sa.String(length=80), nullable=True), schema=SCHEMA)
        op.create_check_constraint(f"ck_{table}_attempt_bounds", table,
                                   "attempt_count >= 0 AND max_attempts >= 1 AND attempt_count <= max_attempts", schema=SCHEMA)
    op.add_column("message_jobs", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)
    op.create_index("ix_message_jobs_ready", "message_jobs", ["status", "available_at", "created_at"], schema=SCHEMA)
    op.create_index("ix_outbox_events_ready", "outbox_events", ["published_at", "available_at", "created_at"], schema=SCHEMA)

    op.create_table(
        "agent_runs",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thread_id", sa.String(length=160), nullable=False),
        sa.Column("lease_token", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="RUNNING", nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("step_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("result_text", sa.Text(), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('RUNNING','WAITING_APPROVAL','COMPLETED','FAILED','CANCELLED')", name="ck_agent_runs_status_values"),
        sa.CheckConstraint("step_count >= 0", name="ck_agent_runs_steps_nonnegative"),
        sa.ForeignKeyConstraint(["tenant_id", "job_id"], ["serviceos.message_jobs.tenant_id", "serviceos.message_jobs.id"], name="fk_agent_runs_tenant_id_message_jobs"),
        sa.ForeignKeyConstraint(["tenant_id", "conversation_id"], ["serviceos.conversations.tenant_id", "serviceos.conversations.id"], name="fk_agent_runs_tenant_id_conversations"),
        sa.ForeignKeyConstraint(["tenant_id", "message_id"], ["serviceos.messages.tenant_id", "serviceos.messages.id"], name="fk_agent_runs_tenant_id_messages"),
        sa.ForeignKeyConstraint(["tenant_id"], ["serviceos.tenants.id"], name="fk_agent_runs_tenant_id_tenants"),
        sa.PrimaryKeyConstraint("id", name="pk_agent_runs"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_agent_runs_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "message_id", name="uq_agent_runs_tenant_id_message_id"),
        schema=SCHEMA,
    )
    op.create_index("ix_agent_runs_conversation", "agent_runs", ["tenant_id", "conversation_id", "created_at"], schema=SCHEMA)

    op.create_table(
        "agent_proposals",
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("proposal_type", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="DRAFT", nullable=False),
        sa.Column("visibility", sa.String(length=16), server_default="INTERNAL", nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("proposal_type IN ('MISSING_EVIDENCE','ACTION')", name="ck_agent_proposals_type_values"),
        sa.CheckConstraint("status IN ('DRAFT','APPROVED','REJECTED')", name="ck_agent_proposals_status_values"),
        sa.CheckConstraint("visibility = 'INTERNAL'", name="ck_agent_proposals_internal_only"),
        sa.ForeignKeyConstraint(["tenant_id", "agent_run_id"], ["serviceos.agent_runs.tenant_id", "serviceos.agent_runs.id"], name="fk_agent_proposals_tenant_id_agent_runs"),
        sa.ForeignKeyConstraint(["tenant_id", "conversation_id"], ["serviceos.conversations.tenant_id", "serviceos.conversations.id"], name="fk_agent_proposals_tenant_id_conversations"),
        sa.ForeignKeyConstraint(["tenant_id"], ["serviceos.tenants.id"], name="fk_agent_proposals_tenant_id_tenants"),
        sa.PrimaryKeyConstraint("id", name="pk_agent_proposals"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_agent_proposals_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "agent_run_id", "idempotency_key", name="uq_agent_proposals_tenant_id_agent_run_id_idempotency_key"),
        schema=SCHEMA,
    )

    op.create_table(
        "conversation_events",
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column("visibility", sa.String(length=16), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("sequence >= 1", name="ck_conversation_events_sequence_positive"),
        sa.CheckConstraint("visibility IN ('PUBLIC','INTERNAL')", name="ck_conversation_events_visibility_values"),
        sa.ForeignKeyConstraint(["tenant_id", "conversation_id"], ["serviceos.conversations.tenant_id", "serviceos.conversations.id"], name="fk_conversation_events_tenant_id_conversations"),
        sa.ForeignKeyConstraint(["tenant_id"], ["serviceos.tenants.id"], name="fk_conversation_events_tenant_id_tenants"),
        sa.PrimaryKeyConstraint("id", name="pk_conversation_events"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_conversation_events_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "conversation_id", "sequence", name="uq_conversation_events_tenant_id_conversation_id_sequence"),
        schema=SCHEMA,
    )
    op.create_index("ix_conversation_events_replay", "conversation_events", ["tenant_id", "conversation_id", "sequence"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_conversation_events_replay", table_name="conversation_events", schema=SCHEMA)
    op.drop_table("conversation_events", schema=SCHEMA)
    op.drop_table("agent_proposals", schema=SCHEMA)
    op.drop_index("ix_agent_runs_conversation", table_name="agent_runs", schema=SCHEMA)
    op.drop_table("agent_runs", schema=SCHEMA)
    op.drop_index("ix_outbox_events_ready", table_name="outbox_events", schema=SCHEMA)
    op.drop_index("ix_message_jobs_ready", table_name="message_jobs", schema=SCHEMA)
    op.drop_column("message_jobs", "completed_at", schema=SCHEMA)
    for table in ("outbox_events", "message_jobs"):
        op.drop_constraint(f"ck_{table}_attempt_bounds", table, type_="check", schema=SCHEMA)
        for column in ("last_error_code", "heartbeat_at", "lease_expires_at", "lease_token", "lease_owner", "available_at", "max_attempts", "attempt_count"):
            op.drop_column(table, column, schema=SCHEMA)
