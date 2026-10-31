import inspect
from contextlib import contextmanager
from datetime import date

from app.models import Organization, ShiftGroup, TeamMemberShiftGroup
from app.models.base import Base
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from mcp_app import server
from mcp_app.server import (
    create_team_member_tool,
    set_shift_group_memberships_tool,
    set_shift_group_team_members_tool,
)

TOKEN = "membership-token"


def test_create_team_member_tool_has_no_shift_group_ids():
    assert "shift_group_ids" not in inspect.signature(create_team_member_tool).parameters


def test_shift_group_tools_write_dated_memberships(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = factory()
    try:
        db.add(Organization(id=1, name="Org", slug="org", plan_tier="team"))
        db.flush()
        db.add(ShiftGroup(id=1, organization_id=1, code="g1", name="G1", display_order=0))
        db.commit()

        @contextmanager
        def same_session():
            yield db

        monkeypatch.setattr(server, "db_session", same_session)
        monkeypatch.setattr(server, "mcp_organization_id", lambda: 1)
        monkeypatch.setattr(server.settings, "mcp_admin_token", TOKEN)

        member = create_team_member_tool(TOKEN, "Ada", "Lovelace", "ada@example.com")
        assert member["shift_group_memberships"] == []

        set_shift_group_memberships_tool(
            TOKEN,
            1,
            [{"team_member_id": member["id"], "start_date": "2020-01-01", "end_date": "2020-06-30"}],
        )
        set_shift_group_team_members_tool(TOKEN, 1, [member["id"]])
        stints = db.scalars(
            select(TeamMemberShiftGroup).order_by(TeamMemberShiftGroup.start_date)
        ).all()
        assert [(row.start_date, row.end_date) for row in stints] == [
            (date(2020, 1, 1), date(2020, 6, 30)),
            (date.today(), None),
        ]
    finally:
        db.close()
        engine.dispose()
