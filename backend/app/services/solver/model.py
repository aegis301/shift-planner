from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date

from ortools.sat.python import cp_model
from sqlalchemy.orm import Session

from app.models import PlanningPeriod, RosterSlot
from app.schemas.domain import SolverObjectiveWeights
from app.services.planning_period_rosters import team_member_ids_for_period_shift_group
from app.services.rules.registry import resolve_active_rules
from app.services.rules.state import PlanState
from app.services.shift_groups import shift_group_ids_for_template, team_member_may_cover_template

SERVICE_MASK_PERIOD_ROSTER = "period_roster"
SERVICE_MASK_COVER_TEMPLATE = "cover_template"


class SolverCpSatContext:
    def __init__(
        self,
        *,
        state: PlanState,
        target_slots: Sequence[RosterSlot],
        weights: SolverObjectiveWeights,
        fixed_assignments: dict[int, int],
        constant_assignments: dict[int, int],
        eligible_by_slot: dict[int, set[int]],
        fairness_duty_cost: dict[int, int],
    ) -> None:
        self.phase = "mask"
        self.state = state
        self.target_slots = list(target_slots)
        self.target_slot_ids = {slot.id for slot in self.target_slots}
        self.slots_by_id = {slot.id: slot for slot in self.target_slots}
        self.weights = weights
        self.fixed_assignments = dict(fixed_assignments)
        self.constant_assignments = dict(constant_assignments)
        self.fairness_duty_cost = dict(fairness_duty_cost)
        self.cp_model = cp_model.CpModel()
        self.variables: dict[tuple[int, int], cp_model.IntVar] = {}
        self.slack: dict[int, cp_model.IntVar] = {}
        self.exclusion_codes: dict[tuple[int, int], list[str]] = {}
        self.eligible_by_slot = {slot_id: set(member_ids) for slot_id, member_ids in eligible_by_slot.items()}
        self.binding_codes: dict[int, list[str]] = {}
        self.objective_terms: dict[str, cp_model.IntVar] = {}
        self._bool_index = 0

    def new_bool(self, prefix: str) -> cp_model.IntVar:
        self._bool_index += 1
        return self.cp_model.NewBoolVar(f"{prefix}_{self._bool_index}")

    def new_int(self, prefix: str, lo: int, hi: int) -> cp_model.IntVar:
        self._bool_index += 1
        return self.cp_model.NewIntVar(lo, hi, f"{prefix}_{self._bool_index}")

    def iter_candidates(self, slot_id: int) -> tuple[int, ...]:
        return tuple(sorted(self.eligible_by_slot.get(slot_id, ())))

    def exclude(self, slot_id: int, member_id: int, code: str) -> None:
        if slot_id in self.fixed_assignments and self.fixed_assignments[slot_id] == member_id:
            return
        self.exclusion_codes.setdefault((slot_id, member_id), []).append(code)
        members = self.eligible_by_slot.get(slot_id)
        if members is not None:
            members.discard(member_id)

    def var(self, slot_id: int, member_id: int) -> cp_model.IntVar | None:
        return self.variables.get((slot_id, member_id))

    def assigned_expr(self, slot_id: int, member_id: int) -> cp_model.IntVar | int | None:
        existing = self.var(slot_id, member_id)
        if existing is not None:
            return existing
        if self.constant_assignments.get(slot_id) == member_id:
            return 1
        return None

    def add_at_most_one(self, terms: Sequence[object]) -> None:
        present = [term for term in terms if term is not None]
        if len(present) >= 2:
            self.cp_model.Add(sum(present) <= 1)

    def add_implication(self, premise, conclusion) -> None:
        if premise is None:
            return
        if conclusion is None:
            if type(premise) is int:
                return
            self.cp_model.Add(premise == 0)
            return
        if type(conclusion) is int:
            return
        if type(premise) is int:
            self.cp_model.Add(conclusion == 1)
            return
        self.cp_model.Add(conclusion == 1).OnlyEnforceIf(premise)

    def add_penalty(self, component: str, var: cp_model.IntVar, weight: int) -> None:
        if weight <= 0:
            return
        current = self.objective_terms.get(component)
        scaled = self.new_int(f"pen_{component}", 0, 2_000_000_000)
        self.cp_model.Add(scaled == var * weight)
        if current is None:
            self.objective_terms[component] = scaled
            return
        total = self.new_int(f"obj_{component}", 0, 2_000_000_000)
        self.cp_model.Add(total == current + scaled)
        self.objective_terms[component] = total

    def add_linear_term(self, component: str, expr, *, lo: int, hi: int) -> None:
        term = self.new_int(f"obj_{component}", lo, hi)
        self.cp_model.Add(term == expr)
        self.objective_terms[component] = term

    def apply_severity(
        self,
        severity: str,
        *,
        hard,
        penalty_component: str | None = None,
        penalty_var: cp_model.IntVar | None = None,
        penalty_weight: int | None = None,
    ) -> None:
        if severity == "error":
            hard()
            return
        if severity == "warning" and penalty_var is not None and penalty_component is not None:
            weight = self.weights.warning if penalty_weight is None else penalty_weight
            self.add_penalty(penalty_component, penalty_var, weight)


