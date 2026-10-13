"""Make exhausted Outbox delivery visible as a terminal state."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_outbox_dead_letter"
down_revision: Union[str, Sequence[str], None] = "0003_agent_worker_runtime"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("outbox_events", sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True), schema="serviceos")


def downgrade() -> None:
    op.drop_column("outbox_events", "dead_lettered_at", schema="serviceos")
