"""account locale for account-only session

Revision ID: 202606070001
Revises: 202606020001
Create Date: 2026-06-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202606070001"
down_revision: Union[str, None] = "202606020001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("locale", sa.String(length=5), server_default="de", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("accounts", "locale")
