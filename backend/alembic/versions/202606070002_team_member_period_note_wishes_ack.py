"""team member period note wishes response flag

Revision ID: 202606070002
Revises: 202606070001
Create Date: 2026-06-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202606070002"
down_revision: Union[str, None] = "202606070001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "team_member_period_notes",
        sa.Column("wishes_response_received", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("team_member_period_notes", "wishes_response_received")
