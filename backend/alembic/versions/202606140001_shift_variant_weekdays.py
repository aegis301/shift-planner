"""shift variant weekday allowlists

Revision ID: 202606140001
Revises: 202606130001
Create Date: 2026-06-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202606140001"
down_revision: Union[str, None] = "202606130001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("shift_variants", sa.Column("start_weekdays", sa.JSON(), nullable=True))
    op.add_column("shift_variants", sa.Column("end_weekdays", sa.JSON(), nullable=True))
    op.add_column(
        "shift_variants",
        sa.Column("include_holidays", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("shift_variants", "include_holidays", server_default=None)


def downgrade() -> None:
    op.drop_column("shift_variants", "include_holidays")
    op.drop_column("shift_variants", "end_weekdays")
    op.drop_column("shift_variants", "start_weekdays")
