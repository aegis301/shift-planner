from datetime import date

import pytest

from mcp_app import server
from mcp_app.server import (
    bulk_upsert_planning_shift_intents_tool,
    create_contract_group_tool,
    create_shift_template_tool,
    delete_planning_period_tool,
    delete_shift_template_tool,
    delete_shift_variant_tool,
    delete_team_member_tool,
    filter_team_member_property_matrix_tool,
    regenerate_planning_period_roster_tool,
    replace_employment_periods_tool,
    replace_team_member_planning_patterns_tool,
    require_token,
    sync_planning_period_roster_tool,
    upsert_planning_cell_tool,
    upsert_roster_slot_assignment_tool,
    upsert_time_entry_tool,
    get_hours_ledger_tool,
    create_work_time_rule_set_tool,
    delete_work_time_rule_set_tool,
    adopt_work_time_rule_set_preset_tool,
    update_work_time_rule_set_tool,
    record_work_time_consent_tool,
    revoke_work_time_consent_tool,
    record_duty_activity_tool,
)


def test_require_token_rejects_invalid_token():
    with pytest.raises(PermissionError):
        require_token("wrong-token")


def test_contract_group_and_employment_writes_require_token():
    with pytest.raises(PermissionError):
        create_contract_group_tool(token="wrong-token", name="X")
    with pytest.raises(PermissionError):
        replace_employment_periods_tool(token="wrong-token", team_member_id=1, periods=[])


def test_upsert_time_entry_requires_token():
    with pytest.raises(PermissionError):
        upsert_time_entry_tool(
            token="wrong-token",
            team_member_id=1,
            entry_date=date(2026, 8, 1),
            kind="work",
        )


def test_work_time_rule_set_writes_require_token():
    with pytest.raises(PermissionError):
        create_work_time_rule_set_tool(token="wrong-token", name="ArbZG")
    with pytest.raises(PermissionError):
        update_work_time_rule_set_tool(token="wrong-token", rule_set_id=1, name="ArbZG")
    with pytest.raises(PermissionError):
        delete_work_time_rule_set_tool(token="wrong-token", rule_set_id=1)
    with pytest.raises(PermissionError):
        adopt_work_time_rule_set_preset_tool(token="wrong-token", code="tv_aerzte_tdl")


def test_work_time_consent_writes_require_token():
    with pytest.raises(PermissionError):
        record_work_time_consent_tool(
            token="wrong-token",
            team_member_id=1,
            tier="stufe_i",
            valid_from=date(2026, 1, 1),
        )
    with pytest.raises(PermissionError):
        revoke_work_time_consent_tool(token="wrong-token", consent_id=1)


def test_record_duty_activity_requires_token():
    with pytest.raises(PermissionError):
        record_duty_activity_tool(
            token="wrong-token",
            team_member_id=1,
            roster_slot_id=1,
            kind="call_out",
            started_at=date(2026, 3, 1),
            ended_at=date(2026, 3, 1),
        )


def test_get_hours_ledger_tool_uses_service(monkeypatch):
    class LedgerResult:
        def model_dump(self, *, mode: str):
            assert mode == "json"
            return {"team_member_id": 4, "totals": {"statutory_minutes": 10, "credited_minutes": 20}}

    class DbContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    calls = []

    def fake_ledger(db, **kwargs):
        calls.append((db, kwargs))
        return LedgerResult()

    monkeypatch.setattr(server, "db_session", lambda: DbContext())
    monkeypatch.setattr(server, "mcp_organization_id", lambda: 23)
    monkeypatch.setattr(server, "get_hours_ledger", fake_ledger)

    result = get_hours_ledger_tool(
        team_member_id=4,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
    )
    assert result["totals"]["statutory_minutes"] == 10
    assert result["totals"]["credited_minutes"] == 20
    assert calls[0][1]["organization_id"] == 23
    assert calls[0][1]["include_reconciliation"] is True


def test_filter_team_member_property_matrix_tool_uses_service(monkeypatch):
    class MatrixResult:
        def model_dump(self, *, mode: str):
            assert mode == "json"
            return {"definitions": [], "members": [], "values": []}

    class DbContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    calls = []

    def get_matrix(db, **kwargs):
        calls.append((db, kwargs))
        return MatrixResult()

    monkeypatch.setattr(server, "db_session", lambda: DbContext())
    monkeypatch.setattr(server, "mcp_organization_id", lambda: 23)
    monkeypatch.setattr(server, "get_team_member_property_matrix", get_matrix)

    result = filter_team_member_property_matrix_tool(
        filters=[
            {
                "property_definition_id": 4,
                "operator": "greater_or_equal",
                "value": 5,
            }
        ]
    )

    assert result == {"definitions": [], "members": [], "values": []}
    assert calls[0][1]["organization_id"] == 23
    assert calls[0][1]["filters"][0].property_definition_id == 4
    assert calls[0][1]["filters"][0].operator == "greater_or_equal"


def test_matrix_tool_rejects_invalid_token_before_db_access():
    with pytest.raises(PermissionError):
        upsert_planning_cell_tool(
            token="wrong-token",
            planning_period_id=1,
            shift_group_id=1,
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


def test_replace_planning_patterns_tool_rejects_invalid_token_before_db_access():
    with pytest.raises(PermissionError):
        replace_team_member_planning_patterns_tool(token="wrong-token", team_member_id=1, patterns=[])


def test_shift_template_tool_rejects_invalid_token_before_db_access():
    with pytest.raises(PermissionError):
        create_shift_template_tool(
            token="wrong-token",
            code="RD",
            name="Rufdienst",
            category="rufdienst",
        )


def test_destructive_planning_tools_reject_invalid_token_before_db_access():
    with pytest.raises(PermissionError):
        regenerate_planning_period_roster_tool(token="wrong-token", planning_period_id=1)
    with pytest.raises(PermissionError):
        sync_planning_period_roster_tool(token="wrong-token", planning_period_id=1)
    with pytest.raises(PermissionError):
        delete_planning_period_tool(token="wrong-token", planning_period_id=1)
    with pytest.raises(PermissionError):
        delete_shift_template_tool(token="wrong-token", shift_template_id=1)
    with pytest.raises(PermissionError):
        delete_shift_variant_tool(token="wrong-token", shift_variant_id=1)
    with pytest.raises(PermissionError):
        delete_team_member_tool(token="wrong-token", team_member_id=1)
