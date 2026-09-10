from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app
from app.services.work_time_preset_catalog import PRESET_CODE_TDL
from app.services.work_time_presets import ensure_work_time_presets

pytest_plugins = ("app.tests.test_api",)


def login(client: TestClient) -> None:
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "secret", "organization_slug": "default"},
    ).status_code == 200


def seed_presets() -> None:
    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    try:
        ensure_work_time_presets(db)
        db.commit()
        ensure_work_time_presets(db)
        db.commit()
    finally:
        db.close()


def test_seeding_presets_is_idempotent(client: TestClient):
    login(client)
    seed_presets()
    listed = client.get("/api/v1/work-time-rule-sets/presets")
    assert listed.status_code == 200
    codes = [row["code"] for row in listed.json()]
    assert len(codes) == 3
    assert codes.count("arbzg_grundmodell") == 1
    assert codes.count("tv_aerzte_tdl") == 1
    assert codes.count("tv_aerzte_vka") == 1
    for row in listed.json():
        assert row["rules"]
        assert all(rule["source_note"] for rule in row["rules"])


def test_adopt_copies_tdl_numbers_and_does_not_mutate_preset(client: TestClient):
    login(client)
    seed_presets()
    adopted = client.post(f"/api/v1/work-time-rule-sets/presets/{PRESET_CODE_TDL}/adopt", json={})
    assert adopted.status_code == 201, adopted.text
    body = adopted.json()
    rule_set = body["rule_set"]
    preset_before = next(
        row for row in client.get("/api/v1/work-time-rule-sets/presets").json() if row["code"] == PRESET_CODE_TDL
    )
    opt_out = next(rule for rule in rule_set["rules"] if rule["type"] == "opt_out_weekly_cap")
    duties = next(rule for rule in rule_set["rules"] if rule["type"] == "max_duties_per_period")
    assert Decimal(str(opt_out["hours_by_tier"]["stufe_i"])) == Decimal("58")
    assert Decimal(str(opt_out["hours_by_tier"]["stufe_ii"])) == Decimal("54")
    assert Decimal(str(opt_out["hours_by_tier"]["regional_agreement"])) == Decimal("66")
    assert opt_out["reference_period_months"] == 12
    assert duties["count"] == 4
    assert duties["period"] == "month"
    assert duties["additional_allowance_per_quarter"] == 1
    groups = {group["name"]: group for group in body["contract_groups"]}
    assert Decimal(str(groups["TV-Ärzte (TdL) Stufe I"]["category_rules"][0]["credit_factor"])) == Decimal("0.60")
    assert Decimal(str(groups["TV-Ärzte (TdL) Stufe II"]["category_rules"][0]["credit_factor"])) == Decimal("0.95")
    for group in body["contract_groups"]:
        bd = next(rule for rule in group["category_rules"] if rule["category"] == "bereitschaftsdienst")
        assert Decimal(str(bd["holiday_credit_bonus"])) == Decimal("25")
        assert Decimal(str(bd["statutory_factor"])) == Decimal("1")
    assert all(rule["source_note"] for rule in rule_set["rules"])
    patched = client.patch(
        f"/api/v1/work-time-rule-sets/{rule_set['id']}",
        json={"name": "Org copy of TdL"},
    )
    assert patched.status_code == 200
    assert patched.json()["id"] == rule_set["id"]
    assert patched.json()["name"] == "Org copy of TdL"
    preset_after = next(
        row for row in client.get("/api/v1/work-time-rule-sets/presets").json() if row["code"] == PRESET_CODE_TDL
    )
    assert preset_after["id"] == preset_before["id"]
    assert preset_after["name"] == "TV-Ärzte (TdL)"
    assert preset_after["rules"] == preset_before["rules"]
    listed_org = client.get("/api/v1/work-time-rule-sets").json()
    assert any(row["id"] == rule_set["id"] and row["name"] == "Org copy of TdL" for row in listed_org)
    assert all(row["id"] != preset_before["id"] for row in listed_org)
