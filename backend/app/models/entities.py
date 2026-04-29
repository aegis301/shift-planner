from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, Time, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="admin")
    locale: Mapped[str] = mapped_column(String(5), default="de")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Doctor(Base):
    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    employment_percentage: Mapped[int] = mapped_column(Integer, default=100)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ShiftTemplate(Base):
    __tablename__ = "shift_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name_de: Mapped[str] = mapped_column(String(255))
    name_en: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(50))
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    variants: Mapped[list["ShiftVariant"]] = relationship(back_populates="shift_template", cascade="all, delete-orphan")


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
    __table_args__ = (UniqueConstraint("year", "month", name="uq_planning_period_month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(50), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
