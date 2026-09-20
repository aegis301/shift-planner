from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import WorkTimeRuleSetPreset
from app.schemas import (
    ContractGroupCreate,
    ContractGroupRead,
    ContractStatusMapping,
    RegularWeekPatternDay,
    WorkTimePresetContractGroup,
    WorkTimeRuleSetAdoptRead,
    WorkTimeRuleSetCreate,
    WorkTimeRuleSetPresetRead,
)
from app.services.contract_group_defaults import (
    default_regular_week_pattern,
    default_status_mappings,
)
from app.services.contract_groups import contract_group_to_read, create_contract_group
from app.services.work_time_preset_catalog import work_time_preset_catalog
from app.services.work_time_rule_sets import (
    _parse_rules,
    create_work_time_rule_set,
    work_time_rule_set_to_read,
)

_GROUPS_ADAPTER = TypeAdapter(list[WorkTimePresetContractGroup])


def work_time_rule_set_preset_to_read(row: WorkTimeRuleSetPreset) -> WorkTimeRuleSetPresetRead:
    return WorkTimeRuleSetPresetRead(
        id=row.id,
        code=row.code,
        name=row.name,
        values_confirmed=row.values_confirmed,
        rules=_parse_rules(row.rules),
        contract_groups=_GROUPS_ADAPTER.validate_python(row.contract_groups or []),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_work_time_rule_set_presets(db: Session) -> list[WorkTimeRuleSetPreset]:
    return list(db.scalars(select(WorkTimeRuleSetPreset).order_by(WorkTimeRuleSetPreset.name, WorkTimeRuleSetPreset.code)))


def get_work_time_rule_set_preset(db: Session, code: str) -> WorkTimeRuleSetPreset | None:
    return db.scalar(select(WorkTimeRuleSetPreset).where(WorkTimeRuleSetPreset.code == code))


def ensure_work_time_presets(db: Session) -> list[WorkTimeRuleSetPreset]:
    rows: list[WorkTimeRuleSetPreset] = []
    for spec in work_time_preset_catalog():
        row = get_work_time_rule_set_preset(db, spec["code"])
        if row is None:
            row = WorkTimeRuleSetPreset(
                code=spec["code"],
                name=spec["name"],
                values_confirmed=spec["values_confirmed"],
                rules=spec["rules"],
                contract_groups=spec["contract_groups"],
            )
            db.add(row)
        else:
            row.name = spec["name"]
            row.values_confirmed = spec["values_confirmed"]
            row.rules = spec["rules"]
            row.contract_groups = spec["contract_groups"]
        rows.append(row)
    db.flush()
    return rows


def adopt_work_time_rule_set_preset(
    db: Session,
    code: str,
    *,
    organization_id: int,
    actor: str,
    source: str,
    is_active: bool | None = None,
) -> WorkTimeRuleSetAdoptRead | None:
    preset = get_work_time_rule_set_preset(db, code)
    if preset is None:
        return None
    original_groups = list(preset.contract_groups or [])
    rule_set = create_work_time_rule_set(
        db,
        WorkTimeRuleSetCreate(
            name=preset.name,
            rules=_parse_rules(preset.rules),
            is_active=is_active,
        ),
        organization_id=organization_id,
        actor=actor,
        source=source,
        commit=False,
    )
    created_groups: list[ContractGroupRead] = []
    for blueprint in _GROUPS_ADAPTER.validate_python(original_groups):
        group = create_contract_group(
            db,
            ContractGroupCreate(
                name=blueprint.name,
                weekly_hours_at_100=blueprint.weekly_hours_at_100,
                vacation_days_at_100=blueprint.vacation_days_at_100,
                regular_week_pattern=[RegularWeekPatternDay.model_validate(item) for item in default_regular_week_pattern()],
                category_rules=blueprint.category_rules,
                status_mappings=[ContractStatusMapping.model_validate(item) for item in default_status_mappings()],
            ),
            organization_id=organization_id,
            actor=actor,
            source=source,
            commit=False,
        )
        created_groups.append(contract_group_to_read(group))
    db.commit()
    db.refresh(rule_set)
    return WorkTimeRuleSetAdoptRead(
        rule_set=work_time_rule_set_to_read(rule_set),
        contract_groups=created_groups,
    )
