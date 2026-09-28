import pytest
from mcp_app.server import apply_roster_change_set_tool, revert_roster_change_set_tool

from app.services.roster_change_sets import RosterChangeSetError


def test_roster_change_set_tools_require_token():
    with pytest.raises(PermissionError):
        apply_roster_change_set_tool(token="wrong-token", planning_period_id=1, shift_group_id=1, items=[])
    with pytest.raises(PermissionError):
        revert_roster_change_set_tool(token="wrong-token", change_set_id=1)


def test_apply_roster_change_set_tool_uses_service(monkeypatch):
    class ChangeSet:
        id = 4
        organization_id = 1
        planning_period_id = 2
        shift_group_id = 3
        status = "applied"
        mode = "all_or_nothing"
        source = "mcp"
        label = "Paste"
        reverts_change_set_id = None
        items = []

    class DbContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    calls = []

    def fake_apply(db, **kwargs):
        calls.append(kwargs)
        return ChangeSet()

    monkeypatch.setattr("mcp_app.server.db_session", lambda: DbContext())
    monkeypatch.setattr("mcp_app.server.mcp_organization_id", lambda: 1)
    monkeypatch.setattr("mcp_app.server.apply_roster_change_set", fake_apply)
    monkeypatch.setattr("mcp_app.server.require_token", lambda token: None)
    result = apply_roster_change_set_tool(
        token="ok",
        planning_period_id=2,
        shift_group_id=3,
        items=[{"roster_slot_id": 9, "team_member_id": 8}],
        mode="best_effort",
        label="Paste",
    )
    assert result["id"] == 4
    assert result["status"] == "applied"
    assert calls[0]["organization_id"] == 1
    assert calls[0]["mode"] == "best_effort"
    assert calls[0]["items"][0].roster_slot_id == 9
    assert calls[0]["items"][0].team_member_id == 8


def test_apply_tool_rejects_unknown_mode(monkeypatch):
    class DbContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    monkeypatch.setattr("mcp_app.server.db_session", lambda: DbContext())
    monkeypatch.setattr("mcp_app.server.require_token", lambda token: None)
    with pytest.raises(RosterChangeSetError) as exc:
        apply_roster_change_set_tool(
            token="ok",
            planning_period_id=1,
            shift_group_id=1,
            items=[],
            mode="sideways",
        )
    assert exc.value.code == "INVALID_MODE"
