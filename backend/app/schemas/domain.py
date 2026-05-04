from datetime import date as date_type
from datetime import datetime, time
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

PlanningCellStatus = Literal["urlaub", "forschung", "lehre", "frei"]

PLANNED_DUTY_STATUSES: set[str] = set()
UNAVAILABLE_STATUSES = {"urlaub", "forschung", "lehre", "frei"}

PlanningShiftIntentKind = Literal["wish", "no_go"]


class UserShiftGroupBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name_de: str
    name_en: str
    is_active: bool = True


class UserCapabilities(BaseModel):
    admin: bool
    planning: bool
    team_member_portal: bool


class OrganizationBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    plan_tier: str


class MembershipSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    membership_id: int
    organization: OrganizationBrief
    role: str
    team_member_id: int | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: str
    locale: str
    organization_id: int
    organization: OrganizationBrief
    team_member_id: int | None = None
    shift_groups: list[UserShiftGroupBrief] = Field(default_factory=list)
    planner_shift_groups: list[UserShiftGroupBrief] = Field(default_factory=list)
    organization_shift_groups: list[UserShiftGroupBrief] = Field(default_factory=list)
    capabilities: UserCapabilities
    memberships: list[MembershipSummary] = Field(default_factory=list)


class ActiveOrganizationInput(BaseModel):
    organization_slug: str = Field(min_length=1, max_length=64)


class LoginInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    organization_slug: str = Field(default="", max_length=64)


class JoinRequestResubmitInput(BaseModel):
    first_name: str = Field(min_length=1, max_length=255)
    last_name: str = Field(min_length=1, max_length=255)
    message: str | None = Field(default=None, max_length=2000)


class AddOrganizationMembershipInput(BaseModel):
    organization_slug: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    first_name: str = Field(min_length=1, max_length=255)
    last_name: str = Field(min_length=1, max_length=255)
    message: str | None = Field(default=None, max_length=2000)


