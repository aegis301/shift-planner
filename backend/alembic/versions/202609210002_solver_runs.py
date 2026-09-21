"""solver runs and org time-budget ceiling

Revision ID: 202609210002
Revises: 202609210001
Create Date: 2026-09-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609210002"
down_revision: Union[str, None] = "202609210001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "solver_time_budget_ceiling_seconds",
            sa.Integer(),
            nullable=False,
            server_default="120",
        ),
    )
    op.alter_column("organizations", "solver_time_budget_ceiling_seconds", server_default=None)
    op.create_table(
        "solver_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "planning_period_id",
            sa.Integer(),
            sa.ForeignKey("planning_periods.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("shift_group_id", sa.Integer(), sa.ForeignKey("shift_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="queued"),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("proposed_assignments", sa.JSON(), nullable=False),
        sa.Column("objective_breakdown", sa.JSON(), nullable=False),
        sa.Column("unfilled_slots", sa.JSON(), nullable=False),
        sa.Column("post_check_findings", sa.JSON(), nullable=False),
        sa.Column(
            "rule_set_version_id",
            sa.Integer(),
            sa.ForeignKey("work_time_rule_sets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("failure_reason", sa.String(length=255), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_solver_runs_organization_id", "solver_runs", ["organization_id"])
    op.create_index("ix_solver_runs_planning_period_id", "solver_runs", ["planning_period_id"])
    op.create_index("ix_solver_runs_shift_group_id", "solver_runs", ["shift_group_id"])
    op.create_index("ix_solver_runs_status", "solver_runs", ["status"])
    op.create_index("ix_solver_runs_rule_set_version_id", "solver_runs", ["rule_set_version_id"])


def downgrade() -> None:
    raise NotImplementedError("Forward-only migration")
