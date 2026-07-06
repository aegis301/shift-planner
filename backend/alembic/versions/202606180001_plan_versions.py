"""plan versions and snapshot tables

Revision ID: 202606180001
Revises: 202606140001
Create Date: 2026-06-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202606180001"
down_revision: Union[str, None] = "202606140001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    status_columns = {col["name"] for col in inspector.get_columns("planning_period_shift_group_statuses")}
    if "working_major_version" not in status_columns:
        op.add_column(
            "planning_period_shift_group_statuses",
            sa.Column("working_major_version", sa.Integer(), nullable=True),
        )
    if "working_minor_version" not in status_columns:
        op.add_column(
            "planning_period_shift_group_statuses",
            sa.Column("working_minor_version", sa.Integer(), nullable=True),
        )
    if "first_published_at" not in status_columns:
        op.add_column(
            "planning_period_shift_group_statuses",
            sa.Column("first_published_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "planning_plan_versions" not in inspector.get_table_names():
        op.create_table(
            "planning_plan_versions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "organization_id",
                sa.Integer(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
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
            sa.Column("major_version", sa.Integer(), nullable=False),
            sa.Column("minor_version", sa.Integer(), nullable=False),
            sa.Column("lifecycle_phase", sa.String(length=50), nullable=False),
            sa.Column("trigger", sa.String(length=50), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column(
                "created_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.UniqueConstraint(
                "planning_period_id",
                "shift_group_id",
                "major_version",
                "minor_version",
                name="uq_planning_plan_version",
            ),
        )
        op.create_index("ix_planning_plan_versions_period", "planning_plan_versions", ["planning_period_id"])

    table_names = {name for name in inspector.get_table_names()}
    if "plan_version_roster_slots" not in table_names:
        op.create_table(
            "plan_version_roster_slots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "plan_version_id",
                sa.Integer(),
                sa.ForeignKey("planning_plan_versions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("shift_template_id", sa.Integer(), nullable=True),
            sa.Column("shift_variant_id", sa.Integer(), nullable=True),
            sa.Column("slot_date", sa.Date(), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("label", sa.String(length=255), nullable=True),
            sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("day_class", sa.String(length=50), nullable=True),
            sa.Column("source", sa.String(length=50), nullable=False, server_default="template"),
            sa.Column("template_code", sa.String(length=100), nullable=True),
            sa.Column("template_name", sa.String(length=255), nullable=True),
            sa.Column("variant_label", sa.String(length=255), nullable=True),
            sa.UniqueConstraint(
                "plan_version_id",
                "slot_date",
                "shift_variant_id",
                "position",
                name="uq_plan_version_roster_slot",
            ),
        )
    if "plan_version_roster_assignments" not in table_names:
        op.create_table(
            "plan_version_roster_assignments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "plan_version_id",
                sa.Integer(),
                sa.ForeignKey("planning_plan_versions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("slot_date", sa.Date(), nullable=False),
            sa.Column("shift_variant_id", sa.Integer(), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("team_member_id", sa.Integer(), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("manual_override", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.UniqueConstraint(
                "plan_version_id",
                "slot_date",
                "shift_variant_id",
                "position",
                name="uq_plan_version_roster_assignment",
            ),
        )
    if "plan_version_planning_cells" not in table_names:
        op.create_table(
            "plan_version_planning_cells",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "plan_version_id",
                sa.Integer(),
                sa.ForeignKey("planning_plan_versions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("team_member_id", sa.Integer(), nullable=False),
            sa.Column("cell_date", sa.Date(), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("source", sa.String(length=50), nullable=False, server_default="manual"),
            sa.UniqueConstraint(
                "plan_version_id",
                "team_member_id",
                "cell_date",
                name="uq_plan_version_planning_cell",
            ),
        )
    if "plan_version_shift_intents" not in table_names:
        op.create_table(
            "plan_version_shift_intents",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "plan_version_id",
                sa.Integer(),
                sa.ForeignKey("planning_plan_versions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("team_member_id", sa.Integer(), nullable=False),
            sa.Column("cell_date", sa.Date(), nullable=False),
            sa.Column("shift_template_id", sa.Integer(), nullable=False),
            sa.Column("kind", sa.String(length=20), nullable=False),
            sa.Column("source", sa.String(length=50), nullable=False, server_default="manual"),
            sa.UniqueConstraint(
                "plan_version_id",
                "team_member_id",
                "cell_date",
                "shift_template_id",
                name="uq_plan_version_shift_intent",
            ),
        )
    if "plan_version_member_notes" not in table_names:
        op.create_table(
            "plan_version_member_notes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "plan_version_id",
                sa.Integer(),
                sa.ForeignKey("planning_plan_versions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("team_member_id", sa.Integer(), nullable=False),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("wishes_response_received", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.UniqueConstraint("plan_version_id", "team_member_id", name="uq_plan_version_member_note"),
        )


def downgrade() -> None:
    for table in (
        "plan_version_member_notes",
        "plan_version_shift_intents",
        "plan_version_planning_cells",
        "plan_version_roster_assignments",
        "plan_version_roster_slots",
        "planning_plan_versions",
    ):
        op.drop_table(table)
    op.drop_column("planning_period_shift_group_statuses", "first_published_at")
    op.drop_column("planning_period_shift_group_statuses", "working_minor_version")
    op.drop_column("planning_period_shift_group_statuses", "working_major_version")
