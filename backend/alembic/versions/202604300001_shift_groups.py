"""shift groups and memberships

Revision ID: 202604300001
Revises: 202604290001
Create Date: 2026-04-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202604300001"
down_revision: Union[str, None] = "202604290001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shift_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name_de", sa.String(length=255), nullable=False),
        sa.Column("name_en", sa.String(length=255), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_shift_groups_code", "shift_groups", ["code"], unique=True)

    op.create_table(
        "doctor_shift_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shift_group_id", sa.Integer(), sa.ForeignKey("shift_groups.id", ondelete="CASCADE"), nullable=False),
    )
    op.create_unique_constraint("uq_doctor_shift_group", "doctor_shift_groups", ["doctor_id", "shift_group_id"])

    op.create_table(
        "shift_group_shift_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shift_group_id", sa.Integer(), sa.ForeignKey("shift_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shift_template_id", sa.Integer(), sa.ForeignKey("shift_templates.id", ondelete="CASCADE"), nullable=False),
    )
    op.create_unique_constraint(
        "uq_shift_group_template", "shift_group_shift_templates", ["shift_group_id", "shift_template_id"]
    )


def downgrade() -> None:
    op.drop_table("shift_group_shift_templates")
    op.drop_table("doctor_shift_groups")
    op.drop_index("ix_shift_groups_code", table_name="shift_groups")
    op.drop_table("shift_groups")
