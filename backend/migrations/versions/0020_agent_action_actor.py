"""Record AgentRun as the requester for mock service actions."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0020_agent_action_actor"
down_revision: Union[str, Sequence[str], None] = "0019_specialist_author_messages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "serviceos"


def upgrade() -> None:
    op.add_column("case_actions", sa.Column("requested_by_agent_run_id", UUID(as_uuid=True), nullable=True),
                  schema=SCHEMA)
    op.alter_column("case_actions", "requested_by", existing_type=UUID(as_uuid=True), nullable=True,
                    schema=SCHEMA)
    op.create_foreign_key(
        "fk_case_actions_tenant_requested_by_agent_run", "case_actions", "agent_runs",
        ["tenant_id", "requested_by_agent_run_id"], ["tenant_id", "id"],
        source_schema=SCHEMA, referent_schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_case_actions_requester_identity", "case_actions",
        "(requested_by IS NOT NULL AND requested_by_agent_run_id IS NULL) OR "
        "(requested_by IS NULL AND requested_by_agent_run_id IS NOT NULL)",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint("ck_case_actions_requester_identity", "case_actions", schema=SCHEMA, type_="check")
    op.drop_constraint("fk_case_actions_tenant_requested_by_agent_run", "case_actions", schema=SCHEMA,
                       type_="foreignkey")
    op.drop_column("case_actions", "requested_by_agent_run_id", schema=SCHEMA)
    op.alter_column("case_actions", "requested_by", existing_type=UUID(as_uuid=True), nullable=False,
                    schema=SCHEMA)
