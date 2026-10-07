from datetime import UTC, date, datetime
from types import SimpleNamespace

from app.services.rules.builtin import TemplateNoGoConflictRule
from app.services.shift_intent_bands import slot_band
from app.services.solver.objective import wished_slot_members
from app.tests.test_member_api import _login, _member_ids, client  # noqa: F401

SATURDAY = "2026-10-10"
MONDAY = "2026-10-12"


def _variant(test_client, template_id: int, **fields) -> None:
    body = {"end_day_offset": 0, "required_count": 1, **fields}
    response = test_client.post(f"/api/v1/shift-templates/{template_id}/variants", json=body)
    assert response.status_code in (200, 201), response.text


def _setup(test_client, SessionLocal) -> dict:
    """A Bereitschaftsdienst that is night-only on weekdays and day + night on weekends, plus a
    weekday-only late shift."""
    ada_id, bob_id = _member_ids(SessionLocal)
    _login(test_client, "admin@example.com", "secret")
    bd = test_client.post(
        "/api/v1/shift-templates",
        json={"code": "BD", "name": "Bereitschaftsdienst", "category": "bereitschaftsdienst"},
    ).json()
    _variant(test_client, bd["id"], label="Woche Nacht", start_day_class="weekday", starts_at="16:00:00", ends_at="08:00:00", end_day_offset=1)
    _variant(test_client, bd["id"], label="WE Tag", start_day_class="weekend", starts_at="08:00:00", ends_at="20:00:00")
    _variant(test_client, bd["id"], label="WE Nacht", start_day_class="weekend", starts_at="20:00:00", ends_at="08:00:00", end_day_offset=1)
    late = test_client.post(
        "/api/v1/shift-templates",
        json={"code": "SP", "name": "Spaetdienst", "category": "spaetdienst"},
    ).json()
    _variant(test_client, late["id"], label="Spaet", start_day_class="weekday", starts_at="12:00:00", ends_at="20:00:00")
    test_client.put("/api/v1/shift-groups/1/shift-templates", json={"shift_template_ids": [bd["id"], late["id"]]})
    test_client.put(
        "/api/v1/shift-groups/1/memberships",
        json={
            "memberships": [
                {"team_member_id": ada_id, "start_date": "2026-01-01", "end_date": None},
                {"team_member_id": bob_id, "start_date": "2026-01-01", "end_date": None},
            ]
        },
    )
    period_id = test_client.post("/api/v1/planning-periods", json={"year": 2026, "month": 10}).json()["id"]
    return {"period_id": period_id, "ada": ada_id, "bob": bob_id, "bd": bd["id"], "late": late["id"]}


def _put(test_client, ctx: dict, *, template: str, day: str, kind: str | None, band: str = "all", member: str = "ada"):
    return test_client.put(
        f"/api/v1/matrix/{ctx['period_id']}/shift-intents/bulk",
        json={
            "intents": [
                {
                    "team_member_id": ctx[member],
                    "cell_date": day,
                    "shift_group_id": 1,
                    "shift_template_id": ctx[template],
                    "band": band,
                    "kind": kind,
                }
            ]
        },
    )


def _intents(test_client, ctx: dict, day: str, template: str = "bd") -> dict[str, str]:
    matrix = test_client.get(f"/api/v1/matrix/{ctx['period_id']}?shift_group_id=1").json()
    return {
        row["band"]: row["kind"]
        for row in matrix["shift_intents"]
        if row["cell_date"] == day and row["shift_template_id"] == ctx[template] and row["team_member_id"] == ctx["ada"]
    }


def test_template_slot_days_report_day_and_night(client):  # noqa: F811
    test_client, SessionLocal, _engine = client
    ctx = _setup(test_client, SessionLocal)
    matrix = test_client.get(f"/api/v1/matrix/{ctx['period_id']}?shift_group_id=1").json()
    rows = {(row["cell_date"], row["shift_template_id"]): row for row in matrix["template_slot_days"]}
    assert rows[(SATURDAY, ctx["bd"])]["has_day"] is True
    assert rows[(SATURDAY, ctx["bd"])]["has_night"] is True
    assert rows[(MONDAY, ctx["bd"])]["has_day"] is False
    assert rows[(MONDAY, ctx["bd"])]["has_night"] is True
    assert rows[(MONDAY, ctx["late"])]["has_day"] is True
    assert (SATURDAY, ctx["late"]) not in rows


def test_intent_for_a_shift_that_does_not_run_that_day_is_rejected(client):  # noqa: F811
    test_client, SessionLocal, _engine = client
    ctx = _setup(test_client, SessionLocal)
    rejected = _put(test_client, ctx, template="late", day=SATURDAY, kind="no_go")
    assert rejected.status_code == 400
    assert "no shift on this date" in rejected.json()["detail"]
    assert _put(test_client, ctx, template="late", day=MONDAY, kind="no_go").status_code == 200
    assert _put(test_client, ctx, template="late", day=SATURDAY, kind=None).status_code == 200


