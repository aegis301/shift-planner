"""matrix planning

Revision ID: 202604280001
Revises: 202604260001
Create Date: 2026-04-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202604280001"
down_revision: Union[str, None] = "202604260001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "planning_cells",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("planning_period_id", sa.Integer(), sa.ForeignKey("planning_periods.id"), nullable=False),
        sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("doctors.id"), nullable=False),
        sa.Column("cell_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("planning_period_id", "doctor_id", "cell_date", name="uq_planning_cell"),
    )
    op.create_table(
        "doctor_period_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("planning_period_id", sa.Integer(), sa.ForeignKey("planning_periods.id"), nullable=False),
        sa.Column("doctor_id", sa.Integer(), sa.ForeignKey("doctors.id"), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("planning_period_id", "doctor_id", name="uq_doctor_period_note"),
    )

    op.execute(
        """
        INSERT INTO planning_cells (planning_period_id, doctor_id, cell_date, status, comment, source)
        SELECT planning_period_id,
               doctor_id,
               request_date,
               CASE request_type
                   WHEN 'wish' THEN 'dienstwunsch'
                   WHEN 'no_go' THEN 'kein_dienst'
                   WHEN 'preference' THEN 'dienstwunsch'
                   ELSE 'dienstwunsch'
               END,
               note,
               'legacy_request'
        FROM availability_requests
        ON CONFLICT ON CONSTRAINT uq_planning_cell DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("doctor_period_notes")
    op.drop_table("planning_cells")

