"""roster change sets and solver run link

Revision ID: 202609280001
Revises: 202609260001
Create Date: 2026-09-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609280001"
down_revision: Union[str, None] = "202609260001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "roster_change_sets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "planning_period_id",
            sa.Integer(),
            sa.ForeignKey("planning_periods.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("shift_group_id", sa.Integer(), sa.ForeignKey("shift_groups.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reverts_change_set_id", sa.Integer(), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_roster_change_sets_organization_id", "roster_change_sets", ["organization_id"])
    op.create_index("ix_roster_change_sets_planning_period_id", "roster_change_sets", ["planning_period_id"])
    op.create_index("ix_roster_change_sets_shift_group_id", "roster_change_sets", ["shift_group_id"])
    op.create_index("ix_roster_change_sets_status", "roster_change_sets", ["status"])
    op.create_foreign_key(
        "fk_roster_change_sets_reverts_change_set_id",
        "roster_change_sets",
        "roster_change_sets",
        ["reverts_change_set_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "roster_change_set_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "change_set_id",
            sa.Integer(),
            sa.ForeignKey("roster_change_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("roster_slot_id", sa.Integer(), sa.ForeignKey("roster_slots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("before_team_member_id", sa.Integer(), nullable=True),
        sa.Column("after_team_member_id", sa.Integer(), nullable=True),
        sa.Column("before_manual_override", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("after_manual_override", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("before_comment", sa.Text(), nullable=True),
        sa.Column("after_comment", sa.Text(), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("refusal_code", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_roster_change_set_items_change_set_id", "roster_change_set_items", ["change_set_id"])
    op.create_index("ix_roster_change_set_items_roster_slot_id", "roster_change_set_items", ["roster_slot_id"])
    op.add_column(
        "solver_runs",
        sa.Column("change_set_id", sa.Integer(), sa.ForeignKey("roster_change_sets.id", ondelete="SET NULL"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("solver_runs", "change_set_id")
    op.drop_index("ix_roster_change_set_items_roster_slot_id", table_name="roster_change_set_items")
    op.drop_index("ix_roster_change_set_items_change_set_id", table_name="roster_change_set_items")
    op.drop_table("roster_change_set_items")
    op.drop_index("ix_roster_change_sets_status", table_name="roster_change_sets")
    op.drop_index("ix_roster_change_sets_shift_group_id", table_name="roster_change_sets")
    op.drop_index("ix_roster_change_sets_planning_period_id", table_name="roster_change_sets")
    op.drop_index("ix_roster_change_sets_organization_id", table_name="roster_change_sets")
    op.drop_table("roster_change_sets")
