"""day/night band on shift wishes and no-gos

Revision ID: 202610070001
Revises: 202610060001
Create Date: 2026-10-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202610070001"
down_revision: Union[str, None] = "202610060001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "planning_shift_intents",
        sa.Column("band", sa.String(length=10), nullable=False, server_default="all"),
    )
    op.drop_constraint("uq_planning_shift_intent", "planning_shift_intents", type_="unique")
    op.create_unique_constraint(
        "uq_planning_shift_intent",
        "planning_shift_intents",
        ["planning_period_id", "team_member_id", "cell_date", "shift_group_id", "shift_template_id", "band"],
    )
    op.add_column(
        "plan_version_shift_intents",
        sa.Column("band", sa.String(length=10), nullable=False, server_default="all"),
    )
    op.drop_constraint("uq_plan_version_shift_intent", "plan_version_shift_intents", type_="unique")
    op.create_unique_constraint(
        "uq_plan_version_shift_intent",
        "plan_version_shift_intents",
        ["plan_version_id", "team_member_id", "cell_date", "shift_template_id", "band"],
    )


def downgrade() -> None:
    op.execute("DELETE FROM plan_version_shift_intents WHERE band <> 'all'")
    op.drop_constraint("uq_plan_version_shift_intent", "plan_version_shift_intents", type_="unique")
    op.create_unique_constraint(
        "uq_plan_version_shift_intent",
        "plan_version_shift_intents",
        ["plan_version_id", "team_member_id", "cell_date", "shift_template_id"],
    )
    op.drop_column("plan_version_shift_intents", "band")
    op.execute("DELETE FROM planning_shift_intents WHERE band <> 'all'")
    op.drop_constraint("uq_planning_shift_intent", "planning_shift_intents", type_="unique")
    op.create_unique_constraint(
        "uq_planning_shift_intent",
        "planning_shift_intents",
        ["planning_period_id", "team_member_id", "cell_date", "shift_group_id", "shift_template_id"],
    )
    op.drop_column("planning_shift_intents", "band")
