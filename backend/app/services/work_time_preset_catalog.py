from decimal import Decimal

from pydantic import TypeAdapter

from app.schemas import WorkTimePresetContractGroup, WorkTimeRule

PRESET_CODE_ARBZG = "arbzg_grundmodell"
PRESET_CODE_TDL = "tv_aerzte_tdl"
PRESET_CODE_VKA = "tv_aerzte_vka"

_RULES = TypeAdapter(list[WorkTimeRule])
_GROUPS = TypeAdapter(list[WorkTimePresetContractGroup])


def _rules(items: list[dict]) -> list[dict]:
    return _RULES.dump_python(_RULES.validate_python(items), mode="json")


def _groups(items: list[dict]) -> list[dict]:
    return _GROUPS.dump_python(_GROUPS.validate_python(items), mode="json")


def _tv_aerzte_category_rules(*, credit_factor: str) -> list[dict]:
    return [
        {
            "category": "bereitschaftsdienst",
            "counts_toward_contract": True,
            "credit_mode": "factor",
            "credit_factor": credit_factor,
            "holiday_credit_bonus": "25",
            "statutory_factor": "1",
            "call_outs_count_as_work": False,
        },
        {
            "category": "rufdienst",
            "counts_toward_contract": False,
            "credit_mode": "none",
            "holiday_credit_bonus": "0",
            "statutory_factor": "1",
            "call_outs_count_as_work": True,
        },
        {
            "category": "spaetdienst",
            "counts_toward_contract": True,
            "credit_mode": "duration",
            "holiday_credit_bonus": "0",
            "statutory_factor": "1",
            "call_outs_count_as_work": False,
        },
        {
            "category": "other",
            "counts_toward_contract": True,
            "credit_mode": "duration",
            "holiday_credit_bonus": "0",
            "statutory_factor": "1",
            "call_outs_count_as_work": False,
        },
    ]


def _tv_aerzte_groups(*, prefix: str) -> list[dict]:
    return _groups(
        [
            {
                "name": f"{prefix} Stufe I",
                "weekly_hours_at_100": Decimal("42"),
                "vacation_days_at_100": Decimal("30"),
                "category_rules": _tv_aerzte_category_rules(credit_factor="0.60"),
            },
            {
                "name": f"{prefix} Stufe II",
                "weekly_hours_at_100": Decimal("42"),
                "vacation_days_at_100": Decimal("30"),
                "category_rules": _tv_aerzte_category_rules(credit_factor="0.95"),
            },
        ]
    )


def _tv_aerzte_rules(*, tariff: str, confirmed: bool) -> list[dict]:
    suffix = "" if confirmed else " — Werte vor Verwendung bestätigen"
    return _rules(
        [
            {
                "type": "max_daily_working_time",
                "severity": "error",
                "source_note": f"§ 7 TV-Ärzte ({tariff}){suffix}",
                "base_hours": "8",
                "extended_hours": "24",
                "extension_requires_duty_hours": "8",
            },
            {
                "type": "opt_out_weekly_cap",
                "severity": "warning",
                "source_note": f"§ 7 Abs. 5 TV-Ärzte ({tariff}){suffix}",
                "hours_by_tier": {
                    "stufe_i": "58",
                    "stufe_ii": "54",
                    "regional_agreement": "66",
                },
                "reference_period_months": 12,
            },
            {
                "type": "max_duties_per_period",
                "severity": "warning",
                "source_note": f"§ 10 TV-Ärzte ({tariff}){suffix}",
                "count": 4,
                "period": "month",
                "additional_allowance_per_quarter": 1,
            },
        ]
    )


def work_time_preset_catalog() -> list[dict]:
    return [
        {
            "code": PRESET_CODE_ARBZG,
            "name": "ArbZG-Grundmodell",
            "values_confirmed": True,
            "rules": _rules(
                [
                    {
                        "type": "max_daily_working_time",
                        "severity": "error",
                        "source_note": "§ 3 ArbZG",
                        "base_hours": "8",
                        "extended_hours": "10",
                        "extension_requires_duty_hours": "0",
                    },
                    {
                        "type": "min_rest_period",
                        "severity": "error",
                        "source_note": "§ 5 Abs. 1 und Abs. 2 ArbZG",
                        "hours": "11",
                        "reducible_to_hours": "10",
                        "compensation_window_days": 31,
                        "call_out_handling": "interrupt",
                    },
                    {
                        "type": "rest_after_long_duty",
                        "severity": "error",
                        "source_note": "§ 5 Abs. 1 ArbZG",
                        "trigger_hours": "12",
                        "mandatory_rest_hours": "11",
                    },
                    {
                        "type": "weekly_average_cap",
                        "severity": "warning",
                        "source_note": "§ 3 ArbZG",
                        "hours": "48",
                        "reference_period_months": 6,
                        "rolling": True,
                    },
                    {
                        "type": "documentation_requirement",
                        "severity": "info",
                        "source_note": "§ 16 Abs. 2 ArbZG",
                        "threshold_hours": "8",
                        "retention_months": 24,
                    },
                ]
            ),
            "contract_groups": [],
        },
        {
            "code": PRESET_CODE_TDL,
            "name": "TV-Ärzte (TdL)",
            "values_confirmed": True,
            "rules": _tv_aerzte_rules(tariff="TdL", confirmed=True),
            "contract_groups": _tv_aerzte_groups(prefix="TV-Ärzte (TdL)"),
        },
        {
            "code": PRESET_CODE_VKA,
            "name": "TV-Ärzte (VKA)",
            "values_confirmed": False,
            "rules": _tv_aerzte_rules(tariff="VKA", confirmed=False),
            "contract_groups": _tv_aerzte_groups(prefix="TV-Ärzte (VKA)"),
        },
    ]
