import calendar
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import RosterSlot, RosterSlotAssignment, ShiftTemplate, ShiftVariant
from app.schemas import (
    GeneratedRosterSlotPreview,
    ShiftTemplateCreate,
    ShiftTemplateUpdate,
    ShiftVariantCreate,
    ShiftVariantUpdate,
)
from app.services.audit import record_audit
from app.services.holidays import classify_day

@dataclass(frozen=True)
class GeneratedSlot:
    slot_date: date
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


def list_shift_templates(db: Session, *, active_only: bool = False) -> list[ShiftTemplate]:
    stmt = (
        select(ShiftTemplate)
        .options(joinedload(ShiftTemplate.variants))
        .order_by(ShiftTemplate.name_de, ShiftTemplate.code)
    )
    if active_only:
        stmt = stmt.where(ShiftTemplate.is_active.is_(True))
    return list(db.scalars(stmt).unique())


def create_shift_template(db: Session, payload: ShiftTemplateCreate, *, actor: str, source: str) -> ShiftTemplate:
    template = ShiftTemplate(**payload.model_dump())
    db.add(template)
    db.flush()
    record_audit(db, actor=actor, source=source, action="create", entity_type="shift_template", entity_id=template.id)
    db.commit()
    db.refresh(template)
    return template


def update_shift_template(
    db: Session, template_id: int, payload: ShiftTemplateUpdate, *, actor: str, source: str
) -> ShiftTemplate | None:
    template = db.get(ShiftTemplate, template_id)
    if template is None:
        return None
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(template, key, value)
    record_audit(db, actor=actor, source=source, action="update", entity_type="shift_template", entity_id=template.id)
    db.commit()
    db.refresh(template)
    return template


def delete_shift_template(db: Session, template_id: int, *, actor: str, source: str) -> bool:
    template = db.get(ShiftTemplate, template_id)
    if template is None:
        return False
    slot_ids = list(db.scalars(select(RosterSlot.id).where(RosterSlot.shift_template_id == template_id)))
    if slot_ids:
        for assignment in db.scalars(select(RosterSlotAssignment).where(RosterSlotAssignment.roster_slot_id.in_(slot_ids))):
            db.delete(assignment)
    for slot in db.scalars(select(RosterSlot).where(RosterSlot.shift_template_id == template_id)):
        db.delete(slot)
    record_audit(
        db,
        actor=actor,
        source=source,
        action="delete",
        entity_type="shift_template",
        entity_id=template.id,
        details={"code": template.code, "cleared_slot_count": len(slot_ids)},
    )
    db.delete(template)
    db.commit()
    return True


def create_shift_variant(
    db: Session,
    template_id: int,
    payload: ShiftVariantCreate,
    *,
    actor: str,
    source: str,
) -> ShiftVariant | None:
    template = db.get(ShiftTemplate, template_id)
    if template is None:
        return None
    variant = ShiftVariant(shift_template_id=template_id, **payload.model_dump())
    db.add(variant)
    db.flush()
    record_audit(db, actor=actor, source=source, action="create", entity_type="shift_variant", entity_id=variant.id)
    db.commit()
    db.refresh(variant)
    return variant


def update_shift_variant(
    db: Session,
    variant_id: int,
    payload: ShiftVariantUpdate,
    *,
    actor: str,
    source: str,
) -> ShiftVariant | None:
    variant = db.get(ShiftVariant, variant_id)
    if variant is None:
        return None
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(variant, key, value)
    record_audit(db, actor=actor, source=source, action="update", entity_type="shift_variant", entity_id=variant.id)
    db.commit()
    db.refresh(variant)
    return variant


def _variant_applies(
    variant: ShiftVariant,
    start_class: str,
    end_class: str,
    *,
    has_start_holiday_variant: bool,
    has_end_holiday_variant: bool,
) -> bool:
    effective_start_classes = {start_class}
    if start_class == "holiday" and not has_start_holiday_variant:
        effective_start_classes.add("weekend")
    if variant.start_day_class not in effective_start_classes and variant.start_day_class != "any":
        return False
    if variant.end_day_class is None:
        return True
    effective_end_classes = {end_class}
    if end_class == "holiday" and not has_end_holiday_variant:
        effective_end_classes.add("weekend")
    return variant.end_day_class in effective_end_classes or variant.end_day_class == "any"


def _combine(day: date, value: time) -> datetime:
    return datetime.combine(day, value)


def generate_slots_for_month(db: Session, *, year: int, month: int) -> list[GeneratedSlot]:
    templates = list_shift_templates(db, active_only=True)
    days_in_month = calendar.monthrange(year, month)[1]
    generated: list[GeneratedSlot] = []
    for day_number in range(1, days_in_month + 1):
        slot_date = date(year, month, day_number)
        start_class = classify_day(slot_date)
        for template in templates:
            active_variants = [variant for variant in template.variants if variant.is_active]
            has_start_holiday_variant = any(variant.start_day_class == "holiday" for variant in active_variants)
            has_end_holiday_variant = any(variant.end_day_class == "holiday" for variant in active_variants)
            for variant in active_variants:
                end_date = slot_date + timedelta(days=variant.end_day_offset)
                end_class = classify_day(end_date)
                if not _variant_applies(
                    variant,
                    start_class,
                    end_class,
                    has_start_holiday_variant=has_start_holiday_variant,
                    has_end_holiday_variant=has_end_holiday_variant,
                ):
                    continue
                starts_at = _combine(slot_date, variant.starts_at)
                ends_at = _combine(end_date, variant.ends_at)
                if ends_at <= starts_at:
                    ends_at = ends_at + timedelta(days=1)
                time_label = f"{variant.starts_at.strftime('%H:%M')}-{variant.ends_at.strftime('%H:%M')}"
                for position in range(1, variant.required_count + 1):
                    label = f"{template.name_de} {time_label}"
                    if variant.required_count > 1:
                        label = f"{label} #{position}"
                    generated.append(
                        GeneratedSlot(
                            slot_date=slot_date,
                            label=label,
                            starts_at=starts_at,
                            ends_at=ends_at,
                            day_class=start_class,
                            template_id=template.id,
                            template_code=template.code,
                            template_name_de=template.name_de,
                            template_name_en=template.name_en,
                            variant_id=variant.id,
                            variant_label=variant.label,
                            category=template.category,
                            position=position,
                        )
                    )
    return generated


def preview_slots_for_month(db: Session, *, year: int, month: int) -> list[GeneratedRosterSlotPreview]:
    return [GeneratedRosterSlotPreview(**slot.__dict__) for slot in generate_slots_for_month(db, year=year, month=month)]
