"""split doctor name into first and last name

Revision ID: 202604300004
Revises: 202604300003
Create Date: 2026-04-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202604300004"
down_revision: Union[str, None] = "202604300003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("doctors", sa.Column("first_name", sa.String(length=255), nullable=True))
    op.add_column("doctors", sa.Column("last_name", sa.String(length=255), nullable=True))
    op.execute(
        """
        UPDATE doctors
        SET
          first_name = COALESCE(NULLIF(split_part(trim(name), ' ', 1), ''), name),
          last_name = COALESCE(NULLIF(regexp_replace(trim(name), '^[^ ]+\\s*', ''), ''), split_part(trim(name), ' ', 1))
        """
    )
    op.alter_column("doctors", "first_name", nullable=False)
    op.alter_column("doctors", "last_name", nullable=False)
    op.drop_column("doctors", "name")


def downgrade() -> None:
    op.add_column("doctors", sa.Column("name", sa.String(length=255), nullable=True))
    op.execute("UPDATE doctors SET name = trim(first_name || ' ' || last_name)")
    op.alter_column("doctors", "name", nullable=False)
    op.drop_column("doctors", "last_name")
    op.drop_column("doctors", "first_name")