def _template_group_ids(db: Session, slots: Sequence[RosterSlot]) -> dict[int, set[int]]:
    mapping: dict[int, set[int]] = {}
    template_ids = {slot.shift_template_id for slot in slots if slot.shift_template_id is not None}
    for template_id in template_ids:
        mapping[template_id] = shift_group_ids_for_template(db, template_id)
    return mapping


def _period_roster_members(
    db: Session,
    slot: RosterSlot,
    template_groups: dict[int, set[int]],
) -> set[int] | None:
    groups = template_groups.get(slot.shift_template_id or -1, set())
    if not groups:
        return None
    members: set[int] = set()
    for group_id in groups:
        members.update(
            team_member_ids_for_period_shift_group(
                db,
                planning_period_id=slot.planning_period_id,
                shift_group_id=group_id,
            )
        )
    return members


def service_eligible_by_slot(
    db: Session,
    *,
    state: PlanState,
    target_slots: Sequence[RosterSlot],
) -> tuple[dict[int, set[int]], dict[tuple[int, int], list[str]]]:
    template_groups = _template_group_ids(db, target_slots)
    cover_ok: dict[tuple[int, int | None], bool] = {}
    eligible: dict[int, set[int]] = {}
    codes: dict[tuple[int, int], list[str]] = {}
    member_ids = sorted(state.members_by_id)
    for slot in target_slots:
        roster_ids = _period_roster_members(db, slot, template_groups)
        accepted: set[int] = set()
        for member_id in member_ids:
            reasons: list[str] = []
            if roster_ids is not None and member_id not in roster_ids:
                reasons.append(SERVICE_MASK_PERIOD_ROSTER)
            cover_key = (member_id, slot.shift_template_id)
            if cover_key not in cover_ok:
                cover_ok[cover_key] = team_member_may_cover_template(
                    db,
                    team_member_id=member_id,
                    shift_template_id=slot.shift_template_id,
                )
            if not cover_ok[cover_key]:
                reasons.append(SERVICE_MASK_COVER_TEMPLATE)
            if reasons:
                codes[(slot.id, member_id)] = reasons
                continue
            accepted.add(member_id)
        eligible[slot.id] = accepted
    return eligible, codes


def _call_to_cpsat(rules: Iterable[object], ctx: SolverCpSatContext) -> None:
    for rule in rules:
        to_cpsat = getattr(rule, "to_cpsat", None)
        if not callable(to_cpsat):
            continue
        to_cpsat(ctx, ctx.variables, ctx.state)


