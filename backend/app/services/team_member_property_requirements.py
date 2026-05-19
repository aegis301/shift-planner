from __future__ import annotations

import re
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TeamMemberPropertyDefinition
from app.schemas.domain import (
    TeamMemberPropertyRequirementAll,
    TeamMemberPropertyRequirementAny,
    TeamMemberPropertyRequirementAtom,
    TeamMemberPropertyRequirementExpr,
)


class TeamMemberPropertyRequirementError(Exception):
    pass


_MAX_DEPTH = 8
_MAX_NODES = 64
_TEXT_MAX_LEN = 500
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_ATOM_OPS: dict[str, frozenset[str]] = {
    "number": frozenset({"eq", "neq", "gte", "lte"}),
    "date": frozenset({"eq", "before", "after"}),
    "text": frozenset({"eq", "neq", "contains"}),
    "select": frozenset({"eq", "neq", "one_of"}),
    "multi_select": frozenset({"contains_all", "contains_any", "eq_set"}),
}


def _count_and_depth(expr: TeamMemberPropertyRequirementExpr, depth: int) -> tuple[int, int]:
    if isinstance(expr, TeamMemberPropertyRequirementAtom):
        return 1, depth
    deepest = depth
    total = 1
    for child in expr.items:
        c, d = _count_and_depth(child, depth + 1)
        total += c
        deepest = max(deepest, d)
    return total, deepest


def _validate_atom_value(defn: TeamMemberPropertyDefinition, op: str, value: Any) -> None:
    ptype = defn.type
    options = list(defn.options or [])

    def bad(msg: str) -> None:
        raise TeamMemberPropertyRequirementError(msg)

    if ptype == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            bad("Property requirement atom value must be a number")
        return
    if ptype == "date":
        if not isinstance(value, str) or not _ISO_DATE_RE.match(value):
            bad("Property requirement atom value must be an ISO date string")
        try:
            date.fromisoformat(value)
        except ValueError:
            bad("Property requirement atom value must be a valid date")
        return
    if ptype == "text":
        if not isinstance(value, str):
            bad("Property requirement atom value must be a string")
        if len(value) > _TEXT_MAX_LEN:
            bad("Property requirement atom text value is too long")
        if op in {"eq", "neq"} and not value.strip():
            bad("Property requirement atom text value must be non-empty for this operator")
        if op == "contains" and not value:
            bad("Property requirement contains value must be non-empty")
        return
    if ptype == "select":
        if op == "one_of":
            if not isinstance(value, list) or not value:
                bad("one_of requires a non-empty list of option strings")
            for item in value:
                if not isinstance(item, str) or item not in options:
                    bad("one_of values must be allowed options")
            return
        if not isinstance(value, str) or value not in options:
            bad("select atom value must be an allowed option")
        return
    if ptype == "multi_select":
        if not isinstance(value, list) or not value:
            bad("multi_select atom requires a non-empty list of option strings")
        for item in value:
            if not isinstance(item, str) or item not in options:
                bad("multi_select atom values must be allowed options")
        return
    bad(f"Unsupported property type for requirement: {ptype}")


def _validate_atom(db: Session, atom: TeamMemberPropertyRequirementAtom, organization_id: int) -> None:
    defn = db.get(TeamMemberPropertyDefinition, atom.property_definition_id)
    if defn is None:
        raise TeamMemberPropertyRequirementError("Property definition not found for requirement atom")
    if defn.organization_id != organization_id:
        raise TeamMemberPropertyRequirementError("Property definition must belong to the same organization")
    if not defn.is_active:
        raise TeamMemberPropertyRequirementError("Property definition must be active for requirement atoms")
    allowed = _ATOM_OPS.get(defn.type)
    if allowed is None or atom.op not in allowed:
        raise TeamMemberPropertyRequirementError("Invalid operator for property type in requirement atom")
    _validate_atom_value(defn, atom.op, atom.value)


def validate_property_requirement_expr(
    db: Session,
    expr: TeamMemberPropertyRequirementExpr,
    *,
    organization_id: int,
) -> None:
    total, deepest = _count_and_depth(expr, 1)
    if total > _MAX_NODES:
        raise TeamMemberPropertyRequirementError("Property requirement expression exceeds maximum size")
    if deepest > _MAX_DEPTH:
        raise TeamMemberPropertyRequirementError("Property requirement expression is nested too deeply")

    stack: list[TeamMemberPropertyRequirementExpr] = [expr]
    while stack:
        current = stack.pop()
        if isinstance(current, TeamMemberPropertyRequirementAtom):
            _validate_atom(db, current, organization_id)
            continue
        for child in reversed(current.items):
            stack.append(child)


def load_property_definitions_map(db: Session, *, organization_id: int) -> dict[int, TeamMemberPropertyDefinition]:
    rows = db.scalars(
        select(TeamMemberPropertyDefinition).where(TeamMemberPropertyDefinition.organization_id == organization_id)
    ).all()
    return {row.id: row for row in rows}


def _as_float(x: Any) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return float(x)


