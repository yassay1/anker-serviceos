"""Persist diagnostic specialist authorship on conversation messages."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0019_specialist_author_messages"
down_revision: Union[str, Sequence[str], None] = "0018_loop_guard"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "serviceos"


def upgrade() -> None:
    op.add_column("messages", sa.Column("specialist_run_id", UUID(as_uuid=True), nullable=True), schema=SCHEMA)
    op.create_foreign_key(
        op.f("fk_messages_tenant_specialist_run"), "messages", "specialist_runs",
        ["tenant_id", "specialist_run_id"], ["tenant_id", "id"], source_schema=SCHEMA, referent_schema=SCHEMA,
    )
    op.create_unique_constraint(
        op.f("uq_messages_tenant_id_specialist_run_id"), "messages", ["tenant_id", "specialist_run_id"], schema=SCHEMA,
    )
    op.drop_constraint(op.f("ck_messages_author_identity"), "messages", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        op.f("ck_messages_author_identity"), "messages",
        "(author_kind = 'CUSTOMER' AND author_customer_id IS NOT NULL AND author_staff_id IS NULL "
        "AND specialist_run_id IS NULL AND visibility = 'PUBLIC') OR "
        "(author_kind = 'STAFF' AND author_staff_id IS NOT NULL AND author_customer_id IS NULL "
        "AND specialist_run_id IS NULL) OR "
        "(author_kind IN ('AGENT','SYSTEM') AND author_customer_id IS NULL AND author_staff_id IS NULL "
        "AND specialist_run_id IS NULL) OR "
        "(author_kind = 'SPECIALIST' AND author_customer_id IS NULL AND author_staff_id IS NULL "
        "AND specialist_run_id IS NOT NULL)",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_messages_author_identity"), "messages", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        op.f("ck_messages_author_identity"), "messages",
        "(author_kind = 'CUSTOMER' AND author_customer_id IS NOT NULL AND author_staff_id IS NULL "
        "AND visibility = 'PUBLIC') OR "
        "(author_kind = 'STAFF' AND author_staff_id IS NOT NULL AND author_customer_id IS NULL) OR "
        "(author_kind IN ('AGENT','SYSTEM') AND author_customer_id IS NULL AND author_staff_id IS NULL)",
        schema=SCHEMA,
    )
    op.drop_constraint(op.f("uq_messages_tenant_id_specialist_run_id"), "messages", schema=SCHEMA, type_="unique")
    op.drop_constraint(op.f("fk_messages_tenant_specialist_run"), "messages", schema=SCHEMA, type_="foreignkey")
    op.drop_column("messages", "specialist_run_id", schema=SCHEMA)
