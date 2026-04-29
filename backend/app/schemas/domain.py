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


DayClass = Literal["any", "weekday", "weekend", "holiday"]
ShiftTemplateCategory = Literal["bereitschaftsdienst", "rufdienst", "spaetdienst", "other"]


class ShiftVariantCreate(BaseModel):
    label: str = Field(min_length=1, max_length=255)
    start_day_class: DayClass = "any"
    end_day_class: DayClass | None = None
    starts_at: time
    ends_at: time
    end_day_offset: int = Field(default=0, ge=0, le=1)
    required_count: int = Field(default=1, ge=1, le=20)


class ShiftVariantUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=255)
    start_day_class: DayClass | None = None
    end_day_class: DayClass | None = None
    starts_at: time | None = None
    ends_at: time | None = None
    end_day_offset: int | None = Field(default=None, ge=0, le=1)
    required_count: int | None = Field(default=None, ge=1, le=20)
    is_active: bool | None = None


class ShiftVariantRead(ShiftVariantCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shift_template_id: int
    is_active: bool
    created_at: datetime


class ShiftTemplateCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name_de: str
    name_en: str
    category: ShiftTemplateCategory = "bereitschaftsdienst"
    display_order: int = 0


class ShiftTemplateUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name_de: str | None = None
    name_en: str | None = None
    category: ShiftTemplateCategory | None = None
    display_order: int | None = None
    is_active: bool | None = None


class ShiftTemplateRead(ShiftTemplateCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    created_at: datetime
    variants: list[ShiftVariantRead] = Field(default_factory=list)


class GeneratedRosterSlotPreview(BaseModel):
    slot_date: date_type
    label: str
    starts_at: datetime
    ends_at: datetime
    day_class: str
    template_id: int
    template_code: str
    template_name_de: str
    template_name_en: str
    variant_id: int
    variant_label: str
    category: str
    position: int


class ShiftTemplatePreviewRequest(BaseModel):
    year: int = Field(ge=2020, le=2100)
    month: int = Field(ge=1, le=12)


class PlanningPeriodCreate(BaseModel):
    year: int = Field(ge=2020, le=2100)
    month: int = Field(ge=1, le=12)


class PlanningPeriodRead(PlanningPeriodCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    created_at: datetime


class RosterSlotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    planning_period_id: int
    shift_template_id: int | None = None
    shift_variant_id: int | None = None
    slot_date: date_type
    position: int
    label: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    day_class: str | None = None
    template_code: str | None = None
    template_name_de: str | None = None
    template_name_en: str | None = None
    variant_label: str | None = None
    category: str | None = None
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
    shift_templates: list[ShiftTemplateRead] = Field(default_factory=list)
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
