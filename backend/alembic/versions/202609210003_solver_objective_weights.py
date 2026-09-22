"""org solver objective weights

Revision ID: 202609210003
Revises: 202609210002
Create Date: 2026-09-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609210003"
down_revision: Union[str, None] = "202609210002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEFAULT_WEIGHTS = (
    '{"unfilled": 10000, "duty_count": 250, "fairness": 8, '
    '"wish": 25, "avoid_time_window": 15, "warning": 40, "pair_warning": 70}'
)


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "solver_objective_weights",
            sa.JSON(),
            nullable=False,
            server_default=sa.text(f"'{_DEFAULT_WEIGHTS}'::json"),
        ),
    )
    op.alter_column("organizations", "solver_objective_weights", server_default=None)


def downgrade() -> None:
    raise NotImplementedError("Forward-only migration")
