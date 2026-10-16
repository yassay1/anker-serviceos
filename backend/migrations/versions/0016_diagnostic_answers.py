"""Persist controlled Diagnostic Agent questions and customer answers."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0016_diagnostic_answers"
down_revision: Union[str, Sequence[str], None] = "0015_diagnostic_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "serviceos"


def upgrade() -> None:
    op.drop_constraint("uq_diagnostic_tasks_tenant_id_parent_agent_run_id", "diagnostic_tasks",
                       schema=SCHEMA, type_="unique")
    op.add_column("diagnostic_tasks", sa.Column("question_payload", JSONB(), nullable=True), schema=SCHEMA)
    op.add_column("diagnostic_tasks", sa.Column("question_revision", sa.Integer(), nullable=True), schema=SCHEMA)
    op.create_check_constraint("ck_diagnostic_tasks_question_revision_positive", "diagnostic_tasks",
                               "question_revision IS NULL OR question_revision >= 1", schema=SCHEMA)

    op.create_table(
        "diagnostic_answers",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("diagnostic_task_id", UUID(as_uuid=True), nullable=False),
        sa.Column("question_revision", sa.Integer(), nullable=False),
        sa.Column("client_action_id", UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_message_id", UUID(as_uuid=True), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], [f"{SCHEMA}.tenants.id"],
                                name="fk_diagnostic_answers_tenant_id_tenants"),
        sa.ForeignKeyConstraint(["tenant_id", "diagnostic_task_id"],
                                [f"{SCHEMA}.diagnostic_tasks.tenant_id", f"{SCHEMA}.diagnostic_tasks.id"],
                                name="fk_diagnostic_answers_tenant_diagnostic_task"),
        sa.ForeignKeyConstraint(["tenant_id", "source_message_id"],
                                [f"{SCHEMA}.messages.tenant_id", f"{SCHEMA}.messages.id"],
                                name="fk_diagnostic_answers_tenant_source_message"),
        sa.ForeignKeyConstraint(["tenant_id", "customer_id"],
                                [f"{SCHEMA}.customers.tenant_id", f"{SCHEMA}.customers.id"],
                                name="fk_diagnostic_answers_tenant_customer"),
        sa.PrimaryKeyConstraint("id", name="pk_diagnostic_answers"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_diagnostic_answers_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "diagnostic_task_id", "question_revision",
                            name="uq_diag_answer_question_revision"),
        sa.UniqueConstraint("tenant_id", "client_action_id", name="uq_diag_answer_client_action"),
        sa.CheckConstraint("question_revision >= 1", name="ck_diagnostic_answers_question_revision_positive"),
        schema=SCHEMA,
    )
    op.create_index("ix_diagnostic_answers_message", "diagnostic_answers",
                    ["tenant_id", "source_message_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_diagnostic_answers_message", table_name="diagnostic_answers", schema=SCHEMA)
    op.drop_table("diagnostic_answers", schema=SCHEMA)
    op.drop_constraint("ck_diagnostic_tasks_question_revision_positive", "diagnostic_tasks",
                       schema=SCHEMA, type_="check")
    op.drop_column("diagnostic_tasks", "question_revision", schema=SCHEMA)
    op.drop_column("diagnostic_tasks", "question_payload", schema=SCHEMA)
    op.create_unique_constraint("uq_diagnostic_tasks_tenant_id_parent_agent_run_id", "diagnostic_tasks",
                                ["tenant_id", "parent_agent_run_id"], schema=SCHEMA)
