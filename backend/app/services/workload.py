from dataclasses import dataclass
from datetime import date

from app.schemas import ValidationWarning
from app.services.holidays import classify_day


@dataclass
class WorkloadSlotSlice:
    id: int
    shift_template_id: int | None
    category: str | None
    slot_date: date
    starts_at: object | None
    ends_at: object | None


@dataclass
class WorkloadAssignmentSlice:
    roster_slot_id: int
    team_member_id: int


@dataclass
class WorkloadMemberSlice:
    id: int
    first_name: str
    last_name: str
    nickname: str | None
    employment_percentage: int


@dataclass
class MemberWorkloadRow:
    team_member_id: int
    name: str
    employment_percentage: int
    total: int
    on_call_duty: int
    standby_duty: int
    late_duty: int
    other: int
    weekend_holiday_shifts: int
    conflicts: int


def slot_touches_weekend_or_nrw_holiday(slot_date: date) -> bool:
    return classify_day(slot_date) in ("weekend", "holiday")


def member_display_name(*, first_name: str, last_name: str, nickname: str | None) -> str:
    nick = (nickname or "").strip()
    return nick if nick else last_name.strip()


def roster_warning_counts_by_member(warnings: list[ValidationWarning]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for warning in warnings:
        roster_related = (
            warning.code.startswith("ROSTER_MATRIX")
            or warning.code == "ROSTER_TEMPLATE_NO_GO_CONFLICT"
            or warning.code.startswith("ROSTER_CONSTRAINT")
            or warning.code.startswith("MEMBER_PATTERN")
            or warning.code == "ROSTER_CONSECUTIVE_WEEKENDS"
        )
        if not roster_related or warning.team_member_id is None:
            continue
        if warning.severity == "info":
            continue
        member_id = warning.team_member_id
        counts[member_id] = counts.get(member_id, 0) + 1
    return counts


def build_member_workload_rows(
    *,
    slots: list[WorkloadSlotSlice],
    assignments: list[WorkloadAssignmentSlice],
    members: list[WorkloadMemberSlice],
    warnings: list[ValidationWarning],
) -> tuple[list[MemberWorkloadRow], int]:
    slot_by_id = {slot.id: slot for slot in slots}
    conflict_by_member = roster_warning_counts_by_member(warnings)
    rows: dict[int, MemberWorkloadRow] = {
        member.id: MemberWorkloadRow(
            team_member_id=member.id,
            name=member_display_name(
                first_name=member.first_name, last_name=member.last_name, nickname=member.nickname
            ),
            employment_percentage=member.employment_percentage,
            total=0,
            on_call_duty=0,
            standby_duty=0,
            late_duty=0,
            other=0,
            weekend_holiday_shifts=0,
            conflicts=conflict_by_member.get(member.id, 0),
        )
        for member in members
    }
    for assignment in assignments:
        row = rows.get(assignment.team_member_id)
        slot = slot_by_id.get(assignment.roster_slot_id)
        if row is None or slot is None or slot.category is None:
            continue
        row.total += 1
        if slot_touches_weekend_or_nrw_holiday(slot.slot_date):
            row.weekend_holiday_shifts += 1
        category = slot.category
        if category == "bereitschaftsdienst":
            row.on_call_duty += 1
        elif category == "rufdienst":
            row.standby_duty += 1
        elif category == "spaetdienst":
            row.late_duty += 1
        else:
            row.other += 1
    unassigned = max(0, len(slots) - len(assignments))
    return sorted(rows.values(), key=lambda row: (-row.total, row.name)), unassigned


def validation_counts_by_code(warnings: list[ValidationWarning], *, limit: int = 5) -> list[tuple[str, str, int]]:
    tallies: dict[tuple[str, str], int] = {}
    for warning in warnings:
        if warning.severity not in ("warning", "error"):
            continue
        key = (warning.code, warning.severity)
        tallies[key] = tallies.get(key, 0) + 1
    ordered = sorted(tallies.items(), key=lambda item: -item[1])
    return [(code, severity, count) for (code, severity), count in ordered[:limit]]
