from datetime import date, datetime
from types import SimpleNamespace

from app.services.export_colors import member_pastel_palette
from app.services import exports


def test_member_pastel_palette_is_deterministic():
    first = member_pastel_palette(7)
    second = member_pastel_palette(7)
    other = member_pastel_palette(8)
    assert first == second
    assert first.fill_hex != other.fill_hex
    assert first.text_hex in {"#0f172a", "#f8fafc"}


def test_build_roster_export_table_contains_assignee(monkeypatch):
    matrix = SimpleNamespace(
        planning_period=SimpleNamespace(year=2026, month=11),
        days=[SimpleNamespace(date=date(2026, 11, 1), weekday="Sunday")],
        team_members=[SimpleNamespace(id=1, first_name="Lena", last_name="Balitzki")],
        slots=[
            SimpleNamespace(
                id=3,
                shift_template_id=10,
                shift_variant_id=20,
                position=1,
                label="Springer 1",
                template_code="SPR1",
                variant_label="Tag",
                starts_at=datetime(2026, 11, 1, 8, 0),
                ends_at=datetime(2026, 11, 1, 16, 0),
                slot_date=date(2026, 11, 1),
            )
        ],
        assignments=[SimpleNamespace(roster_slot_id=3, team_member_id=1)],
    )

    monkeypatch.setattr(exports, "get_roster_matrix", lambda *args, **kwargs: matrix)
    table = exports.build_roster_export_table(None, 99, organization_id=1)

    assert table.period_label == "2026-11"
    assert table.columns
    assert "SPR1" in table.columns[0].title
    assert table.rows[0].weekday == "So"
    assert table.rows[0].cells[0] is not None
    assert table.rows[0].cells[0].member_name == "Balitzki"


def test_build_roster_export_table_by_template_groups_variants(monkeypatch):
    matrix = SimpleNamespace(
        planning_period=SimpleNamespace(year=2026, month=11),
        days=[SimpleNamespace(date=date(2026, 11, 1), weekday="Sunday")],
        team_members=[
            SimpleNamespace(id=1, first_name="Lena", last_name="Balitzki"),
            SimpleNamespace(id=2, first_name="Moritz", last_name="Mertes"),
        ],
        shift_templates=[SimpleNamespace(id=10, code="SPR1", name="Springer 1")],
        slots=[
            SimpleNamespace(
                id=3,
                shift_template_id=10,
                shift_variant_id=20,
                position=1,
                label="Springer 1",
                template_code="SPR1",
                variant_label="Tag",
                starts_at=datetime(2026, 11, 1, 8, 0),
                ends_at=datetime(2026, 11, 1, 16, 0),
                slot_date=date(2026, 11, 1),
            ),
            SimpleNamespace(
                id=4,
                shift_template_id=10,
                shift_variant_id=21,
                position=2,
                label="Springer 1",
                template_code="SPR1",
                variant_label="Nacht",
                starts_at=datetime(2026, 11, 1, 16, 0),
                ends_at=datetime(2026, 11, 1, 23, 0),
                slot_date=date(2026, 11, 1),
            ),
        ],
        assignments=[
            SimpleNamespace(roster_slot_id=3, team_member_id=1),
            SimpleNamespace(roster_slot_id=4, team_member_id=2),
        ],
    )

    monkeypatch.setattr(exports, "get_roster_matrix", lambda *args, **kwargs: matrix)
    table = exports.build_roster_export_table_by_template(None, 99, organization_id=1)

    assert len(table.columns) == 1
    assert "SPR1" in table.columns[0].title
    assert table.rows[0].cells[0] is not None
    assert "Balitzki" in table.rows[0].cells[0].member_name
    assert "Mertes" in table.rows[0].cells[0].member_name
