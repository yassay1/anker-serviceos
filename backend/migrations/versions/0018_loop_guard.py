"""Policy registry, publication guard decisions and remedy outcome taxonomy."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0018_loop_guard"
down_revision: Union[str, Sequence[str], None] = "0017_knowledge_retrieval"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "serviceos"


def upgrade() -> None:
    op.create_table(
        "service_policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("rule_id", sa.String(length=80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("country", sa.String(length=8), nullable=False),
        sa.Column("channel", sa.String(length=24), nullable=False),
        sa.Column("product_family", sa.String(length=24), nullable=False),
        sa.Column("warranty_state", sa.String(length=16), nullable=False),
        sa.Column("remedies", JSONB(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.UniqueConstraint("rule_id", "version", name="uq_service_policies_rule_version"),
        sa.CheckConstraint("channel IN ('DIRECT','AUTHORIZED_DEALER','UNAUTHORIZED','*')",
                           name=op.f("ck_service_policies_channel")),
        sa.CheckConstraint("product_family IN ('ROBOVAC','BREAST_PUMP','*')",
                           name=op.f("ck_service_policies_product_family")),
        sa.CheckConstraint("warranty_state IN ('IN','OUT','UNKNOWN')",
                           name=op.f("ck_service_policies_warranty_state")),
        sa.CheckConstraint("status IN ('ACTIVE','SUPERSEDED')", name=op.f("ck_service_policies_status")),
        schema=SCHEMA,
    )
    op.create_index("ix_service_policies_active", "service_policies",
                    ["country", "channel", "product_family", "warranty_state", "status"],
                    schema=SCHEMA)
    op.create_table(
        "publication_guard_decisions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("reason_codes", JSONB(), nullable=False),
        sa.Column("entities", JSONB(), nullable=False),
        sa.Column("verifier", JSONB(), nullable=False),
        sa.Column("reply_text", sa.Text(), nullable=False),
        sa.Column("proposal_id", UUID(as_uuid=True), nullable=True),
        sa.Column("override_by", UUID(as_uuid=True), nullable=True),
        sa.Column("override_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("decision IN ('PASSED','BLOCKED','OVERRIDDEN')",
                           name=op.f("ck_publication_guard_decisions_decision")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], [f"{SCHEMA}.tenants.id"],
            name="fk_publication_guard_decisions_tenant_id_tenants",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            [f"{SCHEMA}.conversations.tenant_id", f"{SCHEMA}.conversations.id"],
            name="fk_publication_guard_decisions_conversation_id_conversations",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "proposal_id"],
            [f"{SCHEMA}.agent_proposals.tenant_id", f"{SCHEMA}.agent_proposals.id"],
            name="fk_publication_guard_decisions_proposal_id_agent_proposals",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_publication_guard_decisions_tenant", "publication_guard_decisions",
                    ["tenant_id", "created_at", "id"], schema=SCHEMA)
    op.add_column("case_actions", sa.Column("remedy_type", sa.String(length=16), nullable=True),
                  schema=SCHEMA)
    op.create_check_constraint("ck_case_actions_remedy_type", "case_actions",
                               "remedy_type IN ('REPAIR','RESHIP','REFER_SELLER','DECLINE')",
                               schema=SCHEMA)


def downgrade() -> None:
    op.drop_constraint("ck_case_actions_remedy_type", "case_actions", type_="check", schema=SCHEMA)
    op.drop_column("case_actions", "remedy_type", schema=SCHEMA)
    op.drop_table("publication_guard_decisions", schema=SCHEMA)
    op.drop_table("service_policies", schema=SCHEMA)
