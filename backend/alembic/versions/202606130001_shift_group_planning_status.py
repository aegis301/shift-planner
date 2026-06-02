"""per shift group planning status and scoped wishes cells

Revision ID: 202606130001
Revises: 202606120001
Create Date: 2026-06-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202606130001"
down_revision: Union[str, None] = "202606120001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "planning_period_shift_group_statuses" not in inspector.get_table_names():
        op.create_table(
            "planning_period_shift_group_statuses",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "planning_period_id",
                sa.Integer(),
                sa.ForeignKey("planning_periods.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "shift_group_id",
                sa.Integer(),
                sa.ForeignKey("shift_groups.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.UniqueConstraint(
                "planning_period_id",
                "shift_group_id",
                name="uq_planning_period_shift_group_status",
            ),
        )
        op.create_index(
            "ix_planning_period_shift_group_statuses_period",
            "planning_period_shift_group_statuses",
            ["planning_period_id"],
        )
    op.execute(
        sa.text(
            """
            INSERT INTO planning_period_shift_group_statuses
                (planning_period_id, shift_group_id, status, published_at)
            SELECT pp.id, sg.id, pp.status, pp.published_at
            FROM planning_periods pp
            JOIN shift_groups sg ON sg.organization_id = pp.organization_id AND sg.is_active IS TRUE
            ON CONFLICT ON CONSTRAINT uq_planning_period_shift_group_status DO NOTHING
            """
        )
    )

    planning_cell_columns = {col["name"] for col in inspector.get_columns("planning_cells")}
    if "shift_group_id" not in planning_cell_columns:
        op.add_column(
            "planning_cells",
            sa.Column("shift_group_id", sa.Integer(), sa.ForeignKey("shift_groups.id", ondelete="CASCADE"), nullable=True),
        )
    note_columns = {col["name"] for col in inspector.get_columns("team_member_period_notes")}
    if "shift_group_id" not in note_columns:
        op.add_column(
            "team_member_period_notes",
            sa.Column("shift_group_id", sa.Integer(), sa.ForeignKey("shift_groups.id", ondelete="CASCADE"), nullable=True),
        )

    planning_cell_uqs = {uc["name"] for uc in inspector.get_unique_constraints("planning_cells")}
    if "uq_planning_cell" in planning_cell_uqs:
        op.drop_constraint("uq_planning_cell", "planning_cells", type_="unique")
    note_uqs = {uc["name"] for uc in inspector.get_unique_constraints("team_member_period_notes")}
    for legacy_note_uq in ("uq_team_member_period_note", "uq_doctor_period_note"):
        if legacy_note_uq in note_uqs:
            op.drop_constraint(legacy_note_uq, "team_member_period_notes", type_="unique")

    op.execute(
        sa.text(
            """
            UPDATE planning_cells pc
            SET shift_group_id = picked.shift_group_id
            FROM (
                SELECT
                    pc_inner.id AS cell_id,
                    COALESCE(
                        (
                            SELECT MIN(tmsg.shift_group_id)
                            FROM team_member_shift_groups tmsg
                            WHERE tmsg.team_member_id = pc_inner.team_member_id
                        ),
                        (
                            SELECT MIN(sg.id)
                            FROM shift_groups sg
                            JOIN planning_periods pp ON pp.id = pc_inner.planning_period_id
                            WHERE sg.organization_id = pp.organization_id AND sg.is_active IS TRUE
                        )
                    ) AS shift_group_id
                FROM planning_cells pc_inner
                WHERE pc_inner.shift_group_id IS NULL
            ) picked
            WHERE pc.id = picked.cell_id
              AND picked.shift_group_id IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO planning_cells
                (planning_period_id, shift_group_id, team_member_id, cell_date, status, comment, source, created_at, updated_at)
            SELECT
                pc.planning_period_id,
                sg.id,
                pc.team_member_id,
                pc.cell_date,
                pc.status,
                pc.comment,
                pc.source,
                pc.created_at,
                pc.updated_at
            FROM planning_cells pc
            JOIN planning_periods pp ON pp.id = pc.planning_period_id
            JOIN shift_groups sg ON sg.organization_id = pp.organization_id AND sg.is_active IS TRUE
            WHERE pc.shift_group_id IS NOT NULL
              AND sg.id <> pc.shift_group_id
              AND (
                EXISTS (
                    SELECT 1 FROM team_member_shift_groups tmsg
                    WHERE tmsg.team_member_id = pc.team_member_id AND tmsg.shift_group_id = sg.id
                )
                OR NOT EXISTS (
                    SELECT 1 FROM team_member_shift_groups tmsg2
                    WHERE tmsg2.team_member_id = pc.team_member_id
                )
              )
              AND NOT EXISTS (
                SELECT 1 FROM planning_cells existing
                WHERE existing.planning_period_id = pc.planning_period_id
                  AND existing.shift_group_id = sg.id
                  AND existing.team_member_id = pc.team_member_id
                  AND existing.cell_date = pc.cell_date
              )
            """
        )
    )
    op.execute(sa.text("DELETE FROM planning_cells WHERE shift_group_id IS NULL"))

    op.execute(
        sa.text(
            """
            UPDATE team_member_period_notes n
            SET shift_group_id = picked.shift_group_id
            FROM (
                SELECT
                    n_inner.id AS note_id,
                    COALESCE(
                        (
                            SELECT MIN(tmsg.shift_group_id)
                            FROM team_member_shift_groups tmsg
                            WHERE tmsg.team_member_id = n_inner.team_member_id
                        ),
                        (
                            SELECT MIN(sg.id)
                            FROM shift_groups sg
                            JOIN planning_periods pp ON pp.id = n_inner.planning_period_id
                            WHERE sg.organization_id = pp.organization_id AND sg.is_active IS TRUE
                        )
                    ) AS shift_group_id
                FROM team_member_period_notes n_inner
                WHERE n_inner.shift_group_id IS NULL
            ) picked
            WHERE n.id = picked.note_id
              AND picked.shift_group_id IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO team_member_period_notes
                (planning_period_id, shift_group_id, team_member_id, summary, wishes_response_received, created_at, updated_at)
            SELECT
                n.planning_period_id,
                sg.id,
                n.team_member_id,
                n.summary,
                n.wishes_response_received,
                n.created_at,
                n.updated_at
            FROM team_member_period_notes n
            JOIN planning_periods pp ON pp.id = n.planning_period_id
            JOIN shift_groups sg ON sg.organization_id = pp.organization_id AND sg.is_active IS TRUE
            WHERE n.shift_group_id IS NOT NULL
              AND sg.id <> n.shift_group_id
              AND (
                EXISTS (
                    SELECT 1 FROM team_member_shift_groups tmsg
                    WHERE tmsg.team_member_id = n.team_member_id AND tmsg.shift_group_id = sg.id
                )
                OR NOT EXISTS (
                    SELECT 1 FROM team_member_shift_groups tmsg2
                    WHERE tmsg2.team_member_id = n.team_member_id
                )
              )
              AND NOT EXISTS (
                SELECT 1 FROM team_member_period_notes existing
                WHERE existing.planning_period_id = n.planning_period_id
                  AND existing.shift_group_id = sg.id
                  AND existing.team_member_id = n.team_member_id
              )
            """
        )
    )
    op.execute(sa.text("DELETE FROM team_member_period_notes WHERE shift_group_id IS NULL"))

    inspector = sa.inspect(op.get_bind())
    planning_cell_uqs = {uc["name"] for uc in inspector.get_unique_constraints("planning_cells")}
    if "uq_planning_cell" not in planning_cell_uqs:
        op.create_unique_constraint(
            "uq_planning_cell",
            "planning_cells",
            ["planning_period_id", "shift_group_id", "team_member_id", "cell_date"],
        )
    note_uqs = {uc["name"] for uc in inspector.get_unique_constraints("team_member_period_notes")}
    if "uq_team_member_period_note" not in note_uqs:
        op.create_unique_constraint(
            "uq_team_member_period_note",
            "team_member_period_notes",
            ["planning_period_id", "shift_group_id", "team_member_id"],
        )

    op.alter_column("planning_cells", "shift_group_id", nullable=False)
    op.alter_column("team_member_period_notes", "shift_group_id", nullable=False)

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("planning_cells")}
    if "ix_planning_cells_shift_group" not in existing_indexes:
        op.create_index("ix_planning_cells_shift_group", "planning_cells", ["shift_group_id"])
    note_indexes = {idx["name"] for idx in inspector.get_indexes("team_member_period_notes")}
    if "ix_team_member_period_notes_shift_group" not in note_indexes:
        op.create_index("ix_team_member_period_notes_shift_group", "team_member_period_notes", ["shift_group_id"])


def downgrade() -> None:
    op.drop_index("ix_team_member_period_notes_shift_group", table_name="team_member_period_notes")
    op.drop_index("ix_planning_cells_shift_group", table_name="planning_cells")
    op.drop_constraint("uq_team_member_period_note", "team_member_period_notes", type_="unique")
    op.drop_constraint("uq_planning_cell", "planning_cells", type_="unique")

    op.execute(
        sa.text(
            """
            DELETE FROM team_member_period_notes a
            USING team_member_period_notes b
            WHERE a.id > b.id
              AND a.planning_period_id = b.planning_period_id
              AND a.team_member_id = b.team_member_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM planning_cells a
            USING planning_cells b
            WHERE a.id > b.id
              AND a.planning_period_id = b.planning_period_id
              AND a.team_member_id = b.team_member_id
              AND a.cell_date = b.cell_date
            """
        )
    )

    op.drop_column("team_member_period_notes", "shift_group_id")
    op.drop_column("planning_cells", "shift_group_id")
    op.create_unique_constraint(
        "uq_team_member_period_note",
        "team_member_period_notes",
        ["planning_period_id", "team_member_id"],
    )
    op.create_unique_constraint(
        "uq_planning_cell",
        "planning_cells",
        ["planning_period_id", "team_member_id", "cell_date"],
    )
    op.drop_index(
        "ix_planning_period_shift_group_statuses_period",
        table_name="planning_period_shift_group_statuses",
    )
    op.drop_table("planning_period_shift_group_statuses")
