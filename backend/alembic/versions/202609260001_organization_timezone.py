"""organization timezone and real slot instants

Revision ID: 202609260001
Revises: 202609220001
Create Date: 2026-09-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609260001"
down_revision: Union[str, None] = "202609220001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _convert_pair(table: str, join_sql: str, extra_where: str = "") -> str:
    where = f"WHERE {extra_where}" if extra_where else ""
    return f"""
        UPDATE {table} AS row
        SET
            starts_at = CASE
                WHEN row.starts_at IS NULL THEN NULL
                ELSE (row.starts_at AT TIME ZONE 'UTC') AT TIME ZONE org.timezone
            END,
            ends_at = CASE
                WHEN row.ends_at IS NULL THEN NULL
                ELSE (row.ends_at AT TIME ZONE 'UTC') AT TIME ZONE org.timezone
            END
        FROM {join_sql}
        {where}
    """


def _revert_pair(table: str, join_sql: str, extra_where: str = "") -> str:
    where = f"WHERE {extra_where}" if extra_where else ""
    return f"""
        UPDATE {table} AS row
        SET
            starts_at = CASE
                WHEN row.starts_at IS NULL THEN NULL
                ELSE (row.starts_at AT TIME ZONE org.timezone) AT TIME ZONE 'UTC'
            END,
            ends_at = CASE
                WHEN row.ends_at IS NULL THEN NULL
                ELSE (row.ends_at AT TIME ZONE org.timezone) AT TIME ZONE 'UTC'
            END
        FROM {join_sql}
        {where}
    """


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Europe/Berlin"),
    )
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        _convert_pair(
            "roster_slots",
            "planning_periods AS period JOIN organizations AS org ON org.id = period.organization_id",
            "row.planning_period_id = period.id",
        )
    )
    op.execute(
        _convert_pair(
            "plan_version_roster_slots",
            "planning_plan_versions AS version JOIN organizations AS org ON org.id = version.organization_id",
            "row.plan_version_id = version.id",
        )
    )
    op.execute(
        """
        UPDATE time_entries AS row
        SET
            started_at = CASE
                WHEN row.started_at IS NULL THEN NULL
                ELSE (row.started_at AT TIME ZONE 'UTC') AT TIME ZONE org.timezone
            END,
            ended_at = CASE
                WHEN row.ended_at IS NULL THEN NULL
                ELSE (row.ended_at AT TIME ZONE 'UTC') AT TIME ZONE org.timezone
            END
        FROM organizations AS org
        WHERE row.organization_id = org.id
          AND row.source = 'roster'
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            _revert_pair(
                "roster_slots",
                "planning_periods AS period JOIN organizations AS org ON org.id = period.organization_id",
                "row.planning_period_id = period.id",
            )
        )
        op.execute(
            _revert_pair(
                "plan_version_roster_slots",
                "planning_plan_versions AS version JOIN organizations AS org ON org.id = version.organization_id",
                "row.plan_version_id = version.id",
            )
        )
        op.execute(
            """
            UPDATE time_entries AS row
            SET
                started_at = CASE
                    WHEN row.started_at IS NULL THEN NULL
                    ELSE (row.started_at AT TIME ZONE org.timezone) AT TIME ZONE 'UTC'
                END,
                ended_at = CASE
                    WHEN row.ended_at IS NULL THEN NULL
                    ELSE (row.ended_at AT TIME ZONE org.timezone) AT TIME ZONE 'UTC'
                END
            FROM organizations AS org
            WHERE row.organization_id = org.id
              AND row.source = 'roster'
            """
        )
    op.drop_column("organizations", "timezone")
