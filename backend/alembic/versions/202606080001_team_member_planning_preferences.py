"""team member planning preferences column

Revision ID: 202606080001
Revises: 202606070002
Create Date: 2026-05-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202606080001"
down_revision: Union[str, None] = "202606070002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("team_members", sa.Column("planning_preferences", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE team_members AS tm
        SET planning_preferences = sub.st
        FROM (
            SELECT DISTINCT ON (team_member_id)
                team_member_id,
                source_text AS st
            FROM team_member_period_notes
            WHERE source_text IS NOT NULL AND btrim(source_text) <> ''
            ORDER BY team_member_id, updated_at DESC
        ) AS sub
        WHERE tm.id = sub.team_member_id
        """
    )
    op.drop_column("team_member_period_notes", "source_text")


def downgrade() -> None:
    op.add_column(
        "team_member_period_notes",
        sa.Column("source_text", sa.Text(), nullable=True),
    )
    op.drop_column("team_members", "planning_preferences")
