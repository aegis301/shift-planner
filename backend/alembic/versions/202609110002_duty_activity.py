"""duty activity episode reason

Revision ID: 202609110002
Revises: 202609110001
Create Date: 2026-09-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609110002"
down_revision: Union[str, None] = "202609110001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("time_entries", sa.Column("reason", sa.JSON(), nullable=True))


def downgrade() -> None:
    raise NotImplementedError("Forward-only migration")
