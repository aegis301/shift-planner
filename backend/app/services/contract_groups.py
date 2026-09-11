from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ContractGroup, EmploymentPeriod
from app.schemas import (
    ContractCategoryRule,
    ContractGroupCreate,
    ContractGroupRead,
    ContractGroupUpdate,
    ContractStatusMapping,
    RegularWeekPatternDay,
)
from app.services.audit import record_audit
from app.services.contract_group_defaults import (
    DEFAULT_CONTRACT_GROUP_NAME,
    DEFAULT_VACATION_DAYS_AT_100,
    DEFAULT_WEEKLY_HOURS_AT_100,
    default_category_rules,
    default_regular_week_pattern,
    default_status_mappings,
)


def _dump_json(value: list) -> list:
    return [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in value]


def contract_group_to_read(row: ContractGroup) -> ContractGroupRead:
    return ContractGroupRead(
        id=row.id,
        name=row.name,
        display_order=row.display_order,
        is_active=row.is_active,
        weekly_hours_at_100=row.weekly_hours_at_100,
        vacation_days_at_100=row.vacation_days_at_100,
        regular_week_pattern=[RegularWeekPatternDay.model_validate(item) for item in row.regular_week_pattern or []],
        category_rules=[ContractCategoryRule.model_validate(item) for item in row.category_rules or []],
        status_mappings=[ContractStatusMapping.model_validate(item) for item in row.status_mappings or []],
        created_at=row.created_at,
    )


def list_contract_groups(db: Session, *, organization_id: int, active_only: bool = False) -> list[ContractGroup]:
    stmt = (
        select(ContractGroup)
        .where(ContractGroup.organization_id == organization_id)
        .order_by(ContractGroup.display_order, ContractGroup.name, ContractGroup.id)
    )
    if active_only:
        stmt = stmt.where(ContractGroup.is_active.is_(True))
    return list(db.scalars(stmt))


def get_contract_group(db: Session, contract_group_id: int, *, organization_id: int) -> ContractGroup | None:
    row = db.get(ContractGroup, contract_group_id)
    if row is None or row.organization_id != organization_id:
        return None
    return row


def ensure_default_contract_group(db: Session, *, organization_id: int) -> ContractGroup:
    existing = list_contract_groups(db, organization_id=organization_id)
    if existing:
        return existing[0]
    row = ContractGroup(
        organization_id=organization_id,
        name=DEFAULT_CONTRACT_GROUP_NAME,
        display_order=0,
        is_active=True,
        weekly_hours_at_100=Decimal(DEFAULT_WEEKLY_HOURS_AT_100),
        vacation_days_at_100=Decimal(DEFAULT_VACATION_DAYS_AT_100),
        regular_week_pattern=default_regular_week_pattern(),
        category_rules=default_category_rules(),
        status_mappings=default_status_mappings(),
    )
    db.add(row)
    db.flush()
    return row


def create_contract_group(
    db: Session,
    payload: ContractGroupCreate,
    *,
    organization_id: int,
    actor: str,
    source: str,
    commit: bool = True,
) -> ContractGroup:
    row = ContractGroup(
        organization_id=organization_id,
        name=payload.name.strip(),
        display_order=payload.display_order,
        is_active=payload.is_active,
        weekly_hours_at_100=payload.weekly_hours_at_100,
        vacation_days_at_100=payload.vacation_days_at_100,
        regular_week_pattern=_dump_json(payload.regular_week_pattern),
        category_rules=_dump_json(payload.category_rules),
        status_mappings=_dump_json(payload.status_mappings),
    )
    db.add(row)
    db.flush()
    record_audit(db, actor=actor, source=source, action="create", entity_type="contract_group", entity_id=row.id)
    if commit:
        db.commit()
        db.refresh(row)
    return row


def update_contract_group(
    db: Session,
    contract_group_id: int,
    payload: ContractGroupUpdate,
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> ContractGroup | None:
    row = get_contract_group(db, contract_group_id, organization_id=organization_id)
    if row is None:
        return None
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        row.name = data["name"].strip()
    if "display_order" in data and data["display_order"] is not None:
        row.display_order = data["display_order"]
    if "is_active" in data and data["is_active"] is not None:
        row.is_active = data["is_active"]
    if "weekly_hours_at_100" in data and data["weekly_hours_at_100"] is not None:
        row.weekly_hours_at_100 = data["weekly_hours_at_100"]
    if "vacation_days_at_100" in data and data["vacation_days_at_100"] is not None:
        row.vacation_days_at_100 = data["vacation_days_at_100"]
    if "regular_week_pattern" in data and data["regular_week_pattern"] is not None:
        row.regular_week_pattern = _dump_json(payload.regular_week_pattern or [])
    if "category_rules" in data and data["category_rules"] is not None:
        row.category_rules = _dump_json(payload.category_rules or [])
    if "status_mappings" in data and data["status_mappings"] is not None:
        row.status_mappings = _dump_json(payload.status_mappings or [])
    record_audit(db, actor=actor, source=source, action="update", entity_type="contract_group", entity_id=row.id)
    db.commit()
    db.refresh(row)
    return row


def delete_contract_group(
    db: Session, contract_group_id: int, *, organization_id: int, actor: str, source: str
) -> bool:
    row = get_contract_group(db, contract_group_id, organization_id=organization_id)
    if row is None:
        return False
    referenced = db.scalar(
        select(EmploymentPeriod.id).where(EmploymentPeriod.contract_group_id == row.id).limit(1)
    )
    if referenced is not None:
        raise ValueError("Contract group is referenced by an employment period")
    record_audit(db, actor=actor, source=source, action="delete", entity_type="contract_group", entity_id=row.id)
    db.delete(row)
    db.commit()
    return True
