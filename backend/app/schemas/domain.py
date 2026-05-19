from datetime import date as date_type
from datetime import datetime, time
from typing import Annotated, Any, Literal, Self, Union

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

PlanningCellStatus = Literal["urlaub", "forschung", "lehre", "frei"]
PlanningPeriodStatus = Literal["draft", "preliminary", "published"]

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

    auth_kind: Literal["user"] = "user"
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


class AccountSessionRead(BaseModel):
    auth_kind: Literal["account"] = "account"
    email: EmailStr
    locale: str
    memberships: list[MembershipSummary] = Field(default_factory=list)


AuthLoginResponse = Annotated[Union[UserRead, AccountSessionRead], Field(discriminator="auth_kind")]
AuthMeResponse = Annotated[Union[UserRead, AccountSessionRead], Field(discriminator="auth_kind")]


class ActiveOrganizationInput(BaseModel):
    organization_slug: str = Field(min_length=1, max_length=64)


class LoginInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class RegisterAccountInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    password_confirm: str = Field(min_length=8, max_length=256)
    locale: str = Field(default="de", pattern=r"^(de|en)$")

    @model_validator(mode="after")
    def register_passwords_match(self) -> Self:
        if self.password != self.password_confirm:
            raise ValueError("passwords_do_not_match")
        return self


class OnboardingCreateOrganizationInput(BaseModel):
    organization_name: str = Field(min_length=1, max_length=255)
    organization_slug: str = Field(min_length=3, max_length=64)


class CreateOrganizationMembershipInput(BaseModel):
    organization_name: str = Field(min_length=1, max_length=255)
    organization_slug: str = Field(min_length=3, max_length=64)


class OnboardingJoinOrganizationInput(BaseModel):
    organization_slug: str = Field(min_length=1, max_length=64)
    first_name: str = Field(min_length=1, max_length=255)
    last_name: str = Field(min_length=1, max_length=255)
    message: str | None = Field(default=None, max_length=2000)


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
    planning_preferences: str | None = None
    shift_group_ids: list[int] = Field(default_factory=list)
    user_id: int | None = None


class TeamMemberUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=255)
    last_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    employment_percentage: int | None = Field(default=None, ge=1, le=100)
    notes: str | None = None
    planning_preferences: str | None = None
    is_active: bool | None = None
    shift_group_ids: list[int] | None = None
    user_id: int | None = None


class TeamMemberSelfUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=255)
    last_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    employment_percentage: int | None = Field(default=None, ge=1, le=100)
    notes: str | None = None
    planning_preferences: str | None = None


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
ConstraintSeverity = Literal["info", "warning", "error"]

_PROPERTY_REQUIREMENT_MAX_ITEMS = 32
_PROPERTY_REQUIREMENT_MAX_DEPTH = 8
_PROPERTY_REQUIREMENT_MAX_NODES = 64


