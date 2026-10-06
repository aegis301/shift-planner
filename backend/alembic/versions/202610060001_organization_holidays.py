"""organization holidays

Revision ID: 202610060001
Revises: 202609300002
Create Date: 2026-10-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202610060001"
down_revision: Union[str, None] = "202609300002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization_holidays",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("holiday_date", sa.Date(), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "holiday_date", name="uq_organization_holidays_org_date"),
    )
    op.create_index("ix_organization_holidays_organization_id", "organization_holidays", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_organization_holidays_organization_id", table_name="organization_holidays")
    op.drop_table("organization_holidays")
