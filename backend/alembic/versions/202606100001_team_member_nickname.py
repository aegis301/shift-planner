"""team member nickname

Revision ID: 202606100001
Revises: 202606090001
Create Date: 2026-06-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202606100001"
down_revision: Union[str, None] = "202606090001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("team_members", sa.Column("nickname", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("team_members", "nickname")
