"""Allow audited review of internal Agent reply drafts."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_reply_review"
down_revision: Union[str, Sequence[str], None] = "0007_ui_documents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_agent_proposals_type_values", "agent_proposals", type_="check", schema="serviceos")
    op.create_check_constraint("ck_agent_proposals_type_values", "agent_proposals",
                               "proposal_type IN ('MISSING_EVIDENCE','ACTION','REPLY')", schema="serviceos")


def downgrade() -> None:
    op.execute("DELETE FROM serviceos.agent_proposals WHERE proposal_type = 'REPLY'")
    op.drop_constraint("ck_agent_proposals_type_values", "agent_proposals", type_="check", schema="serviceos")
    op.create_check_constraint("ck_agent_proposals_type_values", "agent_proposals",
                               "proposal_type IN ('MISSING_EVIDENCE','ACTION')", schema="serviceos")
