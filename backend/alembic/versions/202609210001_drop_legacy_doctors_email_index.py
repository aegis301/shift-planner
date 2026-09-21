"""drop leftover doctors-era unique email index

Revision ID: 202609210001
Revises: 202609200002
Create Date: 2026-09-21
"""

from typing import Sequence, Union

from alembic import op

revision: str = "202609210001"
down_revision: Union[str, None] = "202609200002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_doctors_email")
    op.execute("ALTER TABLE team_members DROP CONSTRAINT IF EXISTS doctors_email_key")


def downgrade() -> None:
    pass
