"""shift template and variant constraints

Revision ID: 202606080002
Revises: 202606080001
Create Date: 2026-06-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202606080002"
down_revision: Union[str, None] = "202606080001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "shift_templates",
        sa.Column("constraints", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
    )
    op.add_column(
        "shift_variants",
        sa.Column("constraints", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
    )
    op.alter_column("shift_templates", "constraints", server_default=None)
    op.alter_column("shift_variants", "constraints", server_default=None)


def downgrade() -> None:
    op.drop_column("shift_variants", "constraints")
    op.drop_column("shift_templates", "constraints")
