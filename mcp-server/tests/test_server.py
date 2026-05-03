import pytest

from mcp_app.server import (
    bulk_upsert_planning_shift_intents_tool,
    create_shift_template_tool,
    delete_planning_period_tool,
    delete_shift_template_tool,
    delete_shift_variant_tool,
    delete_team_member_tool,
    regenerate_planning_period_roster_tool,
    require_token,
    upsert_planning_cell_tool,
    upsert_roster_slot_assignment_tool,
)


def test_require_token_rejects_invalid_token():
    with pytest.raises(PermissionError):
        require_token("wrong-token")


def test_matrix_tool_rejects_invalid_token_before_db_access():
    with pytest.raises(PermissionError):
        upsert_planning_cell_tool(
            token="wrong-token",
            planning_period_id=1,
            team_member_id=1,
            cell_date="2026-07-01",
            status="frei",
        )


def test_bulk_shift_intents_tool_rejects_invalid_token_before_db_access():
    with pytest.raises(PermissionError):
        bulk_upsert_planning_shift_intents_tool(token="wrong-token", planning_period_id=1, intents=[])


def test_roster_slot_assignment_tool_rejects_invalid_token_before_db_access():
    with pytest.raises(PermissionError):
        upsert_roster_slot_assignment_tool(
            token="wrong-token",
            roster_slot_id=1,
            team_member_id=1,
        )


def test_shift_template_tool_rejects_invalid_token_before_db_access():
    with pytest.raises(PermissionError):
        create_shift_template_tool(
            token="wrong-token",
            code="RD",
            name_de="Rufdienst",
            name_en="Stand-by duty",
            category="rufdienst",
        )


def test_destructive_planning_tools_reject_invalid_token_before_db_access():
    with pytest.raises(PermissionError):
        regenerate_planning_period_roster_tool(token="wrong-token", planning_period_id=1)
    with pytest.raises(PermissionError):
        delete_planning_period_tool(token="wrong-token", planning_period_id=1)
    with pytest.raises(PermissionError):
        delete_shift_template_tool(token="wrong-token", shift_template_id=1)
    with pytest.raises(PermissionError):
        delete_shift_variant_tool(token="wrong-token", shift_variant_id=1)
    with pytest.raises(PermissionError):
        delete_team_member_tool(token="wrong-token", team_member_id=1)
