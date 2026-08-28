"""worker groups, employment periods, time entries, opening balances

Revision ID: 202608280001
Revises: 202608270001
Create Date: 2026-08-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202608280001"
down_revision: Union[str, None] = "202608270001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "worker_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("weekly_hours_at_100", sa.Numeric(6, 2), nullable=False, server_default="40"),
        sa.Column("vacation_days_at_100", sa.Numeric(6, 2), nullable=False, server_default="30"),
        sa.Column("regular_week_pattern", sa.JSON(), nullable=False),
        sa.Column("category_rules", sa.JSON(), nullable=False),
        sa.Column("status_mappings", sa.JSON(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("organization_id", "name", name="uq_worker_group_org_name"),
    )
    op.create_index(op.f("ix_worker_groups_organization_id"), "worker_groups", ["organization_id"])

    op.create_table(
        "employment_periods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "team_member_id",
            sa.Integer(),
            sa.ForeignKey("team_members.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "worker_group_id",
            sa.Integer(),
            sa.ForeignKey("worker_groups.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("employment_percentage", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(op.f("ix_employment_periods_organization_id"), "employment_periods", ["organization_id"])
    op.create_index(op.f("ix_employment_periods_team_member_id"), "employment_periods", ["team_member_id"])
    op.create_index(op.f("ix_employment_periods_worker_group_id"), "employment_periods", ["worker_group_id"])

    op.create_table(
        "time_account_openings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "team_member_id",
            sa.Integer(),
            sa.ForeignKey("team_members.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("overtime_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("vacation_days_remaining", sa.Numeric(8, 2), nullable=False, server_default="0"),
        sa.Column("sick_days_used_ytd", sa.Numeric(8, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("team_member_id", name="uq_time_account_opening_member"),
    )
    op.create_index(op.f("ix_time_account_openings_organization_id"), "time_account_openings", ["organization_id"])
    op.create_index(op.f("ix_time_account_openings_team_member_id"), "time_account_openings", ["team_member_id"])

    op.create_table(
        "time_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "team_member_id",
            sa.Integer(),
            sa.ForeignKey("team_members.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("all_day", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("counts_toward_contract", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("shift_template_category", sa.String(length=50), nullable=True),
        sa.Column("planning_day_status_code", sa.String(length=32), nullable=True),
        sa.Column("roster_slot_id", sa.Integer(), sa.ForeignKey("roster_slots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(op.f("ix_time_entries_organization_id"), "time_entries", ["organization_id"])
    op.create_index(op.f("ix_time_entries_team_member_id"), "time_entries", ["team_member_id"])
    op.create_index(op.f("ix_time_entries_entry_date"), "time_entries", ["entry_date"])


def downgrade() -> None:
    op.drop_index(op.f("ix_time_entries_entry_date"), table_name="time_entries")
    op.drop_index(op.f("ix_time_entries_team_member_id"), table_name="time_entries")
    op.drop_index(op.f("ix_time_entries_organization_id"), table_name="time_entries")
    op.drop_table("time_entries")
    op.drop_index(op.f("ix_time_account_openings_team_member_id"), table_name="time_account_openings")
    op.drop_index(op.f("ix_time_account_openings_organization_id"), table_name="time_account_openings")
    op.drop_table("time_account_openings")
    op.drop_index(op.f("ix_employment_periods_worker_group_id"), table_name="employment_periods")
    op.drop_index(op.f("ix_employment_periods_team_member_id"), table_name="employment_periods")
    op.drop_index(op.f("ix_employment_periods_organization_id"), table_name="employment_periods")
    op.drop_table("employment_periods")
    op.drop_index(op.f("ix_worker_groups_organization_id"), table_name="worker_groups")
    op.drop_table("worker_groups")
