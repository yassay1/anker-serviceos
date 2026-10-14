"""Audited simulated service actions, approvals and durable mock receipts."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0010_mock_service_actions"
down_revision: Union[str, Sequence[str], None] = "0009_case_image_evidence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
SCHEMA = "serviceos"


def identity():
    return [
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
    ]


def tenant_keys(table):
    return [
        sa.ForeignKeyConstraint(["tenant_id"], [f"{SCHEMA}.tenants.id"],
                                name=f"fk_{table}_tenant_id_tenants"),
        sa.UniqueConstraint("tenant_id", "id", name=f"uq_{table}_tenant_id_id"),
    ]


def tenant_fk(table, column, target, target_column="id"):
    return sa.ForeignKeyConstraint(
        ["tenant_id", column], [f"{SCHEMA}.{target}.tenant_id", f"{SCHEMA}.{target}.{target_column}"],
        name=f"fk_{table}_{column}_{target}",
    )


def upgrade() -> None:
    op.create_table(
        "case_actions", *identity(),
        sa.Column("case_id", UUID(as_uuid=True), nullable=False),
        sa.Column("client_action_id", UUID(as_uuid=True), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("action_kind", sa.String(40), nullable=False),
        sa.Column("adapter", sa.String(16), server_default="MOCK", nullable=False),
        sa.Column("status", sa.String(24), server_default="WAITING_APPROVAL", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("requested_by", UUID(as_uuid=True), nullable=False),
        sa.Column("source_proposal_id", UUID(as_uuid=True)),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("lease_token", UUID(as_uuid=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("receipt_reference", sa.String(160)),
        sa.Column("receipt_result", sa.String(16)),
        sa.Column("receipt_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(80)),
        *tenant_keys("case_actions"),
        tenant_fk("case_actions", "case_id", "service_cases"),
        tenant_fk("case_actions", "requested_by", "tenant_memberships", "staff_user_id"),
        tenant_fk("case_actions", "source_proposal_id", "agent_proposals"),
        sa.UniqueConstraint("tenant_id", "case_id", "client_action_id", name="uq_case_actions_tenant_id_case_id_client_action_id"),
        sa.CheckConstraint("action_kind = 'MOCK_SERVICE_REQUEST'", name="ck_case_actions_kind_values"),
        sa.CheckConstraint("adapter = 'MOCK'", name="ck_case_actions_adapter_values"),
        sa.CheckConstraint("status IN ('WAITING_APPROVAL','APPROVED','EXECUTING','UNKNOWN','SUCCEEDED','FAILED','REJECTED')", name="ck_case_actions_status_values"),
        sa.CheckConstraint("version >= 1 AND attempt_count >= 0", name="ck_case_actions_version_attempt_positive"),
        sa.CheckConstraint("(receipt_result IS NULL AND receipt_reference IS NULL AND receipt_at IS NULL) OR "
                           "(receipt_result IN ('SUCCEEDED','FAILED') AND receipt_reference IS NOT NULL AND receipt_at IS NOT NULL)",
                           name="ck_case_actions_receipt_complete"),
        sa.CheckConstraint("status NOT IN ('SUCCEEDED','FAILED') OR receipt_result = status", name="ck_case_actions_terminal_has_receipt"),
        schema=SCHEMA,
    )
    op.create_index("ix_case_actions_ready", "case_actions", ["status", "available_at", "created_at"], schema=SCHEMA)
    op.create_table(
        "case_action_approvals", *identity(),
        sa.Column("action_id", UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(16), server_default="PENDING", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("decision_id", UUID(as_uuid=True)),
        sa.Column("decision_hash", sa.String(64)),
        sa.Column("decided_by", UUID(as_uuid=True)),
        sa.Column("decision_reason", sa.Text()),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        *tenant_keys("case_action_approvals"),
        tenant_fk("case_action_approvals", "action_id", "case_actions"),
        tenant_fk("case_action_approvals", "decided_by", "tenant_memberships", "staff_user_id"),
        sa.UniqueConstraint("tenant_id", "action_id", name="uq_case_action_approvals_tenant_id_action_id"),
        sa.UniqueConstraint("tenant_id", "decision_id", name="uq_case_action_approvals_tenant_id_decision_id"),
        sa.CheckConstraint("status IN ('PENDING','APPROVED','REJECTED')", name="ck_case_action_approvals_status_values"),
        sa.CheckConstraint("version >= 1", name="ck_case_action_approvals_version_positive"),
        schema=SCHEMA,
    )
    op.create_table(
        "mock_service_operations", *identity(),
        sa.Column("action_id", UUID(as_uuid=True), nullable=False),
        sa.Column("external_reference", sa.String(160), nullable=False),
        sa.Column("result", sa.String(16), nullable=False),
        *tenant_keys("mock_service_operations"),
        tenant_fk("mock_service_operations", "action_id", "case_actions"),
        sa.UniqueConstraint("tenant_id", "action_id", name="uq_mock_service_operations_tenant_id_action_id"),
        sa.UniqueConstraint("tenant_id", "external_reference", name="uq_mock_service_operations_tenant_id_external_reference"),
        sa.CheckConstraint("result IN ('SUCCEEDED','FAILED')", name="ck_mock_service_operations_result_values"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("mock_service_operations", schema=SCHEMA)
    op.drop_table("case_action_approvals", schema=SCHEMA)
    op.drop_index("ix_case_actions_ready", table_name="case_actions", schema=SCHEMA)
    op.drop_table("case_actions", schema=SCHEMA)
