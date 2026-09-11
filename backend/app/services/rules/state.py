from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import TypeVar

from app.models import (
    PlanningCell,
    PlanningDayStatusDefinition,
    PlanningShiftIntent,
    RosterSlot,
    RosterSlotAssignment,
    TeamMember,
    TeamMemberPlanningPattern,
    TeamMemberPropertyDefinition,
)

K = TypeVar("K")
V = TypeVar("V")


def frozen_mapping(data: dict[K, V]) -> Mapping[K, V]:
    return MappingProxyType(data)


@dataclass(frozen=True)
class DutyDayCounts:
    total: int
    weekend_holiday: int
    night: int
    by_category: Mapping[str, int]
    weekend_holiday_by_category: Mapping[str, int]
    night_by_category: Mapping[str, int]


EMPTY_DUTY_COUNTS = DutyDayCounts(
    total=0,
    weekend_holiday=0,
    night=0,
    by_category=frozen_mapping({}),
    weekend_holiday_by_category=frozen_mapping({}),
    night_by_category=frozen_mapping({}),
)


@dataclass(frozen=True)
class PlanState:
    organization_id: int
    start_date: date
    end_date: date
    load_start: date
    load_end: date
    shift_group_id: int | None
    members_by_id: Mapping[int, TeamMember]
    slots_by_id: Mapping[int, RosterSlot]
    slots_by_date: Mapping[date, tuple[RosterSlot, ...]]
    assignments_by_id: Mapping[int, RosterSlotAssignment]
    assignments_by_slot_id: Mapping[int, RosterSlotAssignment]
    assignments_by_member_id: Mapping[int, tuple[RosterSlotAssignment, ...]]
    cells_by_member_date_group: Mapping[tuple[int, date, int], PlanningCell]
    day_status_by_code: Mapping[str, PlanningDayStatusDefinition]
    patterns_by_member_id: Mapping[int, tuple[TeamMemberPlanningPattern, ...]]
    property_values_by_member_id: Mapping[int, Mapping[int, object]]
    property_definitions_by_id: Mapping[int, TeamMemberPropertyDefinition]
    shift_intents: tuple[PlanningShiftIntent, ...]
    time_entries_by_member_id: Mapping[int, tuple[object, ...]]
    employment_periods_by_member_id: Mapping[int, tuple[object, ...]]
    statutory_minutes_by_member_date: Mapping[tuple[int, date], int]
    duty_counts_by_member_date: Mapping[tuple[int, date], DutyDayCounts]
    period_roster_member_ids: Mapping[tuple[int, int, int], frozenset[int]]
    work_time_consents_by_member_id: Mapping[int, tuple[object, ...]]


def empty_indexed_state(
    *,
    organization_id: int,
    start_date: date,
    end_date: date,
    load_start: date,
    load_end: date,
    shift_group_id: int | None,
) -> PlanState:
    empty: Mapping[int, TeamMember] = frozen_mapping({})
    return PlanState(
        organization_id=organization_id,
        start_date=start_date,
        end_date=end_date,
        load_start=load_start,
        load_end=load_end,
        shift_group_id=shift_group_id,
        members_by_id=empty,
        slots_by_id=frozen_mapping({}),
        slots_by_date=frozen_mapping({}),
        assignments_by_id=frozen_mapping({}),
        assignments_by_slot_id=frozen_mapping({}),
        assignments_by_member_id=frozen_mapping({}),
        cells_by_member_date_group=frozen_mapping({}),
        day_status_by_code=frozen_mapping({}),
        patterns_by_member_id=frozen_mapping({}),
        property_values_by_member_id=frozen_mapping({}),
        property_definitions_by_id=frozen_mapping({}),
        shift_intents=(),
        time_entries_by_member_id=frozen_mapping({}),
        employment_periods_by_member_id=frozen_mapping({}),
        statutory_minutes_by_member_date=frozen_mapping({}),
        duty_counts_by_member_date=frozen_mapping({}),
        period_roster_member_ids=frozen_mapping({}),
        work_time_consents_by_member_id=frozen_mapping({}),
    )


def index_slots_by_date(slots: Sequence[RosterSlot]) -> Mapping[date, tuple[RosterSlot, ...]]:
    grouped: dict[date, list[RosterSlot]] = {}
    for slot in slots:
        grouped.setdefault(slot.slot_date, []).append(slot)
    return frozen_mapping({day: tuple(rows) for day, rows in grouped.items()})


def index_assignments_by_member(
    assignments: Sequence[RosterSlotAssignment],
) -> Mapping[int, tuple[RosterSlotAssignment, ...]]:
    grouped: dict[int, list[RosterSlotAssignment]] = {}
    for row in assignments:
        grouped.setdefault(row.team_member_id, []).append(row)
    return frozen_mapping({member_id: tuple(rows) for member_id, rows in grouped.items()})
