"""time entry ledger

Revision ID: 202609100002
Revises: 202609100001
Create Date: 2026-09-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609100002"
down_revision: Union[str, None] = "202609100001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "time_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("team_member_id", sa.Integer(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("all_day", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("counts_toward_contract", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("consumes_vacation", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("shift_template_category", sa.String(length=50), nullable=True),
        sa.Column("planning_day_status_code", sa.String(length=32), nullable=True),
        sa.Column("roster_slot_id", sa.Integer(), nullable=True),
        sa.Column("shift_group_id", sa.Integer(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("derived_snapshot", sa.JSON(), nullable=True),
        sa.Column("corrected_fields", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_member_id"], ["team_members.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["roster_slot_id"], ["roster_slots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shift_group_id"], ["shift_groups.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_time_entries_organization_id", "time_entries", ["organization_id"], unique=False)
    op.create_index("ix_time_entries_member_date", "time_entries", ["team_member_id", "entry_date"], unique=False)
    op.create_index("ix_time_entries_roster_slot_id", "time_entries", ["roster_slot_id"], unique=False)


def downgrade() -> None:
    raise NotImplementedError("Forward-only migration")
