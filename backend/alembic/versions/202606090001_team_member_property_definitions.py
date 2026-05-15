"""team member property definitions and values

Revision ID: 202606090001
Revises: 202606080003
Create Date: 2026-06-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202606090001"
down_revision: Union[str, None] = "202606080003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "team_member_property_definitions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("editable_by_team_member", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_team_member_property_def_org_name"),
    )
    op.create_index(
        op.f("ix_team_member_property_definitions_organization_id"),
        "team_member_property_definitions",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "team_member_property_values",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("team_member_id", sa.Integer(), nullable=False),
        sa.Column("property_definition_id", sa.Integer(), nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["property_definition_id"], ["team_member_property_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_member_id"], ["team_members.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "team_member_id",
            "property_definition_id",
            name="uq_team_member_property_value_member_def",
        ),
    )
    op.create_index(
        op.f("ix_team_member_property_values_organization_id"),
        "team_member_property_values",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_team_member_property_values_team_member_id"),
        "team_member_property_values",
        ["team_member_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_team_member_property_values_property_definition_id"),
        "team_member_property_values",
        ["property_definition_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_team_member_property_values_property_definition_id"),
        table_name="team_member_property_values",
    )
    op.drop_index(op.f("ix_team_member_property_values_team_member_id"), table_name="team_member_property_values")
    op.drop_index(op.f("ix_team_member_property_values_organization_id"), table_name="team_member_property_values")
    op.drop_table("team_member_property_values")
    op.drop_index(
        op.f("ix_team_member_property_definitions_organization_id"),
        table_name="team_member_property_definitions",
    )
    op.drop_table("team_member_property_definitions")
