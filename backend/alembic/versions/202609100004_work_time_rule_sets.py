"""work time rule sets and drop rule_configs

Revision ID: 202609100004
Revises: 202609100003
Create Date: 2026-09-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609100004"
down_revision: Union[str, None] = "202609100003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "work_time_rule_sets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rules", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "name", "version", name="uq_work_time_rule_set_org_name_version"),
    )
    op.create_index("ix_work_time_rule_sets_organization_id", "work_time_rule_sets", ["organization_id"])
    op.add_column(
        "planning_plan_versions",
        sa.Column(
            "work_time_rule_set_version_id",
            sa.Integer(),
            sa.ForeignKey("work_time_rule_sets.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_planning_plan_versions_work_time_rule_set_version_id",
        "planning_plan_versions",
        ["work_time_rule_set_version_id"],
    )
    op.drop_table("rule_configs")


def downgrade() -> None:
    raise NotImplementedError("Forward-only migration")
