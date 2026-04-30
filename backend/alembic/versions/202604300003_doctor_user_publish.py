"""doctor user link and planning published_at

Revision ID: 202604300003
Revises: 202604300002
Create Date: 2026-04-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202604300003"
down_revision: Union[str, None] = "202604300002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("planning_periods", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("doctors", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_doctors_user_id_users", "doctors", "users", ["user_id"], ["id"], ondelete="SET NULL")
    op.create_index(op.f("ix_doctors_user_id"), "doctors", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_doctors_user_id"), table_name="doctors")
    op.drop_constraint("fk_doctors_user_id_users", "doctors", type_="foreignkey")
    op.drop_column("doctors", "user_id")
    op.drop_column("planning_periods", "published_at")
