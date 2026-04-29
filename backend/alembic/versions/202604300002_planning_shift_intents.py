"""planning shift intents and narrow planning cell statuses

Revision ID: 202604300002
Revises: 202604300001
Create Date: 2026-04-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202604300002"
down_revision: Union[str, None] = "202604300001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "planning_shift_intents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("planning_period_id", sa.Integer(), sa.ForeignKey("planning_periods.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cell_date", sa.Date(), nullable=False),
        sa.Column("shift_group_id", sa.Integer(), sa.ForeignKey("shift_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shift_template_id", sa.Integer(), sa.ForeignKey("shift_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint(
            "planning_period_id",
            "doctor_id",
            "cell_date",
            "shift_group_id",
            "shift_template_id",
            name="uq_planning_shift_intent",
        ),
    )
    op.create_index("ix_planning_shift_intents_period", "planning_shift_intents", ["planning_period_id"])
    op.create_index("ix_planning_shift_intents_group", "planning_shift_intents", ["shift_group_id"])
    op.execute(
        sa.text(
            "UPDATE planning_cells SET status = 'frei' "
            "WHERE status NOT IN ('urlaub', 'forschung', 'lehre', 'frei')"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_planning_shift_intents_group", table_name="planning_shift_intents")
    op.drop_index("ix_planning_shift_intents_period", table_name="planning_shift_intents")
    op.drop_table("planning_shift_intents")
