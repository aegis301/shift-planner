"""team member calendar subscription token

Revision ID: 202609300002
Revises: 202609300001
Create Date: 2026-09-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609300002"
down_revision: Union[str, None] = "202609300001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("team_members", sa.Column("calendar_token", sa.String(length=64), nullable=True))
    op.create_index("ix_team_members_calendar_token", "team_members", ["calendar_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_team_members_calendar_token", table_name="team_members")
    op.drop_column("team_members", "calendar_token")
