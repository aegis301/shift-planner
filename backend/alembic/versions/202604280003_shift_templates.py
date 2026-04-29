"""shift templates

Revision ID: 202604280003
Revises: 202604280002
Create Date: 2026-04-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202604280003"
down_revision: Union[str, None] = "202604280002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shift_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False, unique=True, index=True),
        sa.Column("name_de", sa.String(length=255), nullable=False),
        sa.Column("name_en", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "shift_variants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shift_template_id", sa.Integer(), sa.ForeignKey("shift_templates.id"), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("start_day_class", sa.String(length=50), nullable=False),
        sa.Column("end_day_class", sa.String(length=50), nullable=True),
        sa.Column("starts_at", sa.Time(), nullable=False),
        sa.Column("ends_at", sa.Time(), nullable=False),
        sa.Column("end_day_offset", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("required_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.add_column("roster_slots", sa.Column("shift_template_id", sa.Integer(), nullable=True))
    op.add_column("roster_slots", sa.Column("shift_variant_id", sa.Integer(), nullable=True))
    op.add_column("roster_slots", sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("roster_slots", sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("roster_slots", sa.Column("day_class", sa.String(length=50), nullable=True))
    op.create_foreign_key("fk_roster_slots_shift_template", "roster_slots", "shift_templates", ["shift_template_id"], ["id"])
    op.create_foreign_key("fk_roster_slots_shift_variant", "roster_slots", "shift_variants", ["shift_variant_id"], ["id"])
    op.drop_constraint("uq_roster_slot", "roster_slots", type_="unique")
    op.create_unique_constraint(
        "uq_roster_slot",
        "roster_slots",
        ["planning_period_id", "slot_date", "shift_variant_id", "position"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_roster_slot", "roster_slots", type_="unique")
    op.create_unique_constraint("uq_roster_slot", "roster_slots", ["planning_period_id", "slot_date", "position"])
    op.drop_constraint("fk_roster_slots_shift_variant", "roster_slots", type_="foreignkey")
    op.drop_constraint("fk_roster_slots_shift_template", "roster_slots", type_="foreignkey")
    op.drop_column("roster_slots", "day_class")
    op.drop_column("roster_slots", "ends_at")
    op.drop_column("roster_slots", "starts_at")
    op.drop_column("roster_slots", "shift_variant_id")
    op.drop_column("roster_slots", "shift_template_id")
    op.drop_table("shift_variants")
    op.drop_table("shift_templates")
