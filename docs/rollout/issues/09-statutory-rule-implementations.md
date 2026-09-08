---
title: "R1: Implement the statutory rules against PlanState"
labels: rollout-r1, backend, compliance
---

## Context

This is where the two R1 tracks meet: the rule layer (#01–#04), the time model (#05–#07) and the
rule sets (#08). These rules are the reason cross-month evaluation exists — a weekly average
over a 12-month reference period is meaningless inside a month silo.

## Scope

`backend/app/services/rules/statutory.py`, one `Rule` per type from #08:

- `max_daily_working_time` — statutory minutes per calendar day; the extended limit applies only
  when the day contains at least `extension_requires_duty_hours` of duty. `WORKTIME_MAX_DAILY`.
- `min_rest_period` — gap between consecutive assignments; a `call_out` inside a Rufbereitschaft
  interrupts the rest. Supports reduction with compensation inside the window; reports
  uncompensated reductions separately. `WORKTIME_MIN_REST`,
  `WORKTIME_REST_COMPENSATION_PENDING`.
- `rest_after_long_duty` — `WORKTIME_REST_AFTER_LONG_DUTY`.
- `weekly_average_cap` / `opt_out_weekly_cap` — rolling average over the reference period,
  resolving the applicable cap per date from #11. `WORKTIME_WEEKLY_AVERAGE`,
  `WORKTIME_WEEKLY_AVERAGE_OPT_OUT`.
- `max_consecutive_work_days` — `WORKTIME_CONSECUTIVE_DAYS`.
- `max_duties_per_period` — with the quarterly allowance. `WORKTIME_MAX_DUTIES`.
- `documentation_requirement` — `WORKTIME_DOCUMENTATION_GAP`.

Each declares a truthful `lookback`. A 12-month reference period declares 12 months, and
`build_plan_state` must handle that window efficiently by pre-aggregating prior months.

## Acceptance criteria

- [ ] A 24 h duty followed by a next-day shift is flagged under `WORKTIME_MIN_REST` across a
      month boundary.
- [ ] A rolling weekly average matches a hand-computed fixture to the minute.
- [ ] A recorded call-out during Rufbereitschaft restarts the rest calculation.
- [ ] `error`-severity rules block assignment at preflight; `warning` does not.
- [ ] Validating one month for 30 members with a 12-month reference period completes inside a
      documented budget, asserted by a benchmark test.

## Dependencies

Blocked by #04, #07, #08. #11 may land in parallel; until it does, resolve the base cap.

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

Task: implement the statutory working-time rules as `Rule` classes in
`backend/app/services/rules/statutory.py`.

1. Read `backend/app/services/rules/` (protocol, state, builder),
   `work_time_valuation.py`, and the rule-set schemas from #08.
2. All of these rules consume **statutory** minutes from `statutory_work_minutes` or the stored
   `TimeEntry.statutory_minutes`, never tariff credit. Mixing the two is the specific failure
   mode this design exists to prevent — add a comment saying so where it would be tempting.
3. Declare honest `lookback` values. For `weekly_average_cap` it is the reference period; do not
   silently truncate it.
4. Performance: a 12-month lookback must not load 12 months of roster slots per member per
   evaluation. Add a pre-aggregation path in `build_plan_state` returning per-member, per-day
   statutory minute totals for the lookback region outside the evaluated window, and use it for
   the averaging rules.
5. `min_rest_period` must treat a `call_out` entry inside a Rufbereitschaft slot as an
   interruption. Reduced rest is permitted only when compensated inside the configured window;
   emit a distinct pending code when it is not yet.
6. Register the rules in `services/rules/registry.py` so they resolve from the org's active rule
   set.
7. Tests in `backend/app/tests/test_statutory_rules.py`: one per rule, a cross-month rest test,
   a hand-computed rolling-average fixture, and a benchmark asserting a wall-clock ceiling for
   30 members over a month with a 12-month reference.
8. Update `README.md` (validation codes), `AGENTS.md`, `CHANGELOG.md`.
```
