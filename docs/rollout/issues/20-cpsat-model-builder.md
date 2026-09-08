---
title: "R3: Build the CP-SAT model from the rule layer"
labels: rollout-r3, backend, solver
---

## Context

The rule layer already encodes everything the solver needs. The work is translating it into a
CP-SAT model rather than restating the rules a second time — a second statement is the thing most
likely to produce solver output that validation then rejects.

## Scope

- Add OR-Tools CP-SAT. Decision variables: one boolean per (roster slot, eligible member).
- Implement `to_cpsat` on the rules that linearize:
  - eligibility masks: property requirements, member patterns, period roster membership,
    blocking day statuses, `unavailable_overlap_policy`
  - `min_rest_hours` and `min_rest_period`: pairwise exclusions
  - `max_assignments_per_month`, `max_consecutive_work_days`, `max_duties_per_period`,
    `no_additional_same_day`, `ROSTER_CONSECUTIVE_WEEKENDS`: linear sums
  - `requires_coupled_shift`: implication
  - `max_daily_working_time`, `weekly_average_cap`: weighted linear sums over statutory minutes
- Rules without `to_cpsat` are evaluated **after** solving and written to `post_check_findings`.
  Never dropped silently.
- Objective, weighted and configurable per organization: unfilled slots (dominant) → no-go
  violations → fairness deviation (#17) → unmet wishes → `avoid_time_window` hints.
- Infeasibility: never an opaque failure. Relax to a partial assignment, report unfilled slots
  and the binding constraints.

## Acceptance criteria

- [ ] Every assignment a run produces passes the existing preflight unchanged — property test
      over generated fixtures.
- [ ] A deliberately infeasible month returns a partial assignment plus binding constraints.
- [ ] Objective components are reported individually.
- [ ] Rules lacking `to_cpsat` appear in `post_check_findings` when violated.
- [ ] Rules claiming CP-SAT support never appear in `post_check_findings` — asserted by test.
- [ ] A representative month (30 days, 20 members, 3 templates) solves within the default budget,
      recorded as a benchmark.

## Dependencies

Blocked by #19, #09, #17.

## Implementation prompt

```text
You are working in the `aegis301/shift-planner` repository, on top of `main`.
Ignore the abandoned `feat/ai-assistant` branch entirely — nothing in this task depends on it,
and no code from it should be revived.

Read `AGENTS.md` first and follow it strictly. The rules that matter most here:
- Business logic goes in typed service functions under `backend/app/services/`, never in
  route handlers or React components.
- Every capability must be reachable from the web UI, the REST API **and** MCP
  (`mcp-server/mcp_app/server.py`). Mutating MCP tools require `MCP_ADMIN_TOKEN`.
- Every user-visible string exists in both the German and English dictionaries in
  `frontend/lib/i18n.ts`; the dictionaries are key-parity checked in CI.
- Update `README.md`, `CHANGELOG.md`, `PLAN.md` and `AGENTS.md` in the same change when
  behaviour, setup, API shape, MCP capability or roadmap changes.
- Backend changes ship with pytest coverage; run `ruff check app` and `pytest` in
  `backend/`, and `npm run lint` + `npm run typecheck` in `frontend/`.
- Schema changes ship with an Alembic migration. Forward-only; do not add compatibility
  branches for old shapes.

The full design context is `docs/rollout/ROLLOUT.md`. Read it before starting.

Task: implement the CP-SAT roster model, driven by the rule layer.

1. Add `ortools` to `backend/pyproject.toml`. Note the container image size impact in the PR.
2. Create `backend/app/services/solver/`: `model.py`, `objective.py`, `solve.py` (the entry
   point the worker from #19 calls).
3. Variables: one boolean per (slot, member) pair, created only for members the eligibility
   rules admit. Compute eligibility from the rules; do not re-derive it.
4. Implement `to_cpsat` on each rule listed above **in the rule's own module, next to its
   `evaluate`**. Keeping both in one class is the point: it is what stops the model and the
   validator from drifting apart.
5. After solving, run the full rule registry over the produced `PlanState` and write findings to
   `post_check_findings`. If a rule with `to_cpsat` reports a violation there, the translation is
   wrong — add a test asserting that set is empty for CP-SAT-supported rules.
6. Objective weights come from organization configuration with documented defaults. Report each
   component's contribution separately.
7. Infeasibility: model unfilled slots as a heavily penalized slack variable rather than a hard
   requirement, so the solver always returns something, and report which constraints bound the
   solution.
8. Tests: property test that every produced assignment passes preflight; an infeasible fixture;
   per-component objective reporting; the empty-post-check assertion; a benchmark for
   30 days x 20 members x 3 templates.
9. Update `README.md`, `AGENTS.md`, `CHANGELOG.md`, `PLAN.md`, `BRAINSTORM.md`.
```
