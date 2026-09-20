"""org fairness policy and time-account fairness openings

Revision ID: 202609110004
Revises: 202609110003
Create Date: 2026-09-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609110004"
down_revision: Union[str, None] = "202609110003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEFAULT_POLICY = (
    '{"window_months": 12, "dimensions": ['
    '{"id": "duties", "metric": "duty_count", "day_filter": "any", "night": false, "category": null}, '
    '{"id": "weekend_holiday", "metric": "duty_count", "day_filter": "weekend_holiday", "night": false, "category": null}, '
    '{"id": "night", "metric": "duty_count", "day_filter": "any", "night": true, "category": null}, '
    '{"id": "statutory_hours", "metric": "statutory_minutes", "day_filter": "any", "night": false, "category": null}'
    "]}"
)


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "fairness_policy",
            sa.JSON(),
            nullable=False,
            server_default=sa.text(f"'{_DEFAULT_POLICY}'::json"),
        ),
    )
    op.alter_column("organizations", "fairness_policy", server_default=None)
    op.add_column(
        "time_account_openings",
        sa.Column(
            "fairness_balances",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )
    op.alter_column("time_account_openings", "fairness_balances", server_default=None)


def downgrade() -> None:
    raise NotImplementedError("Forward-only migration")
