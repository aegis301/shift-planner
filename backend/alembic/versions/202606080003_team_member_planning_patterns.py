"""team member planning patterns

Revision ID: 202606080003
Revises: 202606080002
Create Date: 2026-06-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202606080003"
down_revision: Union[str, None] = "202606080002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("member_pattern_policy", sa.JSON(), nullable=False, server_default=sa.text("'{\"hard_types\": []}'::json")),
    )
    op.alter_column("organizations", "member_pattern_policy", server_default=None)
    op.create_table(
        "team_member_planning_patterns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("team_member_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("rule", sa.JSON(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="warning"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["team_member_id"], ["team_members.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_team_member_planning_patterns_organization_id"),
        "team_member_planning_patterns",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_team_member_planning_patterns_team_member_id"),
        "team_member_planning_patterns",
        ["team_member_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_team_member_planning_patterns_team_member_id"), table_name="team_member_planning_patterns")
    op.drop_index(op.f("ix_team_member_planning_patterns_organization_id"), table_name="team_member_planning_patterns")
    op.drop_table("team_member_planning_patterns")
    op.drop_column("organizations", "member_pattern_policy")
