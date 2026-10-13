"""Human tasks, assignments, and review metadata."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0006_collaboration"
down_revision: Union[str, Sequence[str], None] = "0005_agent_result"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "service_tasks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", UUID(as_uuid=True)),
        sa.Column("requester_customer_id", UUID(as_uuid=True)),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), server_default="OPEN", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["serviceos.tenants.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "conversation_id"], ["serviceos.conversations.tenant_id", "serviceos.conversations.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "case_id"], ["serviceos.service_cases.tenant_id", "serviceos.service_cases.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "requester_customer_id"], ["serviceos.customers.tenant_id", "serviceos.customers.id"]),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.CheckConstraint("status IN ('OPEN','ASSIGNED','CLOSED')", name="ck_service_tasks_status_values"),
        sa.CheckConstraint("version >= 1", name="ck_service_tasks_version_positive"),
        schema="serviceos",
    )
    op.create_index("ix_service_tasks_conversation", "service_tasks", ["tenant_id", "conversation_id", "created_at"], schema="serviceos")
    op.create_table(
        "task_assignments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", UUID(as_uuid=True), nullable=False),
        sa.Column("staff_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["tenant_id"], ["serviceos.tenants.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "task_id"], ["serviceos.service_tasks.tenant_id", "serviceos.service_tasks.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "staff_user_id"], ["serviceos.tenant_memberships.tenant_id", "serviceos.tenant_memberships.staff_user_id"]),
        sa.UniqueConstraint("tenant_id", "id"),
        schema="serviceos",
    )
    op.create_index("uq_task_assignments_active", "task_assignments", ["tenant_id", "task_id"],
                    unique=True, postgresql_where=sa.text("ended_at IS NULL"), schema="serviceos")
    for name, kind in (("decision_key", UUID(as_uuid=True)), ("decision_hash", sa.String(64)),
                       ("decided_by", UUID(as_uuid=True)), ("decision_reason", sa.Text())):
        op.add_column("agent_proposals", sa.Column(name, kind), schema="serviceos")


def downgrade() -> None:
    for name in ("decision_reason", "decided_by", "decision_hash", "decision_key"):
        op.drop_column("agent_proposals", name, schema="serviceos")
    op.drop_index("uq_task_assignments_active", table_name="task_assignments", schema="serviceos")
    op.drop_table("task_assignments", schema="serviceos")
    op.drop_index("ix_service_tasks_conversation", table_name="service_tasks", schema="serviceos")
    op.drop_table("service_tasks", schema="serviceos")
