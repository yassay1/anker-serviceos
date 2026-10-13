"""Persist the separated internal Agent result."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0005_agent_result"
down_revision: Union[str, Sequence[str], None] = "0004_outbox_dead_letter"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("result_payload", JSONB(), nullable=True), schema="serviceos")


def downgrade() -> None:
    op.drop_column("agent_runs", "result_payload", schema="serviceos")
