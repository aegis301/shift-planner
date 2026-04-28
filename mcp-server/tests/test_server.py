import pytest

from mcp_app.server import require_token, upsert_planning_cell_tool, upsert_roster_slot_assignment_tool


def test_require_token_rejects_invalid_token():
    with pytest.raises(PermissionError):
        require_token("wrong-token")


def test_matrix_tool_rejects_invalid_token_before_db_access():
    with pytest.raises(PermissionError):
        upsert_planning_cell_tool(
            token="wrong-token",
            planning_period_id=1,
            doctor_id=1,
            cell_date="2026-07-01",
            status="tagdienst",
        )


def test_roster_slot_assignment_tool_rejects_invalid_token_before_db_access():
    with pytest.raises(PermissionError):
        upsert_roster_slot_assignment_tool(
            token="wrong-token",
            roster_slot_id=1,
            doctor_id=1,
        )
