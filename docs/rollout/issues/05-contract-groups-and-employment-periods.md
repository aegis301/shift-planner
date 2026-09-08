---
title: "R1: Add contract groups, dated employment periods and opening balances"
labels: rollout-r1, backend, schema, compliance
---

## Context

`main` has no notion of a contract. `TeamMember.employment_percentage` is a single integer with
no history, there are no weekly hours, no vacation entitlement, no mapping from wishes-matrix
day statuses to absence kinds, and no opening balance for members migrated from a previous
system. Every statutory rule and every fairness account needs all of it.

This is the foundation of R1's second track. Build it fresh; do not revive
`feat/ai-assistant`.

## Scope

**`ContractGroup`** (org-scoped, named, ordered, active flag):
- `weekly_hours_at_100`, `vacation_days_at_100`
- `regular_week_pattern`: weekday + start/end times
- `category_rules`: per shift-template category (`bereitschaftsdienst`, `rufdienst`,
  `spaetdienst`, `other`) — `counts_toward_contract`, `credit_mode`
  (`duration` / `factor` / `none`), `credit_factor`, `holiday_credit_bonus` (percentage points),
  `statutory_factor`, `call_outs_count_as_work`
- `status_mappings`: day-status `code` → `absence_kind` (`vacation` / `sick` / `other` / `none`),
  `consumes_vacation`, `counts_as_work_day`

**`EmploymentPeriod`**: `team_member_id`, `contract_group_id`, `employment_percentage`,
`start_date`, `end_date | null`. Non-overlapping per member, 400 on overlap — mirror the
existing dated-membership rules in `services/shift_groups.py`. This becomes the source of truth
for employment percentage; `TeamMember.employment_percentage` is migrated into an initial
open-ended period and removed.

**`TimeAccountOpening`**: one per member — `as_of_date`, `overtime_minutes`,
`vacation_days_remaining`, `sick_days_used_ytd`.

Naming: `ContractGroup`, not `WorkerGroup`, to avoid a fourth "group" colliding with
`ShiftGroup`, `TeamMemberShiftGroup` and `UserShiftGroup`. See open decision 1 in the plan.

REST CRUD (admin write, planning-user read), MCP resources plus guarded tools, and admin UI
under `/organization/team/`.

## Out of scope

The time ledger itself (#06), valuation (#07), payroll, vacation entitlement law.

## Acceptance criteria

- [ ] Overlapping employment periods for one member are rejected with 400.
- [ ] `TeamMember.employment_percentage` is gone; the migration creates an equivalent
      open-ended period for every existing member, and a test asserts values are preserved.
- [ ] `employment_percentage_on(member, date)` resolves through the dated periods.
- [ ] Category rules validate: `credit_factor` present exactly when `credit_mode == "factor"`,
      factors within 0–1, `holiday_credit_bonus` within 0–100.
- [ ] Deleting a contract group referenced by an employment period is refused.
- [ ] MCP mirrors REST with admin-token-guarded writes.
- [ ] DE and EN strings for the admin UI.

## Dependencies

None — parallel to the engine track. Should follow #00 so nobody reaches for the old model.

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

Task: build the contract and employment model from scratch on `main`.

1. Model `ContractGroup`, `EmploymentPeriod` and `TimeAccountOpening` in
   `backend/app/models/entities.py` exactly as described in the issue body. Use `Numeric` for
   hours and day counts, not float columns.
2. Follow the existing dated-membership conventions in
   `backend/app/services/shift_groups.py` (`TeamMemberShiftGroup`): non-overlapping periods,
   open-ended end dates, 400 on overlap, and a resolver for "active on date".
3. Typed payloads for `category_rules` and `status_mappings` go in
   `backend/app/schemas/domain.py` as Pydantic models, validated the way `ShiftConstraint` is.
   Include `statutory_factor` from the start — it is independent of `credit_factor` and is the
   whole point of the design (see section 3 of the rollout plan). Do not add it later.
4. Migration: create the tables, seed one default contract group per organization, create an
   open-ended `EmploymentPeriod` per existing `TeamMember` carrying that member's current
   `employment_percentage`, then drop the `team_members.employment_percentage` column. Write a
   test that seeds members before the migration and asserts percentages survive it.
5. Grep for every reader of `employment_percentage` (workload table, roster picker modal,
   dashboards, exports, MCP payloads) and route them through
   `employment_percentage_on(member, date)`. There must be no remaining direct column access.
6. Services `contract_groups.py` and `employment_periods.py`, REST routers registered in
   `api/v1/router.py`, MCP resources plus guarded create/update/delete tools.
7. Admin UI under `/organization/team/` for contract groups and, in the staff directory row
   detail, the member's employment periods and opening balance. DE and EN strings.
8. Tests: overlap rejection, date resolution, migration fidelity, referenced-group deletion,
   payload validation, authorization.
9. Update `README.md`, `AGENTS.md`, `CHANGELOG.md`, `PLAN.md`.
```
