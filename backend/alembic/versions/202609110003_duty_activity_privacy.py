"""duty activity access policy and purpose acknowledgement

Revision ID: 202609110003
Revises: 202609110002
Create Date: 2026-09-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609110003"
down_revision: Union[str, None] = "202609110002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEFAULT_POLICY = (
    '{"individual_read_roles": [], "retention_months": 24, '
    '"purpose_statement": "", "small_group_threshold": 5}'
)


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "duty_activity_access_policy",
            sa.JSON(),
            nullable=False,
            server_default=sa.text(f"'{_DEFAULT_POLICY}'::json"),
        ),
    )
    op.alter_column("organizations", "duty_activity_access_policy", server_default=None)
    op.add_column(
        "team_members",
        sa.Column("duty_activity_purpose_acknowledged_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    raise NotImplementedError("Forward-only migration")
