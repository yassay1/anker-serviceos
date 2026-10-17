"""Persistent audited staff reply drafts for interaction alignment."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0021_interaction_align"
down_revision: Union[str, Sequence[str], None] = "0020_agent_action_actor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "serviceos"


def upgrade() -> None:
    op.create_table(
        "staff_reply_drafts",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_proposal_id", UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), server_default="IN_COMPOSER", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("approval_key", UUID(as_uuid=True), nullable=True),
        sa.Column("approval_hash", sa.String(64), nullable=True),
        sa.Column("approved_by", UUID(as_uuid=True), nullable=True),
        sa.Column("send_key", UUID(as_uuid=True), nullable=True),
        sa.Column("send_hash", sa.String(64), nullable=True),
        sa.Column("sent_message_id", UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_staff_reply_drafts"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_staff_reply_drafts_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "id", "approval_key", name="uq_staff_reply_drafts_tenant_id_id_approval_key"),
        sa.UniqueConstraint("tenant_id", "id", "send_key", name="uq_staff_reply_drafts_tenant_id_id_send_key"),
        sa.ForeignKeyConstraint(["tenant_id"], [f"{SCHEMA}.tenants.id"], name="fk_staff_reply_drafts_tenant_id_tenants"),
        sa.ForeignKeyConstraint(["tenant_id", "conversation_id"], [f"{SCHEMA}.conversations.tenant_id", f"{SCHEMA}.conversations.id"], name="fk_staff_reply_drafts_tenant_id_conversations"),
        sa.ForeignKeyConstraint(["tenant_id", "source_proposal_id"], [f"{SCHEMA}.agent_proposals.tenant_id", f"{SCHEMA}.agent_proposals.id"], name="fk_staff_reply_drafts_tenant_id_agent_proposals"),
        sa.ForeignKeyConstraint(["tenant_id", "created_by"], [f"{SCHEMA}.tenant_memberships.tenant_id", f"{SCHEMA}.tenant_memberships.staff_user_id"], name="fk_staff_reply_drafts_tenant_id_tenant_memberships_created_by"),
        sa.ForeignKeyConstraint(["tenant_id", "approved_by"], [f"{SCHEMA}.tenant_memberships.tenant_id", f"{SCHEMA}.tenant_memberships.staff_user_id"], name="fk_staff_reply_drafts_tenant_id_tenant_memberships_approved_by"),
        sa.ForeignKeyConstraint(["tenant_id", "sent_message_id"], [f"{SCHEMA}.messages.tenant_id", f"{SCHEMA}.messages.id"], name="fk_staff_reply_drafts_tenant_id_messages"),
        sa.CheckConstraint("status IN ('IN_COMPOSER','EDITED','APPROVED','SENT')", name="ck_staff_reply_drafts_status_values"),
        sa.CheckConstraint("version >= 1", name="ck_staff_reply_drafts_version_positive"),
        sa.CheckConstraint("(approval_key IS NULL) = (approval_hash IS NULL)", name="ck_staff_reply_drafts_approval_pair"),
        sa.CheckConstraint("(send_key IS NULL) = (send_hash IS NULL)", name="ck_staff_reply_drafts_send_pair"),
        schema=SCHEMA,
    )
    op.create_index("ix_staff_reply_drafts_conversation", "staff_reply_drafts",
                    ["tenant_id", "conversation_id", "created_at"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_staff_reply_drafts_conversation", table_name="staff_reply_drafts", schema=SCHEMA)
    op.drop_table("staff_reply_drafts", schema=SCHEMA)
