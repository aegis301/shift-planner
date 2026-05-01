from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, Time, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), default="Default")
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    plan_tier: Mapped[str] = mapped_column(String(50), default="team")
    seat_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    billing_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subscription_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users: Mapped[list["User"]] = relationship(back_populates="organization")
    doctors: Mapped[list["Doctor"]] = relationship(back_populates="organization")
    shift_groups: Mapped[list["ShiftGroup"]] = relationship(back_populates="organization")
    shift_templates: Mapped[list["ShiftTemplate"]] = relationship(back_populates="organization")
    planning_periods: Mapped[list["PlanningPeriod"]] = relationship(back_populates="organization")
    join_requests: Mapped[list["OrganizationJoinRequest"]] = relationship(back_populates="organization")


class ShiftGroup(Base):
    __tablename__ = "shift_groups"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_shift_group_org_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    code: Mapped[str] = mapped_column(String(50), index=True)
    name_de: Mapped[str] = mapped_column(String(255))
    name_en: Mapped[str] = mapped_column(String(255))
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped["Organization"] = relationship(back_populates="shift_groups")
    doctor_links: Mapped[list["DoctorShiftGroup"]] = relationship(
        back_populates="shift_group", cascade="all, delete-orphan"
    )
    template_links: Mapped[list["ShiftGroupShiftTemplate"]] = relationship(
        back_populates="shift_group", cascade="all, delete-orphan"
    )
    planner_links: Mapped[list["UserShiftGroup"]] = relationship(
        back_populates="shift_group", cascade="all, delete-orphan"
    )


