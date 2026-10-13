"""Versioned UI projections and audited low-risk intents."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0007_ui_documents"
down_revision: Union[str, Sequence[str], None] = "0006_collaboration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ui_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("ui_id", UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("schema_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("catalog_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("surface", sa.String(32), nullable=False),
        sa.Column("audience", sa.String(16), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False),
        sa.Column("source_agent_run_id", UUID(as_uuid=True)),
        sa.Column("context_signature", sa.String(64), nullable=False),
        sa.Column("components", JSONB(), nullable=False),
        sa.Column("fallback_text", sa.String(500), nullable=False),
        sa.Column("status", sa.String(24), server_default="ACTIVE", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["tenant_id"], ["serviceos.tenants.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "conversation_id"], ["serviceos.conversations.tenant_id", "serviceos.conversations.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "source_agent_run_id"], ["serviceos.agent_runs.tenant_id", "serviceos.agent_runs.id"]),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("tenant_id", "ui_id", "revision"),
        sa.CheckConstraint("revision >= 1", name="ck_ui_documents_revision_positive"),
        sa.CheckConstraint("audience IN ('CUSTOMER','STAFF')", name="ck_ui_documents_audience_values"),
        sa.CheckConstraint("visibility IN ('PUBLIC','INTERNAL')", name="ck_ui_documents_visibility_values"),
        sa.CheckConstraint("status IN ('ACTIVE','SUPERSEDED','EXPIRED','INVALID')", name="ck_ui_documents_status_values"),
        schema="serviceos",
    )
    op.create_index("uq_ui_documents_active", "ui_documents",
                    ["tenant_id", "conversation_id", "audience"], unique=True,
                    postgresql_where=sa.text("status = 'ACTIVE'"), schema="serviceos")
    op.create_table(
        "ui_action_invocations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("ui_document_id", UUID(as_uuid=True), nullable=False),
        sa.Column("client_action_id", UUID(as_uuid=True), nullable=False),
        sa.Column("actor_kind", sa.String(16), nullable=False),
        sa.Column("actor_id", UUID(as_uuid=True), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("action_id", sa.String(80), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("task_id", UUID(as_uuid=True)),
        sa.Column("result", JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["serviceos.tenants.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "ui_document_id"], ["serviceos.ui_documents.tenant_id", "serviceos.ui_documents.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "task_id"], ["serviceos.service_tasks.tenant_id", "serviceos.service_tasks.id"]),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("tenant_id", "actor_kind", "actor_id", "client_action_id"),
        sa.CheckConstraint("actor_kind IN ('CUSTOMER','STAFF')", name="ck_ui_action_invocations_actor_values"),
        sa.CheckConstraint("status IN ('ACCEPTED','REJECTED')", name="ck_ui_action_invocations_status_values"),
        schema="serviceos",
    )


def downgrade() -> None:
    op.drop_table("ui_action_invocations", schema="serviceos")
    op.drop_index("uq_ui_documents_active", table_name="ui_documents", schema="serviceos")
    op.drop_table("ui_documents", schema="serviceos")