def create_decision_variables(ctx: SolverCpSatContext) -> None:
    for slot in ctx.target_slots:
        fixed_member = ctx.fixed_assignments.get(slot.id)
        if fixed_member is not None:
            var = ctx.cp_model.NewBoolVar(f"x_{slot.id}_{fixed_member}")
            ctx.cp_model.Add(var == 1)
            ctx.variables[(slot.id, fixed_member)] = var
            ctx.slack[slot.id] = ctx.cp_model.NewConstant(0)
            continue
        eligible = ctx.iter_candidates(slot.id)
        member_vars: list[cp_model.IntVar] = []
        for member_id in eligible:
            var = ctx.cp_model.NewBoolVar(f"x_{slot.id}_{member_id}")
            ctx.variables[(slot.id, member_id)] = var
            member_vars.append(var)
        slack = ctx.cp_model.NewBoolVar(f"u_{slot.id}")
        ctx.slack[slot.id] = slack
        ctx.cp_model.Add(sum(member_vars) + slack == 1)
        codes: list[str] = []
        seen: set[str] = set()
        for member_id in ctx.state.members_by_id:
            for code in ctx.exclusion_codes.get((slot.id, member_id), ()):
                if code in seen:
                    continue
                seen.add(code)
                codes.append(code)
        ctx.binding_codes[slot.id] = codes


def rule_claims_cpsat(rule: object) -> bool:
    return bool(getattr(rule, "cpsat_supported", False))


def cpsat_supported_codes(rules: Iterable[object]) -> set[str]:
    return {str(rule.code) for rule in rules if rule_claims_cpsat(rule)}


def build_solver_context(
    db: Session,
    *,
    state: PlanState,
    target_slots: Sequence[RosterSlot],
    weights: SolverObjectiveWeights,
    overwrite_existing: bool,
    fairness_duty_cost: dict[int, int] | None = None,
) -> SolverCpSatContext:
    target_ids = {slot.id for slot in target_slots}
    fixed: dict[int, int] = {}
    if not overwrite_existing:
        for slot in target_slots:
            existing = state.assignments_by_slot_id.get(slot.id)
            if existing is not None:
                fixed[slot.id] = existing.team_member_id
    constants: dict[int, int] = {}
    for assignment in state.assignments_by_id.values():
        slot = assignment.roster_slot
        if slot is None:
            continue
        if slot.id in target_ids and slot.id not in fixed:
            continue
        constants[slot.id] = assignment.team_member_id
    eligible, service_codes = service_eligible_by_slot(db, state=state, target_slots=target_slots)
    ctx = SolverCpSatContext(
        state=state,
        target_slots=target_slots,
        weights=weights,
        fixed_assignments=fixed,
        constant_assignments=constants,
        eligible_by_slot=eligible,
        fairness_duty_cost=fairness_duty_cost or {},
    )
    ctx.exclusion_codes.update(service_codes)
    rules = resolve_active_rules(state.organization_id, state.start_date, state.end_date, db=db)
    ctx.phase = "mask"
    _call_to_cpsat(rules, ctx)
    create_decision_variables(ctx)
    ctx.phase = "constrain"
    _call_to_cpsat(rules, ctx)
    return ctx


def eligible_members_for_slots(
    db: Session,
    *,
    state: PlanState,
    target_slots: Sequence[RosterSlot],
) -> dict[int, set[int]]:
    eligible, service_codes = service_eligible_by_slot(db, state=state, target_slots=target_slots)
    ctx = SolverCpSatContext(
        state=state,
        target_slots=target_slots,
        weights=SolverObjectiveWeights(),
        fixed_assignments={},
        constant_assignments={},
        eligible_by_slot=eligible,
        fairness_duty_cost={},
    )
    ctx.exclusion_codes.update(service_codes)
    rules = resolve_active_rules(state.organization_id, state.start_date, state.end_date, db=db)
    ctx.phase = "mask"
    _call_to_cpsat(rules, ctx)
    return {slot_id: set(member_ids) for slot_id, member_ids in ctx.eligible_by_slot.items()}


def planning_window(period: PlanningPeriod) -> tuple[date, date]:
    from calendar import monthrange

    last = monthrange(period.year, period.month)[1]
    return date(period.year, period.month, 1), date(period.year, period.month, last)
