---
title: "R2: Rolling 12-month fairness accounts and expected-share targets"
labels: rollout-r2, backend
---

## Context

`build_member_workload_rows` counts shifts and weekend/holiday touches for one month. There is
no target, no deviation and no memory across months, so systematic unfairness over a year is
invisible.

## Scope

`backend/app/services/fairness.py`, per member and dimension over a rolling window (default 12
months, configurable per organization):

- **actual**: duties, weekend/holiday duties, night duties, statutory hours
- **expected share**: derived from `EmploymentPeriod.employment_percentage`, the contract
  group's `weekly_hours_at_100` and the period roster size **for each month in the window** — a
  member present for 4 of 12 months is measured against 4 months of expectation
- **deviation**: actual minus expected, absolute and normalized

Opening balances from `TimeAccountOpening`. REST endpoint and MCP read resource.

## Acceptance criteria

- [ ] A member at 50 % employment carrying twice the expected weekend share over 12 months ranks
      as most over-served, independently of the current month.
- [ ] A member who joined three months ago is measured against three months of expectation.
- [ ] Opening balances shift the account by exactly their value.
- [ ] Dimensions are configurable per organization; adding one requires no schema change.
- [ ] Computing accounts for 30 members over 12 months stays inside a documented budget.

## Dependencies

Blocked by #04, #07.

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

Task: implement rolling fairness accounts with expected-share targets.

1. Read `backend/app/services/workload.py` — the descriptive version this replaces — and the
   rolling-window handling added in #09.
2. Create `backend/app/services/fairness.py`. Compute expectation **per month** in the window
   and sum, never as one window-level figure: roster size and employment percentage both change
   over a year, and a window-level average hides exactly the unfairness this is meant to expose.
3. Use `EmploymentPeriod` for the percentage — `TeamMember.employment_percentage` no longer
   exists after #05.
4. Measure members only over months in which they were on that shift group's period roster
   (`planning_period_shift_group_members`), so joiners and leavers are handled by construction.
5. Make dimensions data-driven: a list of dimension definitions per organization, each naming a
   metric and a filter. Adding one must not require a migration.
6. Reuse the pre-aggregation path from #09 rather than loading a year of slots.
7. Tests: the part-time over-service case, the mid-window joiner, opening balance application,
   and a performance test for 30 members over 12 months.
8. Update `README.md`, `AGENTS.md`, `CHANGELOG.md`, `PLAN.md`.
```
