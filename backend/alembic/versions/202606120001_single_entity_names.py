"""single entity names

Revision ID: 202606120001
Revises: 202606110001
Create Date: 2026-06-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202606120001"
down_revision: Union[str, None] = "202606110001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _merge_name(table: str, code_col: str = "code") -> None:
    op.add_column(table, sa.Column("name", sa.String(length=255), nullable=True))
    op.execute(
        sa.text(
            f"""
            UPDATE {table}
            SET name = COALESCE(
                NULLIF(TRIM(name_de), ''),
                NULLIF(TRIM(name_en), ''),
                {code_col}
            )
            """
        )
    )
    op.alter_column(table, "name", nullable=False)
    op.drop_column(table, "name_de")
    op.drop_column(table, "name_en")


def upgrade() -> None:
    _merge_name("shift_groups")
    _merge_name("shift_templates")

    op.add_column(
        "planning_day_status_definitions",
        sa.Column("label", sa.String(length=64), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE planning_day_status_definitions
            SET label = COALESCE(
                NULLIF(TRIM(label_de), ''),
                NULLIF(TRIM(label_en), ''),
                code
            )
            """
        )
    )
    op.alter_column("planning_day_status_definitions", "label", nullable=False)
    op.drop_column("planning_day_status_definitions", "label_de")
    op.drop_column("planning_day_status_definitions", "label_en")


def downgrade() -> None:
    op.add_column(
        "planning_day_status_definitions",
        sa.Column("label_de", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "planning_day_status_definitions",
        sa.Column("label_en", sa.String(length=64), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE planning_day_status_definitions
            SET label_de = label, label_en = label
            """
        )
    )
    op.alter_column("planning_day_status_definitions", "label_de", nullable=False)
    op.alter_column("planning_day_status_definitions", "label_en", nullable=False)
    op.drop_column("planning_day_status_definitions", "label")

    for table in ("shift_templates", "shift_groups"):
        op.add_column(table, sa.Column("name_de", sa.String(length=255), nullable=True))
        op.add_column(table, sa.Column("name_en", sa.String(length=255), nullable=True))
        op.execute(sa.text(f"UPDATE {table} SET name_de = name, name_en = name"))
        op.alter_column(table, "name_de", nullable=False)
        op.alter_column(table, "name_en", nullable=False)
        op.drop_column(table, "name")
