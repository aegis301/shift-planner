"""dual valuation minutes and template override

Revision ID: 202609100003
Revises: 202609100002
Create Date: 2026-09-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609100003"
down_revision: Union[str, None] = "202609100002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("shift_templates", sa.Column("valuation_override", sa.JSON(), nullable=True))
    op.add_column(
        "time_entries",
        sa.Column("statutory_minutes", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "time_entries",
        sa.Column("credited_minutes", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    raise NotImplementedError("Forward-only migration")
