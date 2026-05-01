"""organizations, tenant FKs, planner shift groups

Revision ID: 202605010001
Revises: 202604300004
Create Date: 2026-05-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202605010001"
down_revision: Union[str, None] = "202604300004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False, server_default="Default"),
        sa.Column("plan_tier", sa.String(length=50), nullable=False, server_default="team"),
        sa.Column("seat_limit", sa.Integer(), nullable=True),
        sa.Column("billing_customer_id", sa.String(length=255), nullable=True),
        sa.Column("subscription_status", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute(sa.text("INSERT INTO organizations (id, name, plan_tier) VALUES (1, 'Default', 'team')"))
    op.execute(
        sa.text(
            "SELECT setval(pg_get_serial_sequence('organizations', 'id'), "
            "(SELECT COALESCE(MAX(id), 1) FROM organizations))"
        )
    )

    op.add_column("users", sa.Column("organization_id", sa.Integer(), nullable=True))
    op.execute(sa.text("UPDATE users SET organization_id = 1 WHERE organization_id IS NULL"))
    op.alter_column("users", "organization_id", nullable=False)
    op.create_foreign_key("fk_users_organization_id", "users", "organizations", ["organization_id"], ["id"])

    op.add_column("shift_groups", sa.Column("organization_id", sa.Integer(), nullable=True))
    op.execute(sa.text("UPDATE shift_groups SET organization_id = 1 WHERE organization_id IS NULL"))
    op.alter_column("shift_groups", "organization_id", nullable=False)
    op.create_foreign_key("fk_shift_groups_organization_id", "shift_groups", "organizations", ["organization_id"], ["id"])
    op.drop_index("ix_shift_groups_code", table_name="shift_groups")
    op.create_index("ix_shift_groups_org_code", "shift_groups", ["organization_id", "code"], unique=True)

    op.add_column("shift_templates", sa.Column("organization_id", sa.Integer(), nullable=True))
    op.execute(sa.text("UPDATE shift_templates SET organization_id = 1 WHERE organization_id IS NULL"))
    op.alter_column("shift_templates", "organization_id", nullable=False)
    op.create_foreign_key("fk_shift_templates_organization_id", "shift_templates", "organizations", ["organization_id"], ["id"])
    op.drop_index("ix_shift_templates_code", table_name="shift_templates")
    op.create_index("ix_shift_templates_org_code", "shift_templates", ["organization_id", "code"], unique=True)

    op.add_column("doctors", sa.Column("organization_id", sa.Integer(), nullable=True))
    op.execute(sa.text("UPDATE doctors SET organization_id = 1 WHERE organization_id IS NULL"))
    op.alter_column("doctors", "organization_id", nullable=False)
    op.create_foreign_key("fk_doctors_organization_id", "doctors", "organizations", ["organization_id"], ["id"])
    op.execute(sa.text("ALTER TABLE doctors DROP CONSTRAINT IF EXISTS doctors_email_key"))
    op.create_index("ix_doctors_org_email", "doctors", ["organization_id", "email"], unique=True)

    op.add_column("planning_periods", sa.Column("organization_id", sa.Integer(), nullable=True))
    op.execute(sa.text("UPDATE planning_periods SET organization_id = 1 WHERE organization_id IS NULL"))
    op.alter_column("planning_periods", "organization_id", nullable=False)
    op.create_foreign_key("fk_planning_periods_organization_id", "planning_periods", "organizations", ["organization_id"], ["id"])
    op.drop_constraint("uq_planning_period_month", "planning_periods", type_="unique")
    op.create_unique_constraint("uq_planning_period_org_month", "planning_periods", ["organization_id", "year", "month"])

    op.create_table(
        "user_shift_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shift_group_id", sa.Integer(), sa.ForeignKey("shift_groups.id", ondelete="CASCADE"), nullable=False),
    )
    op.create_unique_constraint("uq_user_shift_group", "user_shift_groups", ["user_id", "shift_group_id"])


def downgrade() -> None:
    op.drop_constraint("uq_user_shift_group", "user_shift_groups", type_="unique")
    op.drop_table("user_shift_groups")

    op.drop_constraint("uq_planning_period_org_month", "planning_periods", type_="unique")
    op.create_unique_constraint("uq_planning_period_month", "planning_periods", ["year", "month"])
    op.drop_constraint("fk_planning_periods_organization_id", "planning_periods", type_="foreignkey")
    op.drop_column("planning_periods", "organization_id")

    op.drop_index("ix_doctors_org_email", table_name="doctors")
    op.create_unique_constraint("doctors_email_key", "doctors", ["email"])
    op.drop_constraint("fk_doctors_organization_id", "doctors", type_="foreignkey")
    op.drop_column("doctors", "organization_id")

    op.drop_index("ix_shift_templates_org_code", table_name="shift_templates")
    op.create_index("ix_shift_templates_code", "shift_templates", ["code"], unique=True)
    op.drop_constraint("fk_shift_templates_organization_id", "shift_templates", type_="foreignkey")
    op.drop_column("shift_templates", "organization_id")

    op.drop_index("ix_shift_groups_org_code", table_name="shift_groups")
    op.create_index("ix_shift_groups_code", "shift_groups", ["code"], unique=True)
    op.drop_constraint("fk_shift_groups_organization_id", "shift_groups", type_="foreignkey")
    op.drop_column("shift_groups", "organization_id")

    op.drop_constraint("fk_users_organization_id", "users", type_="foreignkey")
    op.drop_column("users", "organization_id")

    op.drop_table("organizations")
