"""backfill max_duties_per_period categories on stored rule sets

Revision ID: 202609200002
Revises: 202609110004
Create Date: 2026-09-20
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.services.work_time_rule_sets import backfill_max_duties_categories

revision: str = "202609200002"
down_revision: Union[str, None] = "202609110004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _backfill_table(table_name: str) -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text(f"SELECT id, rules FROM {table_name}")).mappings().all()
    for row in rows:
        original = row["rules"]
        if isinstance(original, str):
            original = json.loads(original)
        updated = backfill_max_duties_categories(original)
        if updated == original:
            continue
        bind.execute(
            sa.text(f"UPDATE {table_name} SET rules = CAST(:rules AS json) WHERE id = :id"),
            {"rules": json.dumps(updated), "id": row["id"]},
        )


def upgrade() -> None:
    _backfill_table("work_time_rule_sets")
    _backfill_table("work_time_rule_set_presets")


def downgrade() -> None:
    raise NotImplementedError("Forward-only migration")
