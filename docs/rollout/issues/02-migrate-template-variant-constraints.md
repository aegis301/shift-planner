---
title: "R1: Migrate template and variant constraints onto the Rule protocol"
labels: rollout-r1, backend, architecture
---

## Context

`services/constraints.py` implements six constraint types inline in one long function. They
must become `Rule` implementations so the solver and the swap workflow can reuse them. This is
a behaviour-preserving refactor and must be provably so.

## Scope

Port to `backend/app/services/rules/shift_constraints.py`:

- `no_additional_same_day` → `ROSTER_CONSTRAINT_SAME_DAY`
- `min_rest_hours` → `ROSTER_CONSTRAINT_MIN_REST_HOURS`
- `unavailable_overlap_policy`, including the global `ROSTER_MATRIX_UNAVAILABLE_OVERLAP`
  behaviour in `services/unavailable_overlap.py`
- `max_assignments_per_month` → `ROSTER_CONSTRAINT_MAX_ASSIGNMENTS_PER_MONTH`
- `requires_coupled_shift` → `ROSTER_CONSTRAINT_COUPLED_SHIFT_REQUIRED`
- `team_member_property_requirement` → `ROSTER_CONSTRAINT_TEAM_MEMBER_PROPERTIES`

Each declares its own `lookback`. Keep the template-then-variant resolution order and the
existing `details` payload keys — the frontend reads them.

## Out of scope

Changing severities, codes or messages.

## Acceptance criteria

- [ ] Golden-file test: for a fixture month, the new rules produce a warning list identical to
      today's, including `details` keys and ordering.
- [ ] `requires_coupled_shift` evaluates a partner date in the following month instead of
      skipping it, with a test.
- [ ] `min_rest_hours` considers assignments outside the planning period, with a test using a
      24-hour duty on the last day of a month.
- [ ] Duplicate merging for `MAX_ASSIGNMENTS_PER_MONTH` and `COUPLED_SHIFT_REQUIRED` still
      produces one warning per member/template/limit.

## Dependencies

Blocked by #01.

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

Task: port shift template and variant constraints onto the `Rule` protocol, preserving
behaviour exactly, and fix the two documented month-boundary defects while doing so.

1. Capture current behaviour first. Write `backend/app/tests/test_constraints_golden.py`:
   build a fixture organization with several templates, variants and a full month of
   assignments, call the existing `evaluate_assignment_constraints` and
   `get_validation_warnings`, and snapshot the warnings (code, severity, team_member_id, date,
   details) to a JSON fixture.
2. Implement one `Rule` class per constraint type in
   `backend/app/services/rules/shift_constraints.py`, reading payloads through the existing
   `ShiftConstraint` schema. Do not change the JSON shape.
3. Declare `lookback` from each rule's own parameters: the configured hours for
   `min_rest_hours`, `abs(partner_day_offset)` days for `requires_coupled_shift`, the
   containing calendar month for `max_assignments_per_month`.
4. Fix the two boundary defects deliberately:
   - `requires_coupled_shift` currently returns early when the partner date falls outside the
     planning month. It must evaluate against `PlanState`, which spans the widened window.
   - `min_rest_hours` currently only sees the caller-supplied, month-scoped slot list.
   Add explicit regression tests for both, using a duty on the last day of a month.
5. Re-run the golden test. The only acceptable differences are those two fixes; update the
   fixture with a comment naming the fix.
6. Leave `services/constraints.py` as a thin delegation so no caller breaks; callers move
   in #04.
7. Update `AGENTS.md` and `CHANGELOG.md`. Run `ruff check app` and `pytest`.
```
