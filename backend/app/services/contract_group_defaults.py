from datetime import date

OPEN_ENDED_EMPLOYMENT_START = date(2000, 1, 1)
DEFAULT_CONTRACT_GROUP_NAME = "Standard"
DEFAULT_WEEKLY_HOURS_AT_100 = "40.00"
DEFAULT_VACATION_DAYS_AT_100 = "30.00"


def default_regular_week_pattern() -> list[dict]:
    return [
        {"weekday": day, "start": "08:00:00", "end": "16:30:00"}
        for day in ("mon", "tue", "wed", "thu", "fri")
    ]


def default_category_rules() -> list[dict]:
    return [
        {
            "category": "bereitschaftsdienst",
            "counts_toward_contract": True,
            "credit_mode": "factor",
            "credit_factor": "0.6",
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


def default_status_mappings() -> list[dict]:
    return [
        {"code": "urlaub", "absence_kind": "vacation", "consumes_vacation": True, "counts_as_work_day": False},
        {"code": "forschung", "absence_kind": "other", "consumes_vacation": False, "counts_as_work_day": True},
        {"code": "lehre", "absence_kind": "other", "consumes_vacation": False, "counts_as_work_day": True},
        {"code": "frei", "absence_kind": "none", "consumes_vacation": False, "counts_as_work_day": False},
    ]
