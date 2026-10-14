"""Frozen conditions and customer-observed outcome for simulated service actions."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0011_resolution_verification"
down_revision: Union[str, Sequence[str], None] = "0010_mock_service_actions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
SCHEMA = "serviceos"


def base_columns():
    return [
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
    ]


def tenant_keys(table):
    return [
        sa.ForeignKeyConstraint(["tenant_id"], [f"{SCHEMA}.tenants.id"], name=f"fk_{table}_tenant_id_tenants"),
        sa.UniqueConstraint("tenant_id", "id", name=f"uq_{table}_tenant_id_id"),
    ]


def tenant_fk(table, column, target):
    return sa.ForeignKeyConstraint(
        ["tenant_id", column], [f"{SCHEMA}.{target}.tenant_id", f"{SCHEMA}.{target}.id"],
        name=f"fk_{table}_{column}_{target}",
    )


def upgrade() -> None:
    op.create_table(
        "resolution_contracts", *base_columns(),
        sa.Column("case_id", UUID(as_uuid=True), nullable=False),
        sa.Column("action_id", UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("conditions", JSONB(), nullable=False),
        *tenant_keys("resolution_contracts"),
        tenant_fk("resolution_contracts", "case_id", "service_cases"),
        tenant_fk("resolution_contracts", "action_id", "case_actions"),
        sa.UniqueConstraint("tenant_id", "action_id", name="uq_resolution_contracts_tenant_id_action_id"),
        sa.CheckConstraint("version >= 1", name="ck_resolution_contracts_version_positive"),
        schema=SCHEMA,
    )
    # Earlier development actions have no contract. Freeze the now-confirmed rule for them as well.
    op.execute(sa.text("""
        INSERT INTO serviceos.resolution_contracts
            (id, tenant_id, case_id, action_id, version, conditions)
        SELECT gen_random_uuid(), tenant_id, case_id, id, 1,
               '["模拟服务请求收到成功回执", "客户明确确认问题已解决"]'::jsonb
        FROM serviceos.case_actions
    """))
    op.create_table(
        "case_verifications", *base_columns(),
        sa.Column("case_id", UUID(as_uuid=True), nullable=False),
        sa.Column("contract_id", UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True), nullable=False),
        sa.Column("client_verification_id", UUID(as_uuid=True), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("observed_result", sa.String(16), nullable=False),
        sa.Column("decision", sa.String(24), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("evidence_ids", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("case_status", sa.String(24), nullable=False),
        *tenant_keys("case_verifications"),
        tenant_fk("case_verifications", "case_id", "service_cases"),
        tenant_fk("case_verifications", "contract_id", "resolution_contracts"),
        tenant_fk("case_verifications", "customer_id", "customers"),
        sa.UniqueConstraint("tenant_id", "case_id", "client_verification_id",
                            name="uq_case_verifications_tenant_id_case_id_client_verification_id"),
        sa.CheckConstraint("observed_result IN ('WORKING','NOT_WORKING','UNCERTAIN')",
                           name="ck_case_verifications_observation_values"),
        sa.CheckConstraint("decision IN ('PENDING','VERIFIED_RESOLVED','NOT_RESOLVED')",
                           name="ck_case_verifications_decision_values"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("case_verifications", schema=SCHEMA)
    op.drop_table("resolution_contracts", schema=SCHEMA)