class DoctorShiftGroup(Base):
    __tablename__ = "doctor_shift_groups"
    __table_args__ = (UniqueConstraint("doctor_id", "shift_group_id", name="uq_doctor_shift_group"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id", ondelete="CASCADE"))
    shift_group_id: Mapped[int] = mapped_column(ForeignKey("shift_groups.id", ondelete="CASCADE"))

    doctor: Mapped["Doctor"] = relationship(back_populates="shift_group_links")
    shift_group: Mapped["ShiftGroup"] = relationship(back_populates="doctor_links")


class ShiftGroupShiftTemplate(Base):
    __tablename__ = "shift_group_shift_templates"
    __table_args__ = (UniqueConstraint("shift_group_id", "shift_template_id", name="uq_shift_group_template"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shift_group_id: Mapped[int] = mapped_column(ForeignKey("shift_groups.id", ondelete="CASCADE"))
    shift_template_id: Mapped[int] = mapped_column(ForeignKey("shift_templates.id", ondelete="CASCADE"))

    shift_group: Mapped["ShiftGroup"] = relationship(back_populates="template_links")
    shift_template: Mapped["ShiftTemplate"] = relationship(back_populates="shift_group_links")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("organization_id", "email", name="uq_users_organization_email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="admin")
    locale: Mapped[str] = mapped_column(String(5), default="de")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped["Organization"] = relationship(back_populates="users")
    planner_shift_group_links: Mapped[list["UserShiftGroup"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    linked_doctor: Mapped["Doctor | None"] = relationship(
        back_populates="user",
        uselist=False,
        foreign_keys="Doctor.user_id",
    )


class UserShiftGroup(Base):
    __tablename__ = "user_shift_groups"
    __table_args__ = (UniqueConstraint("user_id", "shift_group_id", name="uq_user_shift_group"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    shift_group_id: Mapped[int] = mapped_column(ForeignKey("shift_groups.id", ondelete="CASCADE"))

    user: Mapped["User"] = relationship(back_populates="planner_shift_group_links")
    shift_group: Mapped["ShiftGroup"] = relationship(back_populates="planner_links")


class Doctor(Base):
    __tablename__ = "doctors"
    __table_args__ = (UniqueConstraint("organization_id", "email", name="uq_doctor_org_email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    first_name: Mapped[str] = mapped_column(String(255))
    last_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), index=True)
    employment_percentage: Mapped[int] = mapped_column(Integer, default=100)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped["Organization"] = relationship(back_populates="doctors")
    user: Mapped["User | None"] = relationship(back_populates="linked_doctor", foreign_keys=[user_id])
    shift_group_links: Mapped[list["DoctorShiftGroup"]] = relationship(
        back_populates="doctor", cascade="all, delete-orphan"
    )


class ShiftTemplate(Base):
    __tablename__ = "shift_templates"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_shift_template_org_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    code: Mapped[str] = mapped_column(String(50), index=True)
    name_de: Mapped[str] = mapped_column(String(255))
    name_en: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(50))
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped["Organization"] = relationship(back_populates="shift_templates")
    variants: Mapped[list["ShiftVariant"]] = relationship(back_populates="shift_template", cascade="all, delete-orphan")
    shift_group_links: Mapped[list["ShiftGroupShiftTemplate"]] = relationship(
        back_populates="shift_template", cascade="all, delete-orphan"
    )


class ShiftVariant(Base):
    __tablename__ = "shift_variants"

    id: Mapped[int] = mapped_column(primary_key=True)
    shift_template_id: Mapped[int] = mapped_column(ForeignKey("shift_templates.id"))
    label: Mapped[str] = mapped_column(String(255))
    start_day_class: Mapped[str] = mapped_column(String(50))
    end_day_class: Mapped[str | None] = mapped_column(String(50))
    starts_at: Mapped[time] = mapped_column(Time)
    ends_at: Mapped[time] = mapped_column(Time)
    end_day_offset: Mapped[int] = mapped_column(Integer, default=0)
    required_count: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    shift_template: Mapped[ShiftTemplate] = relationship(back_populates="variants")


class PlanningPeriod(Base):
    __tablename__ = "planning_periods"
    __table_args__ = (UniqueConstraint("organization_id", "year", "month", name="uq_planning_period_org_month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(50), default="draft")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped["Organization"] = relationship(back_populates="planning_periods")


class RuleConfig(Base):
    __tablename__ = "rule_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    max_consecutive_work_days: Mapped[int] = mapped_column(Integer, default=6)
    min_rest_hours: Mapped[int] = mapped_column(Integer, default=11)
    max_monthly_nights_full_time: Mapped[int] = mapped_column(Integer, default=7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RosterSlot(Base):
    __tablename__ = "roster_slots"
    __table_args__ = (
        UniqueConstraint("planning_period_id", "slot_date", "shift_variant_id", "position", name="uq_roster_slot"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    planning_period_id: Mapped[int] = mapped_column(ForeignKey("planning_periods.id"))
    shift_template_id: Mapped[int | None] = mapped_column(ForeignKey("shift_templates.id"))
    shift_variant_id: Mapped[int | None] = mapped_column(ForeignKey("shift_variants.id"))
    slot_date: Mapped[date] = mapped_column(Date)
    position: Mapped[int] = mapped_column(Integer, default=1)
    label: Mapped[str | None] = mapped_column(String(255))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    day_class: Mapped[str | None] = mapped_column(String(50))
    source: Mapped[str] = mapped_column(String(50), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    planning_period: Mapped[PlanningPeriod] = relationship()
    shift_template: Mapped[ShiftTemplate | None] = relationship()
    shift_variant: Mapped[ShiftVariant | None] = relationship()


class RosterSlotAssignment(Base):
    __tablename__ = "roster_slot_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    roster_slot_id: Mapped[int] = mapped_column(ForeignKey("roster_slots.id"), unique=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"))
    comment: Mapped[str | None] = mapped_column(Text)
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(50), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    roster_slot: Mapped[RosterSlot] = relationship()
    doctor: Mapped[Doctor] = relationship()


class PlanningCell(Base):
    __tablename__ = "planning_cells"
    __table_args__ = (
        UniqueConstraint("planning_period_id", "doctor_id", "cell_date", name="uq_planning_cell"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    planning_period_id: Mapped[int] = mapped_column(ForeignKey("planning_periods.id"))
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"))
    cell_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(50))
    comment: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(50), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    doctor: Mapped[Doctor] = relationship()
    planning_period: Mapped[PlanningPeriod] = relationship()


class PlanningShiftIntent(Base):
    __tablename__ = "planning_shift_intents"
    __table_args__ = (
        UniqueConstraint(
            "planning_period_id",
            "doctor_id",
            "cell_date",
            "shift_group_id",
            "shift_template_id",
            name="uq_planning_shift_intent",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    planning_period_id: Mapped[int] = mapped_column(ForeignKey("planning_periods.id", ondelete="CASCADE"))
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id", ondelete="CASCADE"))
    cell_date: Mapped[date] = mapped_column(Date)
    shift_group_id: Mapped[int] = mapped_column(ForeignKey("shift_groups.id", ondelete="CASCADE"))
    shift_template_id: Mapped[int] = mapped_column(ForeignKey("shift_templates.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(50), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    planning_period: Mapped[PlanningPeriod] = relationship()
    doctor: Mapped[Doctor] = relationship()
    shift_group: Mapped[ShiftGroup] = relationship()
    shift_template: Mapped[ShiftTemplate] = relationship()


class DoctorPeriodNote(Base):
    __tablename__ = "doctor_period_notes"
    __table_args__ = (
        UniqueConstraint("planning_period_id", "doctor_id", name="uq_doctor_period_note"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    planning_period_id: Mapped[int] = mapped_column(ForeignKey("planning_periods.id"))
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"))
    source_text: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    doctor: Mapped[Doctor] = relationship()
    planning_period: Mapped[PlanningPeriod] = relationship()


class OrganizationJoinRequest(Base):
    __tablename__ = "organization_join_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    requester_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    first_name: Mapped[str] = mapped_column(String(255))
    last_name: Mapped[str] = mapped_column(String(255))
    message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    resolution: Mapped[str | None] = mapped_column(String(32))
    resolved_doctor_id: Mapped[int | None] = mapped_column(ForeignKey("doctors.id", ondelete="SET NULL"))
    resolved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    organization: Mapped["Organization"] = relationship(back_populates="join_requests")
    requester: Mapped["User"] = relationship(foreign_keys=[requester_user_id])


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str | None] = mapped_column(String(100))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