class TeamMemberPropertyRequirementAtom(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: Literal["atom"] = "atom"
    property_definition_id: int = Field(ge=1)
    op: str = Field(min_length=1, max_length=32)
    value: Any


class TeamMemberPropertyRequirementAll(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: Literal["all"] = "all"
    items: list["TeamMemberPropertyRequirementExpr"] = Field(
        min_length=1, max_length=_PROPERTY_REQUIREMENT_MAX_ITEMS
    )


class TeamMemberPropertyRequirementAny(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: Literal["any"] = "any"
    items: list["TeamMemberPropertyRequirementExpr"] = Field(
        min_length=1, max_length=_PROPERTY_REQUIREMENT_MAX_ITEMS
    )


TeamMemberPropertyRequirementExpr = Annotated[
    Union[TeamMemberPropertyRequirementAll, TeamMemberPropertyRequirementAny, TeamMemberPropertyRequirementAtom],
    Field(discriminator="kind"),
]

TeamMemberPropertyRequirementAll.model_rebuild()
TeamMemberPropertyRequirementAny.model_rebuild()

ShiftConstraintType = Literal[
    "no_additional_same_day",
    "min_rest_hours",
    "no_cross_day_into_unavailable_day",
    "max_assignments_per_month",
    "requires_coupled_shift",
    "team_member_property_requirement",
]


class ShiftConstraint(BaseModel):
    type: ShiftConstraintType
    severity: ConstraintSeverity = "warning"
    min_rest_hours: int | None = Field(default=None, ge=1, le=48)
    max_assignments_per_month: int | None = Field(default=None, ge=1, le=31)
    paired_shift_variant_id: int | None = Field(default=None, ge=1)
    partner_day_offset: int = Field(default=1, ge=-7, le=7)
    property_requirement: TeamMemberPropertyRequirementExpr | None = None

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_enforcement(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        next_data = dict(data)
        if "severity" in next_data:
            next_data.pop("enforcement", None)
            return next_data
        enforcement = next_data.pop("enforcement", None)
        if enforcement == "block":
            next_data["severity"] = "error"
        elif enforcement == "warning":
            next_data["severity"] = "warning"
        return next_data

    @model_validator(mode="after")
    def validate_min_rest_hours(self) -> Self:
        if self.type == "min_rest_hours":
            if self.min_rest_hours is None:
                raise ValueError("min_rest_hours is required for min_rest_hours constraints")
            self.max_assignments_per_month = None
            self.paired_shift_variant_id = None
            self.partner_day_offset = 1
            self.property_requirement = None
            return self
        if self.type == "max_assignments_per_month":
            if self.max_assignments_per_month is None:
                raise ValueError("max_assignments_per_month is required for max_assignments_per_month constraints")
            self.min_rest_hours = None
            self.paired_shift_variant_id = None
            self.partner_day_offset = 1
            self.property_requirement = None
            return self
        if self.type == "requires_coupled_shift":
            if self.paired_shift_variant_id is None:
                raise ValueError("paired_shift_variant_id is required for requires_coupled_shift constraints")
            self.min_rest_hours = None
            self.max_assignments_per_month = None
            self.property_requirement = None
            return self
        if self.type == "team_member_property_requirement":
            if self.property_requirement is None:
                raise ValueError("property_requirement is required for team_member_property_requirement constraints")
            self.min_rest_hours = None
            self.max_assignments_per_month = None
            self.paired_shift_variant_id = None
            self.partner_day_offset = 1
            return self
        self.min_rest_hours = None
        self.max_assignments_per_month = None
        self.paired_shift_variant_id = None
        self.partner_day_offset = 1
        self.property_requirement = None
        return self


PatternWeekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
MemberPatternRuleType = Literal["avoid_time_window", "allowed_calendar_week_parity", "recurring_weekday_status"]
MemberPatternHardType = Literal["allowed_calendar_week_parity"]
TimeWindowAnchor = Literal["slot_start_day", "any_overlap_day"]


class AvoidTimeWindowBand(BaseModel):
    weekdays: list[PatternWeekday] = Field(min_length=1)
    window_start: time
    window_end: time
    match_mode: Literal["overlap"] = "overlap"
    anchor: TimeWindowAnchor = "any_overlap_day"


class AvoidTimeWindowMemberPatternRule(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["avoid_time_window"] = "avoid_time_window"
    match_mode: Literal["overlap"] = "overlap"
    windows: list[AvoidTimeWindowBand] = Field(min_length=1, max_length=32)

    @model_validator(mode="before")
    @classmethod
    def _legacy_flat_window_to_windows(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if data.get("type") != "avoid_time_window":
            return data
        if data.get("windows"):
            return data
        weekdays = data.get("weekdays")
        window_start = data.get("window_start")
        window_end = data.get("window_end")
        if weekdays and window_start is not None and window_end is not None:
            rest = {k: v for k, v in data.items() if k not in ("weekdays", "window_start", "window_end", "anchor")}
            rest["windows"] = [
                {
                    "weekdays": weekdays,
                    "window_start": window_start,
                    "window_end": window_end,
                    "match_mode": data.get("match_mode", "overlap"),
                    "anchor": data.get("anchor", "any_overlap_day"),
                }
            ]
            return rest
        return data


class AllowedCalendarWeekParityMemberPatternRule(BaseModel):
    type: Literal["allowed_calendar_week_parity"] = "allowed_calendar_week_parity"
    parity: Literal["even", "odd"]
    status: PlanningCellStatus = "frei"


class RecurringWeekdayStatusMemberPatternRule(BaseModel):
    type: Literal["recurring_weekday_status"] = "recurring_weekday_status"
    weekdays: list[PatternWeekday] = Field(min_length=1)
    status: PlanningCellStatus


MemberPlanningPatternRule = Annotated[
    AvoidTimeWindowMemberPatternRule
    | AllowedCalendarWeekParityMemberPatternRule
    | RecurringWeekdayStatusMemberPatternRule,
    Field(discriminator="type"),
]


class OrganizationMemberPatternPolicy(BaseModel):
    hard_types: list[MemberPatternHardType] = Field(default_factory=list)

    @field_validator("hard_types", mode="before")
    @classmethod
    def _only_parity_hard_types(cls, value: object) -> object:
        if not value:
            return []
        allowed = {"allowed_calendar_week_parity"}
        if isinstance(value, list):
            return [item for item in value if item in allowed]
        return value


class TeamMemberPlanningPatternUpsertItem(BaseModel):
    label: str = Field(min_length=1, max_length=255)
    is_active: bool = True
    rule: MemberPlanningPatternRule
    severity: ConstraintSeverity = "warning"
    display_order: int = Field(default=0, ge=0, le=10_000)


class TeamMemberPlanningPatternsReplace(BaseModel):
    patterns: list[TeamMemberPlanningPatternUpsertItem] = Field(default_factory=list)


class TeamMemberPlanningPatternRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    team_member_id: int
    label: str
    is_active: bool
    rule: dict[str, Any]
    severity: ConstraintSeverity
    display_order: int
    created_at: datetime
    updated_at: datetime


class OrganizationMemberPatternPolicyRead(BaseModel):
    hard_types: list[MemberPatternHardType] = Field(default_factory=list)

    @field_validator("hard_types", mode="before")
    @classmethod
    def _filter_hard_types_read(cls, value: object) -> object:
        if not value:
            return []
        allowed = {"allowed_calendar_week_parity"}
        if isinstance(value, list):
            return [item for item in value if item in allowed]
        return value


class OrganizationMemberPatternPolicyUpdate(BaseModel):
    hard_types: list[MemberPatternHardType] = Field(default_factory=list)

    @field_validator("hard_types", mode="before")
    @classmethod
    def _filter_hard_types_update(cls, value: object) -> object:
        if not value:
            return []
        allowed = {"allowed_calendar_week_parity"}
        if isinstance(value, list):
            return [item for item in value if item in allowed]
        return value


TeamMemberPropertyType = Literal["number", "date", "select", "multi_select", "text"]
_SELECT_PROPERTY_TYPES = frozenset({"select", "multi_select"})


class TeamMemberPropertyDefinitionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: TeamMemberPropertyType
    options: list[str] = Field(default_factory=list)
    editable_by_team_member: bool = True
    display_order: int = Field(default=0, ge=0, le=10_000)
    is_active: bool = True

    @field_validator("options", mode="before")
    @classmethod
    def _normalize_options(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("options must be a list")
        return [str(item).strip() for item in value if str(item).strip()]

    @model_validator(mode="after")
    def _validate_options_for_type(self) -> Self:
        if self.type in _SELECT_PROPERTY_TYPES:
            if not self.options:
                raise ValueError("options are required for select and multi_select property types")
        elif self.options:
            raise ValueError("options are only allowed for select and multi_select property types")
        return self


class TeamMemberPropertyDefinitionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    type: TeamMemberPropertyType | None = None
    options: list[str] | None = None
    editable_by_team_member: bool | None = None
    display_order: int | None = Field(default=None, ge=0, le=10_000)
    is_active: bool | None = None

    @field_validator("options", mode="before")
    @classmethod
    def _normalize_options(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError("options must be a list")
        return [str(item).strip() for item in value if str(item).strip()]


class TeamMemberPropertyDefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    name: str
    type: TeamMemberPropertyType
    options: list[str] = Field(default_factory=list)
    editable_by_team_member: bool
    display_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TeamMemberPropertyValueUpsertItem(BaseModel):
    property_definition_id: int
    value: Any | None = None


class TeamMemberPropertyValuesReplace(BaseModel):
    values: list[TeamMemberPropertyValueUpsertItem] = Field(default_factory=list)


class TeamMemberPropertyValueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    organization_id: int
    team_member_id: int
    property_definition_id: int
    value: Any | None = None
    name: str
    type: TeamMemberPropertyType
    options: list[str] = Field(default_factory=list)
    editable_by_team_member: bool
    display_order: int
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ShiftVariantCreate(BaseModel):
    label: str = Field(min_length=1, max_length=255)
    start_day_class: DayClass = "any"
    end_day_class: DayClass | None = None
    starts_at: time
    ends_at: time
    end_day_offset: int = Field(default=0, ge=0, le=1)
    required_count: int = Field(default=1, ge=1, le=20)
    constraints: list[ShiftConstraint] = Field(default_factory=list)


class ShiftVariantUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=255)
    start_day_class: DayClass | None = None
    end_day_class: DayClass | None = None
    starts_at: time | None = None
    ends_at: time | None = None
    end_day_offset: int | None = Field(default=None, ge=0, le=1)
    required_count: int | None = Field(default=None, ge=1, le=20)
    constraints: list[ShiftConstraint] | None = None
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
    constraints: list[ShiftConstraint] = Field(default_factory=list)


class ShiftTemplateUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name_de: str | None = None
    name_en: str | None = None
    category: ShiftTemplateCategory | None = None
    display_order: int | None = None
    constraints: list[ShiftConstraint] | None = None
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
    status: PlanningPeriodStatus
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
    planning_preferences: str | None = None


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
    summary: str | None = None
    wishes_response_received: bool = False
    planning_preferences: str | None = None
    sync_planning_preferences: bool = False


class TeamMemberPeriodNoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    planning_period_id: int
    team_member_id: int
    summary: str | None = None
    wishes_response_received: bool
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
