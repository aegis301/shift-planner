"""organization AI settings and task-run audit tables

Revision ID: 202609050001
Revises: 202608280001
Create Date: 2026-09-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609050001"
down_revision: Union[str, None] = "202608280001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization_ai_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="anthropic"),
        sa.Column("encrypted_api_key", sa.Text(), nullable=True),
        sa.Column("key_last4", sa.String(length=8), nullable=True),
        sa.Column("default_model", sa.String(length=128), nullable=False, server_default="claude-sonnet-4-5"),
        sa.Column("enabled_task_ids", sa.JSON(), nullable=False),
        sa.Column("monthly_token_budget", sa.Integer(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("organization_id", name="uq_organization_ai_settings_org"),
    )
    op.create_table(
        "ai_task_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column(
            "planning_period_id",
            sa.Integer(),
            sa.ForeignKey("planning_periods.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "shift_group_id",
            sa.Integer(),
            sa.ForeignKey("shift_groups.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("output_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("langfuse_trace_id", sa.String(length=128), nullable=True),
        sa.Column("applied_assignment_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ai_task_runs_organization_id", "ai_task_runs", ["organization_id"])
    op.create_index("ix_ai_task_runs_user_id", "ai_task_runs", ["user_id"])
    op.create_index("ix_ai_task_runs_task_id", "ai_task_runs", ["task_id"])
    op.create_index("ix_ai_task_runs_planning_period_id", "ai_task_runs", ["planning_period_id"])
    op.create_index("ix_ai_task_runs_shift_group_id", "ai_task_runs", ["shift_group_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_task_runs_shift_group_id", table_name="ai_task_runs")
    op.drop_index("ix_ai_task_runs_planning_period_id", table_name="ai_task_runs")
    op.drop_index("ix_ai_task_runs_task_id", table_name="ai_task_runs")
    op.drop_index("ix_ai_task_runs_user_id", table_name="ai_task_runs")
    op.drop_index("ix_ai_task_runs_organization_id", table_name="ai_task_runs")
    op.drop_table("ai_task_runs")
    op.drop_table("organization_ai_settings")
