"""period rosters and dated shift group membership

Revision ID: 202608270001
Revises: 202606180001
Create Date: 2026-08-27
"""

from __future__ import annotations

import calendar
from datetime import date
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202608270001"
down_revision: Union[str, None] = "202606180001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _stint_overlaps_month(start_date: date, end_date: date | None, month_start: date, month_end: date) -> bool:
    stint_end = end_date if end_date is not None else date.max
    return start_date <= month_end and stint_end >= month_start


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    tmsg_columns = {col["name"] for col in inspector.get_columns("team_member_shift_groups")}
    if "start_date" not in tmsg_columns:
        op.add_column("team_member_shift_groups", sa.Column("start_date", sa.Date(), nullable=True))
    if "end_date" not in tmsg_columns:
        op.add_column("team_member_shift_groups", sa.Column("end_date", sa.Date(), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE team_member_shift_groups AS tmsg
            SET start_date = COALESCE(tm.created_at::date, DATE '2000-01-01')
            FROM team_members AS tm
            WHERE tm.id = tmsg.team_member_id AND tmsg.start_date IS NULL
            """
        )
    )
    op.alter_column("team_member_shift_groups", "start_date", nullable=False)

    constraints = {c["name"] for c in inspector.get_unique_constraints("team_member_shift_groups")}
    if "uq_team_member_shift_group" in constraints:
        op.drop_constraint("uq_team_member_shift_group", "team_member_shift_groups", type_="unique")

    if "planning_period_shift_group_members" not in inspector.get_table_names():
        op.create_table(
            "planning_period_shift_group_members",
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
            sa.Column(
                "team_member_id",
                sa.Integer(),
                sa.ForeignKey("team_members.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("source", sa.String(length=50), nullable=False, server_default="seeded"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.UniqueConstraint(
                "planning_period_id",
                "shift_group_id",
                "team_member_id",
                name="uq_planning_period_shift_group_member",
            ),
        )
        op.create_index(
            "ix_planning_period_shift_group_members_period",
            "planning_period_shift_group_members",
            ["planning_period_id"],
        )
        op.create_index(
            "ix_planning_period_shift_group_members_group",
            "planning_period_shift_group_members",
            ["shift_group_id"],
        )

    if "plan_version_team_members" not in inspector.get_table_names():
        op.create_table(
            "plan_version_team_members",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "plan_version_id",
                sa.Integer(),
                sa.ForeignKey("planning_plan_versions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("team_member_id", sa.Integer(), nullable=False),
            sa.Column("first_name", sa.String(length=255), nullable=False),
            sa.Column("last_name", sa.String(length=255), nullable=False),
            sa.Column("nickname", sa.String(length=64), nullable=True),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("employment_percentage", sa.Integer(), nullable=True),
            sa.Column("planning_preferences", sa.Text(), nullable=True),
            sa.UniqueConstraint("plan_version_id", "team_member_id", name="uq_plan_version_team_member"),
        )

    connection = op.get_bind()
    periods = connection.execute(
        sa.text("SELECT id, organization_id, year, month FROM planning_periods ORDER BY id")
    ).fetchall()
    groups = connection.execute(sa.text("SELECT id, organization_id FROM shift_groups ORDER BY id")).fetchall()
    groups_by_org: dict[int, list[int]] = {}
    for group_id, org_id in groups:
        groups_by_org.setdefault(org_id, []).append(group_id)

    stints = connection.execute(
        sa.text(
            """
            SELECT tmsg.team_member_id, tmsg.shift_group_id, tmsg.start_date, tmsg.end_date, tm.is_active
            FROM team_member_shift_groups AS tmsg
            JOIN team_members AS tm ON tm.id = tmsg.team_member_id
            """
        )
    ).fetchall()
    stints_by_group: dict[int, list[tuple[int, date, date | None, bool]]] = {}
    for team_member_id, shift_group_id, start_date, end_date, is_active in stints:
        stints_by_group.setdefault(shift_group_id, []).append(
            (team_member_id, start_date, end_date, bool(is_active))
        )

    existing_roster = {
        (row[0], row[1], row[2])
        for row in connection.execute(
            sa.text(
                "SELECT planning_period_id, shift_group_id, team_member_id "
                "FROM planning_period_shift_group_members"
            )
        ).fetchall()
    }

    for period_id, org_id, year, month in periods:
        month_start, month_end = _month_bounds(year, month)
        org_groups = groups_by_org.get(org_id, [])
        member_ids_with_data: dict[int, set[int]] = {gid: set() for gid in org_groups}

        for table, group_col in (
            ("planning_cells", "shift_group_id"),
            ("planning_shift_intents", "shift_group_id"),
            ("team_member_period_notes", "shift_group_id"),
        ):
            rows = connection.execute(
                sa.text(
                    f"SELECT {group_col}, team_member_id FROM {table} WHERE planning_period_id = :period_id"
                ),
                {"period_id": period_id},
            ).fetchall()
            for group_id, team_member_id in rows:
                if group_id in member_ids_with_data:
                    member_ids_with_data[group_id].add(team_member_id)

        assignment_rows = connection.execute(
            sa.text(
                """
                SELECT DISTINCT sgst.shift_group_id, rsa.team_member_id
                FROM roster_slot_assignments AS rsa
                JOIN roster_slots AS rs ON rs.id = rsa.roster_slot_id
                JOIN shift_group_shift_templates AS sgst ON sgst.shift_template_id = rs.shift_template_id
                WHERE rs.planning_period_id = :period_id
                """
            ),
            {"period_id": period_id},
        ).fetchall()
        for group_id, team_member_id in assignment_rows:
            if group_id in member_ids_with_data:
                member_ids_with_data[group_id].add(team_member_id)

        for group_id in org_groups:
            roster_ids: set[int] = set(member_ids_with_data.get(group_id, set()))
            for team_member_id, start_date, end_date, is_active in stints_by_group.get(group_id, []):
                if not is_active:
                    continue
                if _stint_overlaps_month(start_date, end_date, month_start, month_end):
                    roster_ids.add(team_member_id)
            for team_member_id in roster_ids:
                key = (period_id, group_id, team_member_id)
                if key in existing_roster:
                    continue
                connection.execute(
                    sa.text(
                        """
                        INSERT INTO planning_period_shift_group_members
                            (planning_period_id, shift_group_id, team_member_id, source)
                        VALUES (:period_id, :group_id, :team_member_id, 'seeded')
                        """
                    ),
                    {"period_id": period_id, "group_id": group_id, "team_member_id": team_member_id},
                )
                existing_roster.add(key)

    versions = connection.execute(
        sa.text(
            """
            SELECT id, planning_period_id, shift_group_id
            FROM planning_plan_versions
            ORDER BY id
            """
        )
    ).fetchall()
    for version_id, planning_period_id, shift_group_id in versions:
        existing_version_members = {
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT team_member_id FROM plan_version_team_members WHERE plan_version_id = :version_id"
                ),
                {"version_id": version_id},
            ).fetchall()
        }
        roster_member_ids = {
            row[0]
            for row in connection.execute(
                sa.text(
                    """
                    SELECT team_member_id
                    FROM planning_period_shift_group_members
                    WHERE planning_period_id = :period_id AND shift_group_id = :group_id
                    """
                ),
                {"period_id": planning_period_id, "group_id": shift_group_id},
            ).fetchall()
        }
        data_member_ids: set[int] = set()
        for table in (
            "plan_version_planning_cells",
            "plan_version_shift_intents",
            "plan_version_member_notes",
            "plan_version_roster_assignments",
        ):
            rows = connection.execute(
                sa.text(f"SELECT DISTINCT team_member_id FROM {table} WHERE plan_version_id = :version_id"),
                {"version_id": version_id},
            ).fetchall()
            data_member_ids.update(row[0] for row in rows)
        all_member_ids = roster_member_ids | data_member_ids
        for team_member_id in all_member_ids:
            if team_member_id in existing_version_members:
                continue
            member_row = connection.execute(
                sa.text(
                    """
                    SELECT first_name, last_name, nickname, email, employment_percentage, planning_preferences
                    FROM team_members WHERE id = :member_id
                    """
                ),
                {"member_id": team_member_id},
            ).fetchone()
            if member_row is None:
                continue
            connection.execute(
                sa.text(
                    """
                    INSERT INTO plan_version_team_members
                        (plan_version_id, team_member_id, first_name, last_name, nickname, email,
                         employment_percentage, planning_preferences)
                    VALUES
                        (:version_id, :team_member_id, :first_name, :last_name, :nickname, :email,
                         :employment_percentage, :planning_preferences)
                    """
                ),
                {
                    "version_id": version_id,
                    "team_member_id": team_member_id,
                    "first_name": member_row[0],
                    "last_name": member_row[1],
                    "nickname": member_row[2],
                    "email": member_row[3],
                    "employment_percentage": member_row[4],
                    "planning_preferences": member_row[5],
                },
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "plan_version_team_members" in inspector.get_table_names():
        op.drop_table("plan_version_team_members")
    if "planning_period_shift_group_members" in inspector.get_table_names():
        op.drop_table("planning_period_shift_group_members")
    op.drop_column("team_member_shift_groups", "end_date")
    op.drop_column("team_member_shift_groups", "start_date")
    op.create_unique_constraint(
        "uq_team_member_shift_group",
        "team_member_shift_groups",
        ["team_member_id", "shift_group_id"],
    )
