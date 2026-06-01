"""planning day status definitions

Revision ID: 202606110001
Revises: 202606100001
Create Date: 2026-06-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202606110001"
down_revision: Union[str, None] = "202606100001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEFAULT_ROWS = [
    ("urlaub", "Urlaub", "Vacation", "rose", True, 0),
    ("forschung", "Forschung", "Research", "violet", True, 1),
    ("lehre", "Lehre", "Teaching", "amber", True, 2),
    ("frei", "Frei", "Off", "slate", True, 3),
]


def upgrade() -> None:
    op.create_table(
        "planning_day_status_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("label_de", sa.String(length=64), nullable=False),
        sa.Column("label_en", sa.String(length=64), nullable=False),
        sa.Column("color_preset", sa.String(length=32), nullable=False),
        sa.Column("blocks_roster_assignment", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("organization_id", "code", name="uq_planning_day_status_org_code"),
    )
    op.create_index(
        op.f("ix_planning_day_status_definitions_organization_id"),
        "planning_day_status_definitions",
        ["organization_id"],
    )
    conn = op.get_bind()
    org_ids = [row[0] for row in conn.execute(sa.text("SELECT id FROM organizations")).fetchall()]
    for org_id in org_ids:
        for code, label_de, label_en, color_preset, blocks_roster, display_order in _DEFAULT_ROWS:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO planning_day_status_definitions
                    (organization_id, code, label_de, label_en, color_preset, blocks_roster_assignment, display_order, is_active)
                    VALUES (:org_id, :code, :label_de, :label_en, :color_preset, :blocks_roster, :display_order, true)
                    """
                ),
                {
                    "org_id": org_id,
                    "code": code,
                    "label_de": label_de,
                    "label_en": label_en,
                    "color_preset": color_preset,
                    "blocks_roster": blocks_roster,
                    "display_order": display_order,
                },
            )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_planning_day_status_definitions_organization_id"),
        table_name="planning_day_status_definitions",
    )
    op.drop_table("planning_day_status_definitions")
