from __future__ import annotations

import json

import sqlalchemy as sa

from app.services.contract_group_defaults import (
    DEFAULT_CONTRACT_GROUP_NAME,
    DEFAULT_VACATION_DAYS_AT_100,
    DEFAULT_WEEKLY_HOURS_AT_100,
    OPEN_ENDED_EMPLOYMENT_START,
    default_category_rules,
    default_regular_week_pattern,
    default_status_mappings,
)


def apply_contract_employment_upgrade(connection) -> None:
    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names())
    dialect = connection.dialect.name
    meta = sa.MetaData()
    if "organizations" in tables:
        sa.Table(
            "organizations",
            meta,
            sa.Column("id", sa.Integer(), primary_key=True),
        )
    if "team_members" in tables:
        sa.Table(
            "team_members",
            meta,
            sa.Column("id", sa.Integer(), primary_key=True),
        )
    if "contract_groups" in tables:
        sa.Table(
            "contract_groups",
            meta,
            sa.Column("id", sa.Integer(), primary_key=True),
        )

    if "contract_groups" not in tables:
        sa.Table(
            "contract_groups",
            meta,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("weekly_hours_at_100", sa.Numeric(8, 2), nullable=False),
            sa.Column("vacation_days_at_100", sa.Numeric(8, 2), nullable=False),
            sa.Column("regular_week_pattern", sa.JSON(), nullable=False),
            sa.Column("category_rules", sa.JSON(), nullable=False),
            sa.Column("status_mappings", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        ).create(connection, checkfirst=True)

    if "employment_periods" not in tables:
        sa.Table(
            "employment_periods",
            meta,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("team_member_id", sa.Integer(), sa.ForeignKey("team_members.id", ondelete="CASCADE"), nullable=False),
            sa.Column("contract_group_id", sa.Integer(), sa.ForeignKey("contract_groups.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("employment_percentage", sa.Integer(), nullable=False),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=True),
        ).create(connection, checkfirst=True)

    if "time_account_openings" not in tables:
        sa.Table(
            "time_account_openings",
            meta,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "team_member_id",
                sa.Integer(),
                sa.ForeignKey("team_members.id", ondelete="CASCADE"),
                nullable=False,
                unique=True,
            ),
            sa.Column("as_of_date", sa.Date(), nullable=False),
            sa.Column("overtime_minutes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("vacation_days_remaining", sa.Numeric(8, 2), nullable=False, server_default="0"),
            sa.Column("sick_days_used_ytd", sa.Numeric(8, 2), nullable=False, server_default="0"),
        ).create(connection, checkfirst=True)

    inspector = sa.inspect(connection)
    org_ids = [row[0] for row in connection.execute(sa.text("SELECT id FROM organizations")).fetchall()]
    existing_orgs = {
        row[0]
        for row in connection.execute(sa.text("SELECT DISTINCT organization_id FROM contract_groups")).fetchall()
    }
    pattern_json = json.dumps(default_regular_week_pattern())
    rules_json = json.dumps(default_category_rules())
    mappings_json = json.dumps(default_status_mappings())
    for org_id in org_ids:
        if org_id in existing_orgs:
            continue
        json_placeholders = (
            "CAST(:regular_week_pattern AS json), CAST(:category_rules AS json), CAST(:status_mappings AS json)"
            if dialect == "postgresql"
            else ":regular_week_pattern, :category_rules, :status_mappings"
        )
        connection.execute(
            sa.text(
                f"""
                INSERT INTO contract_groups (
                    organization_id, name, display_order, is_active,
                    weekly_hours_at_100, vacation_days_at_100,
                    regular_week_pattern, category_rules, status_mappings
                ) VALUES (
                    :organization_id, :name, 0, :is_active,
                    :weekly_hours, :vacation_days,
                    {json_placeholders}
                )
                """
            ),
            {
                "organization_id": org_id,
                "name": DEFAULT_CONTRACT_GROUP_NAME,
                "is_active": True,
                "weekly_hours": DEFAULT_WEEKLY_HOURS_AT_100,
                "vacation_days": DEFAULT_VACATION_DAYS_AT_100,
                "regular_week_pattern": pattern_json,
                "category_rules": rules_json,
                "status_mappings": mappings_json,
            },
        )

    tm_columns = {col["name"] for col in sa.inspect(connection).get_columns("team_members")}
    if "employment_percentage" in tm_columns:
        connection.execute(
            sa.text(
                """
                INSERT INTO employment_periods (
                    team_member_id, contract_group_id, employment_percentage, start_date, end_date
                )
                SELECT
                    tm.id,
                    (
                        SELECT cg.id FROM contract_groups cg
                        WHERE cg.organization_id = tm.organization_id
                        ORDER BY cg.display_order, cg.id
                        LIMIT 1
                    ),
                    tm.employment_percentage,
                    :start_date,
                    NULL
                FROM team_members tm
                WHERE NOT EXISTS (
                    SELECT 1 FROM employment_periods ep WHERE ep.team_member_id = tm.id
                )
                """
            ),
            {"start_date": OPEN_ENDED_EMPLOYMENT_START.isoformat() if dialect == "sqlite" else OPEN_ENDED_EMPLOYMENT_START},
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO time_account_openings (
                    team_member_id, as_of_date, overtime_minutes, vacation_days_remaining, sick_days_used_ytd
                )
                SELECT tm.id, :as_of_date, 0, 0, 0
                FROM team_members tm
                WHERE NOT EXISTS (
                    SELECT 1 FROM time_account_openings tao WHERE tao.team_member_id = tm.id
                )
                """
            ),
            {"as_of_date": OPEN_ENDED_EMPLOYMENT_START.isoformat() if dialect == "sqlite" else OPEN_ENDED_EMPLOYMENT_START},
        )
        if dialect == "sqlite":
            connection.execute(sa.text("ALTER TABLE team_members DROP COLUMN employment_percentage"))
        else:
            connection.execute(sa.text("ALTER TABLE team_members DROP COLUMN IF EXISTS employment_percentage"))