def test_member_path_rejects_a_shift_that_does_not_run_that_day(client):  # noqa: F811
    test_client, SessionLocal, _engine = client
    ctx = _setup(test_client, SessionLocal)
    _login(test_client, "ada@example.com", "ada-secret")
    body = {
        "intents": [
            {
                "team_member_id": ctx["ada"],
                "cell_date": SATURDAY,
                "shift_group_id": 1,
                "shift_template_id": ctx["late"],
                "kind": "wish",
            }
        ]
    }
    rejected = test_client.put(f"/api/v1/me/wishes/{ctx['period_id']}/intents?shift_group_id=1", json=body)
    assert rejected.status_code == 400
    body["intents"][0]["shift_template_id"] = ctx["bd"]
    body["intents"][0]["band"] = "night"
    saved = test_client.put(f"/api/v1/me/wishes/{ctx['period_id']}/intents?shift_group_id=1", json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()[0]["band"] == "night"


def test_day_or_night_band_needs_both_bands_that_day(client):  # noqa: F811
    test_client, SessionLocal, _engine = client
    ctx = _setup(test_client, SessionLocal)
    assert _put(test_client, ctx, template="bd", day=MONDAY, kind="wish", band="night").status_code == 400
    assert _put(test_client, ctx, template="bd", day=MONDAY, kind="wish", band="day").status_code == 400
    assert _put(test_client, ctx, template="bd", day=MONDAY, kind="wish").status_code == 200
    saved = _put(test_client, ctx, template="bd", day=SATURDAY, kind="no_go", band="night")
    assert saved.status_code == 200
    assert saved.json()[0]["band"] == "night"
    assert _intents(test_client, ctx, SATURDAY) == {"night": "no_go"}


def test_all_and_band_rows_never_coexist(client):  # noqa: F811
    test_client, SessionLocal, _engine = client
    ctx = _setup(test_client, SessionLocal)
    assert _put(test_client, ctx, template="bd", day=SATURDAY, kind="no_go").status_code == 200
    assert _intents(test_client, ctx, SATURDAY) == {"all": "no_go"}
    assert _put(test_client, ctx, template="bd", day=SATURDAY, kind="wish", band="night").status_code == 200
    assert _intents(test_client, ctx, SATURDAY) == {"day": "no_go", "night": "wish"}
    assert _put(test_client, ctx, template="bd", day=SATURDAY, kind=None, band="night").status_code == 200
    assert _intents(test_client, ctx, SATURDAY) == {"day": "no_go"}
    assert _put(test_client, ctx, template="bd", day=SATURDAY, kind="wish").status_code == 200
    assert _intents(test_client, ctx, SATURDAY) == {"all": "wish"}
    assert _put(test_client, ctx, template="bd", day=SATURDAY, kind=None, band="day").status_code == 200
    assert _intents(test_client, ctx, SATURDAY) == {"night": "wish"}


def test_night_no_go_blocks_only_the_night_slot(client):  # noqa: F811
    test_client, SessionLocal, _engine = client
    ctx = _setup(test_client, SessionLocal)
    roster = test_client.get(f"/api/v1/roster-matrix/{ctx['period_id']}?shift_group_id=1").json()
    saturday = sorted(
        (row for row in roster["slots"] if row["slot_date"] == SATURDAY and row["shift_template_id"] == ctx["bd"]),
        key=lambda row: row["starts_at"],
    )
    day_slot, night_slot = saturday
    assigned = test_client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": night_slot["id"], "team_member_id": ctx["ada"]},
    )
    assert assigned.status_code == 200, assigned.text
    assert _put(test_client, ctx, template="bd", day=SATURDAY, kind="no_go", band="night").status_code == 200

    warnings = test_client.get(f"/api/v1/validation/{ctx['period_id']}").json()
    conflicts = [row for row in warnings if row["code"] == "ROSTER_TEMPLATE_NO_GO_CONFLICT"]
    assert [row["details"]["roster_slot_id"] for row in conflicts] == [night_slot["id"]]

    cleared = test_client.post("/api/v1/roster-matrix/assignments/clear", json={"roster_slot_id": night_slot["id"]})
    assert cleared.status_code == 200, cleared.text
    blocked = test_client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": night_slot["id"], "team_member_id": ctx["ada"]},
    )
    assert blocked.status_code == 400
    allowed = test_client.put(
        "/api/v1/roster-matrix/assignments",
        json={"roster_slot_id": day_slot["id"], "team_member_id": ctx["ada"]},
    )
    assert allowed.status_code == 200, allowed.text
    warnings = test_client.get(f"/api/v1/validation/{ctx['period_id']}").json()
    assert [row for row in warnings if row["code"] == "ROSTER_TEMPLATE_NO_GO_CONFLICT"] == []


