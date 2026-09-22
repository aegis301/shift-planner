from __future__ import annotations

from collections import defaultdict

from app.services.member_planning_patterns import evaluate_member_planning_patterns
from app.services.solver.model import SolverCpSatContext


class _VariantOnlySession:
    def get(self, model, ident):
        del model, ident
        return None


def _member_counts(ctx: SolverCpSatContext) -> dict[int, object]:
    counts: dict[int, list] = defaultdict(list)
    for (slot_id, member_id), var in ctx.variables.items():
        del slot_id
        counts[member_id].append(var)
    summed: dict[int, object] = {}
    n_slots = max(len(ctx.target_slots), 1)
    for member_id, vars_for_member in counts.items():
        total = ctx.new_int(f"count_{member_id}", 0, n_slots)
        ctx.cp_model.Add(total == sum(vars_for_member))
        summed[member_id] = total
    return summed


def _employment_percentage(state, member_id: int) -> int:
    on_date = state.start_date
    for period in state.employment_periods_by_member_id.get(member_id, ()):
        if period.start_date > on_date:
            continue
        if period.end_date is not None and period.end_date < on_date:
            continue
        return int(period.employment_percentage)
    return 100


def _fair_share(ctx: SolverCpSatContext) -> dict[int, int]:
    n_slots = len(ctx.target_slots)
    weights: dict[int, int] = {}
    for member_id in ctx.state.members_by_id:
        weights[member_id] = _employment_percentage(ctx.state, member_id)
    total_weight = sum(weights.values()) or 1
    shares: dict[int, int] = {}
    for member_id, weight in weights.items():
        shares[member_id] = (n_slots * weight + total_weight - 1) // total_weight
    return shares


def apply_objective(ctx: SolverCpSatContext) -> None:
    n_slots = len(ctx.target_slots)
    slack_terms = [ctx.slack[slot.id] for slot in ctx.target_slots if slot.id in ctx.slack]
    if slack_terms:
        ctx.add_linear_term(
            "unfilled",
            ctx.weights.unfilled * sum(slack_terms),
            lo=0,
            hi=ctx.weights.unfilled * n_slots,
        )

    counts = _member_counts(ctx)
    shares = _fair_share(ctx)
    overflow_terms = []
    for member_id, count in counts.items():
        overflow = ctx.new_int(f"ov_{member_id}", 0, n_slots)
        ctx.cp_model.Add(overflow >= count - shares.get(member_id, 0))
        overflow_terms.append(overflow)
    if overflow_terms:
        ctx.add_linear_term(
            "duty_count",
            ctx.weights.duty_count * sum(overflow_terms),
            lo=0,
            hi=ctx.weights.duty_count * n_slots * max(len(counts), 1),
        )

    fairness_terms = []
    max_fair = 0
    for member_id, count in counts.items():
        cost = max(0, int(ctx.fairness_duty_cost.get(member_id, 0)))
        if cost <= 0:
            continue
        scaled = ctx.new_int(f"fair_{member_id}", 0, cost * n_slots)
        ctx.cp_model.Add(scaled == count * cost)
        fairness_terms.append(scaled)
        max_fair += cost * n_slots
    if fairness_terms:
        ctx.add_linear_term(
            "fairness",
            ctx.weights.fairness * sum(fairness_terms),
            lo=0,
            hi=max(ctx.weights.fairness * max_fair, 0),
        )

    wish_vars = []
    wish_keys = {
        (intent.team_member_id, intent.cell_date, intent.shift_template_id)
        for intent in ctx.state.shift_intents
        if intent.kind == "wish"
    }
    for slot in ctx.target_slots:
        if slot.shift_template_id is None:
            continue
        for member_id in ctx.iter_candidates(slot.id):
            if (member_id, slot.slot_date, slot.shift_template_id) not in wish_keys:
                continue
            var = ctx.var(slot.id, member_id)
            if var is not None:
                wish_vars.append(var)
    if wish_vars:
        ctx.add_linear_term(
            "wish",
            -ctx.weights.wish * sum(wish_vars),
            lo=-ctx.weights.wish * len(wish_vars),
            hi=0,
        )

    avoid_vars = []
    session = _VariantOnlySession()
    for slot in ctx.target_slots:
        for member_id in ctx.iter_candidates(slot.id):
            patterns = ctx.state.patterns_by_member_id.get(member_id, ())
            if not patterns:
                continue
            findings = evaluate_member_planning_patterns(
                db=session,
                slot=slot,
                team_member_id=member_id,
                patterns=list(patterns),
                assignment_id=None,
            )
            if not any(item.details.get("pattern_type") == "avoid_time_window" for item in findings):
                continue
            var = ctx.var(slot.id, member_id)
            if var is not None:
                avoid_vars.append(var)
    if avoid_vars:
        ctx.add_linear_term(
            "avoid_time_window",
            ctx.weights.avoid_time_window * sum(avoid_vars),
            lo=0,
            hi=ctx.weights.avoid_time_window * len(avoid_vars),
        )

    if ctx.objective_terms:
        ctx.cp_model.Minimize(sum(ctx.objective_terms.values()))
