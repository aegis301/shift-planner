"""roster slot matrix

Revision ID: 202604280002
Revises: 202604280001
Create Date: 2026-04-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202604280002"
down_revision: Union[str, None] = "202604280001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "roster_slots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("planning_period_id", sa.Integer(), sa.ForeignKey("planning_periods.id"), nullable=False),
        sa.Column("shift_type_id", sa.Integer(), sa.ForeignKey("shift_types.id"), nullable=False),
        sa.Column("slot_date", sa.Date(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("planning_period_id", "slot_date", "shift_type_id", "position", name="uq_roster_slot"),
    )
    op.create_table(
        "roster_slot_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("roster_slot_id", sa.Integer(), sa.ForeignKey("roster_slots.id"), nullable=False, unique=True),
        sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("doctors.id"), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("manual_override", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("roster_slot_assignments")
    op.drop_table("roster_slots")
