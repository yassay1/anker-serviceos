"""Mark case-derived verified facts as explicitly archived after resolution."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0013_case_fact_archive"
down_revision: Union[str, Sequence[str], None] = "0012_follow_up_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("device_facts", sa.Column("client_fact_id", UUID(as_uuid=True), nullable=True), schema="serviceos")
    op.create_unique_constraint("uq_device_facts_tenant_id_device_id_client_fact_id", "device_facts",
                                ["tenant_id", "device_id", "client_fact_id"], schema="serviceos")
    op.add_column("device_facts", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True), schema="serviceos")
    op.add_column("device_facts", sa.Column("archived_by", UUID(as_uuid=True), nullable=True), schema="serviceos")
    op.create_foreign_key("fk_device_facts_archived_by_tenant_memberships", "device_facts", "tenant_memberships",
                          ["tenant_id", "archived_by"], ["tenant_id", "staff_user_id"],
                          source_schema="serviceos", referent_schema="serviceos")
    # Carry forward only historical facts meeting the new source and resolution gate.
    op.execute(sa.text("""
        UPDATE serviceos.device_facts AS f
        SET archived_at = f.verified_at
        FROM serviceos.service_cases AS c
        WHERE f.source_case_id = c.id AND f.tenant_id = c.tenant_id
          AND c.status IN ('RESOLVED', 'CLOSED')
          AND f.validity = 'VERIFIED' AND f.verified_at IS NOT NULL
          AND EXISTS (
              SELECT 1 FROM serviceos.case_devices AS cd
              WHERE cd.tenant_id = f.tenant_id AND cd.case_id = f.source_case_id
                AND cd.device_id = f.device_id
          )
    """))


def downgrade() -> None:
    op.drop_constraint("fk_device_facts_archived_by_tenant_memberships", "device_facts", schema="serviceos")
    op.drop_column("device_facts", "archived_by", schema="serviceos")
    op.drop_column("device_facts", "archived_at", schema="serviceos")
    op.drop_constraint("uq_device_facts_tenant_id_device_id_client_fact_id", "device_facts", schema="serviceos")
    op.drop_column("device_facts", "client_fact_id", schema="serviceos")