def test_plan_version_snapshot_keeps_band(client):  # noqa: F811
    test_client, SessionLocal, _engine = client
    ctx = _setup(test_client, SessionLocal)
    assert _put(test_client, ctx, template="bd", day=SATURDAY, kind="wish", band="night").status_code == 200
    moved = test_client.post(f"/api/v1/planning-periods/{ctx['period_id']}/preliminary?shift_group_id=1", json={})
    assert moved.status_code == 200, moved.text
    versions = test_client.get(f"/api/v1/planning-periods/{ctx['period_id']}/versions?shift_group_id=1").json()
    version_id = versions["versions"][0]["id"]
    snapshot = test_client.get(f"/api/v1/planning-periods/{ctx['period_id']}/versions/{version_id}/matrix").json()
    assert [(row["cell_date"], row["band"], row["kind"]) for row in snapshot["shift_intents"]] == [
        (SATURDAY, "night", "wish")
    ]


def _slot(slot_id: int, start: datetime, end: datetime, template_id: int = 7) -> SimpleNamespace:
    return SimpleNamespace(
        id=slot_id,
        slot_date=start.date(),
        shift_template_id=template_id,
        starts_at=start,
        ends_at=end,
    )


def _intent(kind: str, band: str, template_id: int = 7) -> SimpleNamespace:
    return SimpleNamespace(
        team_member_id=1,
        cell_date=date(2026, 10, 10),
        shift_template_id=template_id,
        band=band,
        kind=kind,
    )


DAY_SLOT = _slot(1, datetime(2026, 10, 10, 6, tzinfo=UTC), datetime(2026, 10, 10, 18, tzinfo=UTC))
NIGHT_SLOT = _slot(2, datetime(2026, 10, 10, 18, tzinfo=UTC), datetime(2026, 10, 11, 6, tzinfo=UTC))


def test_slot_band_follows_the_roster_day_night_split():
    assert slot_band(DAY_SLOT.starts_at, DAY_SLOT.ends_at, "Europe/Berlin") == "day"
    assert slot_band(NIGHT_SLOT.starts_at, NIGHT_SLOT.ends_at, "Europe/Berlin") == "night"
    late = datetime(2026, 10, 12, 12, tzinfo=UTC)
    assert slot_band(late, datetime(2026, 10, 12, 18, tzinfo=UTC), "Europe/Berlin") == "night"
    assert slot_band(None, None) == "day"


def test_cpsat_mask_excludes_only_the_night_slot_for_a_night_no_go():
    excluded: list[tuple[int, int]] = []
    model = SimpleNamespace(
        phase="mask",
        target_slots=[DAY_SLOT, NIGHT_SLOT],
        iter_candidates=lambda slot_id: [1],
        exclude=lambda slot_id, member_id, code: excluded.append((slot_id, member_id)),
    )
    state = SimpleNamespace(shift_intents=(_intent("no_go", "night"),), timezone="Europe/Berlin")
    TemplateNoGoConflictRule().to_cpsat(model, None, state)
    assert excluded == [(NIGHT_SLOT.id, 1)]

    excluded.clear()
    state = SimpleNamespace(shift_intents=(_intent("no_go", "all"),), timezone="Europe/Berlin")
    TemplateNoGoConflictRule().to_cpsat(model, None, state)
    assert excluded == [(DAY_SLOT.id, 1), (NIGHT_SLOT.id, 1)]


def test_solver_wish_term_honours_the_band():
    state = SimpleNamespace(shift_intents=(_intent("wish", "night"),), timezone="Europe/Berlin")
    assert wished_slot_members(state, [DAY_SLOT, NIGHT_SLOT], lambda slot_id: [1]) == [(NIGHT_SLOT.id, 1)]
    state = SimpleNamespace(shift_intents=(_intent("wish", "day"),), timezone="Europe/Berlin")
    assert wished_slot_members(state, [DAY_SLOT, NIGHT_SLOT], lambda slot_id: [1]) == [(DAY_SLOT.id, 1)]
    state = SimpleNamespace(shift_intents=(_intent("wish", "all"),), timezone="Europe/Berlin")
    assert wished_slot_members(state, [DAY_SLOT, NIGHT_SLOT], lambda slot_id: [1, 2]) == [
        (DAY_SLOT.id, 1),
        (NIGHT_SLOT.id, 1),
    ]