def _as_date_str(x: Any) -> str | None:
    if not isinstance(x, str) or not _ISO_DATE_RE.match(x):
        return None
    try:
        date.fromisoformat(x)
    except ValueError:
        return None
    return x


def _as_str_list(x: Any) -> list[str] | None:
    if not isinstance(x, list):
        return None
    out: list[str] = []
    for item in x:
        if not isinstance(item, str):
            return None
        out.append(item)
    return out


def _evaluate_atom(
    atom: TeamMemberPropertyRequirementAtom,
    values: dict[int, Any],
    definitions: dict[int, TeamMemberPropertyDefinition],
) -> bool:
    op = atom.op
    val = atom.value
    pid = atom.property_definition_id
    defn = definitions.get(pid)
    if defn is None:
        return False
    if pid not in values:
        return False
    actual = values[pid]
    if actual is None or actual == "" or actual == []:
        return False

    ptype = defn.type

    if ptype == "number":
        left = _as_float(actual)
        right = _as_float(val)
        if left is None or right is None:
            return False
        if op == "eq":
            return left == right
        if op == "neq":
            return left != right
        if op == "gte":
            return left >= right
        if op == "lte":
            return left <= right
        return False

    if ptype == "date":
        av = _as_date_str(actual)
        vv = _as_date_str(val)
        if av is None or vv is None:
            return False
        da = date.fromisoformat(av)
        dv = date.fromisoformat(vv)
        if op == "eq":
            return da == dv
        if op == "before":
            return da < dv
        if op == "after":
            return da > dv
        return False

    if ptype == "text":
        if not isinstance(actual, str) or not isinstance(val, str):
            return False
        if op == "eq":
            return actual == val
        if op == "neq":
            return actual != val
        if op == "contains":
            return val in actual
        return False

    if ptype == "select":
        if not isinstance(actual, str):
            return False
        if op == "one_of":
            choices = _as_str_list(val)
            if choices is None:
                return False
            return actual in choices
        if not isinstance(val, str):
            return False
        if op == "eq":
            return actual == val
        if op == "neq":
            return actual != val
        return False

    if ptype == "multi_select":
        actual_list = _as_str_list(actual)
        need = _as_str_list(val)
        if actual_list is None or need is None:
            return False
        a_set = set(actual_list)
        v_set = set(need)
        if op == "contains_all":
            return v_set <= a_set
        if op == "contains_any":
            return bool(a_set & v_set)
        if op == "eq_set":
            return a_set == v_set
        return False

    return False


def evaluate_property_requirement_expr(
    expr: TeamMemberPropertyRequirementExpr,
    values: dict[int, Any],
    definitions: dict[int, TeamMemberPropertyDefinition],
) -> bool:
    if isinstance(expr, TeamMemberPropertyRequirementAll):
        return all(evaluate_property_requirement_expr(i, values, definitions) for i in expr.items)
    if isinstance(expr, TeamMemberPropertyRequirementAny):
        return any(evaluate_property_requirement_expr(i, values, definitions) for i in expr.items)
    if isinstance(expr, TeamMemberPropertyRequirementAtom):
        return _evaluate_atom(expr, values, definitions)
    return False


def _atom_is_missing(values: dict[int, Any], property_definition_id: int) -> bool:
    if property_definition_id not in values:
        return True
    actual = values[property_definition_id]
    return actual is None or actual == "" or actual == []


def _atom_violation_record(
    atom: TeamMemberPropertyRequirementAtom,
    values: dict[int, Any],
    definitions: dict[int, TeamMemberPropertyDefinition],
) -> dict[str, object]:
    pid = atom.property_definition_id
    defn = definitions.get(pid)
    name = defn.name if defn is not None else f"#{pid}"
    missing = _atom_is_missing(values, pid)
    actual: object | None = None if missing else values.get(pid)
    return {
        "property_definition_id": pid,
        "property_name": name,
        "op": atom.op,
        "required_value": atom.value,
        "actual_value": actual,
        "missing": missing,
    }


def collect_property_requirement_violations(
    expr: TeamMemberPropertyRequirementExpr,
    values: dict[int, Any],
    definitions: dict[int, TeamMemberPropertyDefinition],
    *,
    max_items: int = 8,
) -> list[dict[str, object]]:
    if evaluate_property_requirement_expr(expr, values, definitions):
        return []
    out: list[dict[str, object]] = []

    def extend_from(child: TeamMemberPropertyRequirementExpr) -> None:
        nonlocal out
        if len(out) >= max_items:
            return
        for row in collect_property_requirement_violations(
            child, values, definitions, max_items=max_items - len(out)
        ):
            out.append(row)
            if len(out) >= max_items:
                return

    if isinstance(expr, TeamMemberPropertyRequirementAtom):
        return [_atom_violation_record(expr, values, definitions)]
    if isinstance(expr, TeamMemberPropertyRequirementAll):
        for child in expr.items:
            if not evaluate_property_requirement_expr(child, values, definitions):
                extend_from(child)
        return out
    if isinstance(expr, TeamMemberPropertyRequirementAny):
        for child in expr.items:
            extend_from(child)
        return out
    return out
