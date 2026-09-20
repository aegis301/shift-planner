"""work time rule set presets

Revision ID: 202609100005
Revises: 202609100004
Create Date: 2026-09-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609100005"
down_revision: Union[str, None] = "202609100004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "work_time_rule_set_presets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("values_confirmed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("rules", sa.JSON(), nullable=False),
        sa.Column("contract_groups", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", name="uq_work_time_rule_set_preset_code"),
    )
    op.create_index("ix_work_time_rule_set_presets_code", "work_time_rule_set_presets", ["code"], unique=True)


def downgrade() -> None:
    raise NotImplementedError("Forward-only migration")
