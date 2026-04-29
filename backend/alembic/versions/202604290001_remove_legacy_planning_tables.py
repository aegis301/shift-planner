"""remove old planning tables

Revision ID: 202604290001
Revises: 202604280004
Create Date: 2026-04-29
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect

revision: str = "202604290001"
down_revision: Union[str, None] = "202604280004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "roster_slots" in tables:
        roster_slot_columns = {column["name"] for column in inspector.get_columns("roster_slots")}
        unique_constraints = {constraint["name"] for constraint in inspector.get_unique_constraints("roster_slots")}
        foreign_keys = {constraint["name"] for constraint in inspector.get_foreign_keys("roster_slots")}

        if "shift_type_id" in roster_slot_columns:
            if "shift_variant_id" in roster_slot_columns and "roster_slot_assignments" in tables:
                op.execute(
                    """
                    DELETE FROM roster_slot_assignments
                    WHERE roster_slot_id IN (
                        SELECT id FROM roster_slots WHERE shift_variant_id IS NULL
                    )
                    """
                )
                op.execute("DELETE FROM roster_slots WHERE shift_variant_id IS NULL")
            for constraint_name in ("roster_slots_shift_type_id_fkey", "fk_roster_slots_shift_type_id"):
                if constraint_name in foreign_keys:
                    op.drop_constraint(constraint_name, "roster_slots", type_="foreignkey")
            if "uq_roster_slot" in unique_constraints:
                op.drop_constraint("uq_roster_slot", "roster_slots", type_="unique")
            op.drop_column("roster_slots", "shift_type_id")

        unique_constraints = {constraint["name"] for constraint in inspect(bind).get_unique_constraints("roster_slots")}
        if "uq_roster_slot" not in unique_constraints:
            op.create_unique_constraint(
                "uq_roster_slot",
                "roster_slots",
                ["planning_period_id", "slot_date", "shift_variant_id", "position"],
            )

    for table_name in ("roster_assignments", "availability_requests", "shift_types"):
        if table_name in tables:
            op.drop_table(table_name)


def downgrade() -> None:
    pass