class DeleteAccountInput(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class OrganizationLookupResponse(BaseModel):
    slug: str
    name: str


class RegisterCreateOrganizationInput(BaseModel):
    organization_name: str = Field(min_length=1, max_length=255)
    organization_slug: str = Field(min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    password_confirm: str = Field(min_length=8, max_length=256)
    locale: str = Field(default="de", pattern=r"^(de|en)$")

    @model_validator(mode="after")
    def register_passwords_match(self) -> Self:
        if self.password != self.password_confirm:
            raise ValueError("passwords_do_not_match")
        return self


class RegisterJoinOrganizationInput(BaseModel):
    organization_slug: str = Field(min_length=1, max_length=64)
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    password_confirm: str = Field(min_length=8, max_length=256)
    first_name: str = Field(min_length=1, max_length=255)
    last_name: str = Field(min_length=1, max_length=255)
    message: str | None = Field(default=None, max_length=2000)
    locale: str = Field(default="de", pattern=r"^(de|en)$")

    @model_validator(mode="after")
    def register_passwords_match(self) -> Self:
        if self.password != self.password_confirm:
            raise ValueError("passwords_do_not_match")
        return self


class OrganizationUpdateInput(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    organization_slug: str | None = Field(default=None, min_length=3, max_length=64)


class OrganizationReadForAdmin(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    plan_tier: str


class OrganizationUserRead(BaseModel):
    id: int
    email: EmailStr
    role: str
    locale: str
    is_active: bool
    linked_team_member_id: int | None
    linked_team_member_label: str | None


OrganizationUserAssignableRole = Literal["admin", "planner", "team_member"]


class OrganizationUserRolePatch(BaseModel):
    role: OrganizationUserAssignableRole


StaffDirectoryLinkStatus = Literal[
    "team_member_only",
    "login_only",
    "login_unlinked",
    "linked_ok",
    "linked_wrong_user",
    "linked_foreign_user",
]


class OrganizationStaffDirectoryRow(BaseModel):
    email: str
    team_member_id: int | None
    team_member_label: str | None
    team_member_is_active: bool | None
    user_id: int | None
    user_role: str | None
    user_is_active: bool | None
    linked_user_id: int | None
    linked_user_role: str | None
    linked_user_is_active: bool | None
    link_status: StaffDirectoryLinkStatus


class JoinRequestRead(BaseModel):
    id: int
    organization_id: int
    requester_user_id: int
    requester_email: str
    first_name: str
    last_name: str
    message: str | None
    status: str
    resolution: str | None
    resolved_team_member_id: int | None
    created_at: datetime


OrganizationInviteRole = Literal["planner", "team_member"]


class OrganizationInviteCreate(BaseModel):
    invitee_email: EmailStr
    role: OrganizationInviteRole = "team_member"
    message: str | None = None
    prepare_team_member_profile: bool = False
    first_name: str | None = None
    last_name: str | None = None
    employment_percentage: int = Field(default=100, ge=1, le=100)
    notes: str | None = None
    shift_group_ids: list[int] = Field(default_factory=list)
    planner_shift_group_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_role_payload(self) -> Self:
        if self.role == "planner" and not self.planner_shift_group_ids:
            raise ValueError("planner_shift_group_ids is required for planner invites")
        if self.role == "team_member" and self.prepare_team_member_profile:
            if not (self.first_name or "").strip() or not (self.last_name or "").strip():
                raise ValueError("first_name and last_name are required when preparing a team member profile")
            if not self.shift_group_ids:
                raise ValueError("shift_group_ids is required when preparing a team member profile")
        return self


class OrganizationInviteAcceptInput(BaseModel):
    first_name: str | None = Field(default=None, max_length=255)
    last_name: str | None = Field(default=None, max_length=255)
    employment_percentage: int | None = Field(default=None, ge=1, le=100)
    shift_group_ids: list[int] | None = None
    notes: str | None = None


class OrganizationMembershipInviteRead(BaseModel):
    id: int
    organization_id: int
    invitee_email: str
    role: str
    status: str
    message: str | None
    first_name: str | None
    last_name: str | None
    employment_percentage: int | None
    shift_group_ids: list[int]
    planner_shift_group_ids: list[int]
    has_precreated_team_member: bool
    created_at: datetime


class ShiftGroupInviteOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name_de: str
    name_en: str
    is_active: bool = True


class OrganizationMembershipInvitePendingRead(BaseModel):
    id: int
    organization: OrganizationBrief
    role: str
    message: str | None
    first_name: str | None
    last_name: str | None
    needs_profile_on_accept: bool
    has_precreated_team_member: bool
    accept_shift_groups: list[ShiftGroupInviteOption] = Field(default_factory=list)
    created_at: datetime


class DeleteOrganizationInput(BaseModel):
    confirm_organization_name: str = Field(min_length=1, max_length=255)


class ApproveJoinCreateTeamMemberInput(BaseModel):
    first_name: str = Field(min_length=1, max_length=255)
    last_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    employment_percentage: int = Field(default=100, ge=1, le=100)
    notes: str | None = None
    shift_group_ids: list[int] = Field(default_factory=list)


class ApproveJoinLinkTeamMemberBody(BaseModel):
    team_member_id: int


class TeamMemberCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=255)
    last_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    employment_percentage: int = Field(default=100, ge=1, le=100)
    notes: str | None = None
    shift_group_ids: list[int] = Field(default_factory=list)
    user_id: int | None = None


class TeamMemberUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=255)
    last_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    employment_percentage: int | None = Field(default=None, ge=1, le=100)
    notes: str | None = None
    is_active: bool | None = None
    shift_group_ids: list[int] | None = None
    user_id: int | None = None


class TeamMemberSelfUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=255)
    last_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    employment_percentage: int | None = Field(default=None, ge=1, le=100)
    notes: str | None = None


class TeamMemberRead(TeamMemberCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    created_at: datetime


class ShiftGroupCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name_de: str = Field(min_length=1, max_length=255)
    name_en: str = Field(min_length=1, max_length=255)
    display_order: int = 0
    is_active: bool = True


class ShiftGroupUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name_de: str | None = Field(default=None, min_length=1, max_length=255)
    name_en: str | None = Field(default=None, min_length=1, max_length=255)
    display_order: int | None = None
    is_active: bool | None = None


class ShiftGroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name_de: str
    name_en: str
    display_order: int
    is_active: bool
    created_at: datetime
    team_member_ids: list[int] = Field(default_factory=list)
    shift_template_ids: list[int] = Field(default_factory=list)


class ShiftGroupTeamMemberIdsPut(BaseModel):
    team_member_ids: list[int] = Field(default_factory=list)


class ShiftGroupTemplateIdsPut(BaseModel):
    shift_template_ids: list[int] = Field(default_factory=list)


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
    published_at: datetime | None = None
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
    team_member_id: int
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
    team_member_id: int
    cell_date: date_type
    status: PlanningCellStatus
    comment: str | None = None
    source: str = "manual"


class PlanningCellUpsert(BaseModel):
    team_member_id: int
    cell_date: date_type
    status: PlanningCellStatus
    comment: str | None = None


class PlanningCellBulkUpsert(BaseModel):
    cells: list[PlanningCellUpsert]


class PlanningCellClear(BaseModel):
    team_member_id: int
    cell_date: date_type


class PlanningCellRead(PlanningCellBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    planning_period_id: int
    created_at: datetime
    updated_at: datetime


class MatrixTemplateSlotDay(BaseModel):
    cell_date: date_type
    shift_template_id: int
    shift_group_id: int | None = None


class PlanningShiftIntentUpsert(BaseModel):
    team_member_id: int
    cell_date: date_type
    shift_group_id: int
    shift_template_id: int
    kind: PlanningShiftIntentKind | None = None


class PlanningShiftIntentBulkUpsert(BaseModel):
    intents: list[PlanningShiftIntentUpsert]


class PlanningShiftIntentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    planning_period_id: int
    team_member_id: int
    cell_date: date_type
    shift_group_id: int
    shift_template_id: int
    kind: PlanningShiftIntentKind
    source: str
    created_at: datetime
    updated_at: datetime


class MatrixTeamMember(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: EmailStr
    employment_percentage: int


class MatrixDay(BaseModel):
    date: date_type
    weekday: str


class PlanningMatrixRead(BaseModel):
    planning_period: PlanningPeriodRead
    team_members: list[MatrixTeamMember]
    days: list[MatrixDay]
    cells: list[PlanningCellRead]
    shift_templates: list[ShiftTemplateRead] = Field(default_factory=list)
    shift_intents: list[PlanningShiftIntentRead] = Field(default_factory=list)
    template_slot_days: list[MatrixTemplateSlotDay] = Field(default_factory=list)


class RosterMatrixRead(BaseModel):
    planning_period: PlanningPeriodRead
    team_members: list[MatrixTeamMember]
    days: list[MatrixDay]
    shift_templates: list[ShiftTemplateRead] = Field(default_factory=list)
    slots: list[RosterSlotRead]
    assignments: list[RosterSlotAssignmentRead]
    planning_cells: list[PlanningCellRead]
    shift_intents: list[PlanningShiftIntentRead] = Field(default_factory=list)


class TeamMemberPeriodNoteUpsert(BaseModel):
    team_member_id: int
    source_text: str | None = None
    summary: str | None = None


class TeamMemberPeriodNoteRead(TeamMemberPeriodNoteUpsert):
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
    team_member_id: int | None = None
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
