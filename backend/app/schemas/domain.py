from datetime import date as date_type
from datetime import datetime, time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

PlanningCellStatus = Literal[
    "dienstwunsch",
    "urlaub",
    "kein_dienst",
    "forschung",
    "lehre",
    "frei",
    "tagdienst",
    "nachtdienst",
    "spaetdienst",
    "rufdienst",
]

PLANNED_DUTY_STATUSES = {"tagdienst", "nachtdienst", "spaetdienst", "rufdienst"}
UNAVAILABLE_STATUSES = {"urlaub", "kein_dienst", "forschung", "lehre", "frei"}


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: str
    locale: str


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class DoctorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    employment_percentage: int = Field(default=100, ge=1, le=100)
    notes: str | None = None


class DoctorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    employment_percentage: int | None = Field(default=None, ge=1, le=100)
    notes: str | None = None
    is_active: bool | None = None


class DoctorRead(DoctorCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    created_at: datetime


class ShiftTypeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name_de: str
    name_en: str
    starts_at: time
    ends_at: time
    category: Literal["day", "night", "on_call", "other"] = "day"


class ShiftTypeUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name_de: str | None = None
    name_en: str | None = None
    starts_at: time | None = None
    ends_at: time | None = None
    category: Literal["day", "night", "on_call", "other"] | None = None
    is_active: bool | None = None


class ShiftTypeRead(ShiftTypeCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool


class PlanningPeriodCreate(BaseModel):
    year: int = Field(ge=2020, le=2100)
    month: int = Field(ge=1, le=12)


class PlanningPeriodRead(PlanningPeriodCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    created_at: datetime


class AvailabilityRequestCreate(BaseModel):
    doctor_id: int
    planning_period_id: int
    request_date: date_type
    request_type: Literal["wish", "no_go", "preference"]
    note: str | None = None


class AvailabilityRequestRead(AvailabilityRequestCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class RosterAssignmentCreate(BaseModel):
    doctor_id: int
    planning_period_id: int
    shift_type_id: int
    assignment_date: date_type
    note: str | None = None
    manual_override: bool = False


class RosterAssignmentRead(RosterAssignmentCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class RosterSlotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    planning_period_id: int
    shift_type_id: int
    slot_date: date_type
    position: int
    label: str | None = None
    source: str
    created_at: datetime
    updated_at: datetime


class RosterSlotAssignmentUpsert(BaseModel):
    roster_slot_id: int
    doctor_id: int
    comment: str | None = None
    manual_override: bool = False


class RosterSlotAssignmentClear(BaseModel):
    roster_slot_id: int


class RosterSlotAssignmentRead(RosterSlotAssignmentUpsert):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    created_at: datetime
    updated_at: datetime


class PlanningCellBase(BaseModel):
    doctor_id: int
    cell_date: date_type
    status: PlanningCellStatus
    comment: str | None = None
    source: str = "manual"


class PlanningCellUpsert(BaseModel):
    doctor_id: int
    cell_date: date_type
    status: PlanningCellStatus
    comment: str | None = None


class PlanningCellBulkUpsert(BaseModel):
    cells: list[PlanningCellUpsert]


class PlanningCellClear(BaseModel):
    doctor_id: int
    cell_date: date_type


class PlanningCellRead(PlanningCellBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    planning_period_id: int
    created_at: datetime
    updated_at: datetime


class MatrixDoctor(BaseModel):
    id: int
    name: str
    email: EmailStr
    employment_percentage: int


class MatrixDay(BaseModel):
    date: date_type
    weekday: str


class PlanningMatrixRead(BaseModel):
    planning_period: PlanningPeriodRead
    doctors: list[MatrixDoctor]
    days: list[MatrixDay]
    cells: list[PlanningCellRead]


class RosterMatrixRead(BaseModel):
    planning_period: PlanningPeriodRead
    doctors: list[MatrixDoctor]
    days: list[MatrixDay]
    shift_types: list[ShiftTypeRead]
    slots: list[RosterSlotRead]
    assignments: list[RosterSlotAssignmentRead]
    planning_cells: list[PlanningCellRead]


class DoctorPeriodNoteUpsert(BaseModel):
    doctor_id: int
    source_text: str | None = None
    summary: str | None = None


class DoctorPeriodNoteRead(DoctorPeriodNoteUpsert):
    model_config = ConfigDict(from_attributes=True)

    id: int
    planning_period_id: int
    created_at: datetime
    updated_at: datetime


class RuleConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    max_consecutive_work_days: int
    min_rest_hours: int
    max_monthly_nights_full_time: int


class ValidationWarning(BaseModel):
    code: str
    severity: Literal["info", "warning", "error"] = "warning"
    message: str
    doctor_id: int | None = None
    assignment_id: int | None = None
    request_id: int | None = None
    date: date_type | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor: str
    source: str
    action: str
    entity_type: str
    entity_id: str | None
    details: dict[str, Any]
    created_at: datetime
