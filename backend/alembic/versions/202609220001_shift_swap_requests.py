"""shift swap requests

Revision ID: 202609220001
Revises: 202609210003
Create Date: 2026-09-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609220001"
down_revision: Union[str, None] = "202609210003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ACTIVE_STATUSES = "status IN ('draft', 'open', 'claimed', 'targeted', 'accepted', 'approved')"


def upgrade() -> None:
    op.create_table(
        "shift_swap_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "planning_period_id",
            sa.Integer(),
            sa.ForeignKey("planning_periods.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "shift_group_id",
            sa.Integer(),
            sa.ForeignKey("shift_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column(
            "offered_by_team_member_id",
            sa.Integer(),
            sa.ForeignKey("team_members.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "offered_slot_id",
            sa.Integer(),
            sa.ForeignKey("roster_slots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_team_member_id",
            sa.Integer(),
            sa.ForeignKey("team_members.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "counterparty_slot_id",
            sa.Integer(),
            sa.ForeignKey("roster_slots.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("warning_findings", sa.JSON(), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "resolved_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "applied_plan_version_id",
            sa.Integer(),
            sa.ForeignKey("planning_plan_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_shift_swap_requests_organization_id", "shift_swap_requests", ["organization_id"])
    op.create_index("ix_shift_swap_requests_planning_period_id", "shift_swap_requests", ["planning_period_id"])
    op.create_index("ix_shift_swap_requests_shift_group_id", "shift_swap_requests", ["shift_group_id"])
    op.create_index("ix_shift_swap_requests_status", "shift_swap_requests", ["status"])
    op.create_index(
        "ix_shift_swap_requests_offered_by_team_member_id",
        "shift_swap_requests",
        ["offered_by_team_member_id"],
    )
    op.create_index("ix_shift_swap_requests_offered_slot_id", "shift_swap_requests", ["offered_slot_id"])
    op.create_index(
        "ix_shift_swap_requests_target_team_member_id",
        "shift_swap_requests",
        ["target_team_member_id"],
    )
    op.create_index(
        "uq_shift_swap_requests_active_offered_slot",
        "shift_swap_requests",
        ["offered_slot_id"],
        unique=True,
        sqlite_where=sa.text(_ACTIVE_STATUSES),
        postgresql_where=sa.text(_ACTIVE_STATUSES),
    )


def downgrade() -> None:
    raise NotImplementedError("Forward-only migration")
