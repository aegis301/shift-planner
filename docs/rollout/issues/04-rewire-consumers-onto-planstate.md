---
title: "R1: Rewire preflight, validation and workload onto PlanState"
labels: rollout-r1, backend, architecture
---

## Context

With rules ported (#02, #03), the three existing consumers must use the new layer, and the
month-scoped call sites must be replaced by windows. This is the change that makes the
boundary fixes reach users.

## Scope

- Assignment preflight in `services/roster_matrix.py` builds a `PlanState` for a window around
  the target slot instead of a month-scoped assignment list, blocking on `error` as today.
- `GET /api/v1/validation/{planning_period_id}` builds a `PlanState` for the month plus
  lookback and runs the registry.
- `services/workload.py` reads assignments from `PlanState`.
- Delete the inline evaluation and month arithmetic from `services/constraints.py`.
- Keep `unavailable_overlap.py` behaviour, moved behind its rule.

## Acceptance criteria

- [ ] `constraints.py` contains no month arithmetic.
- [ ] Assigning a shift that violates rest against an assignment in the adjacent month is
      blocked at preflight with `ROSTER_CONSTRAINT_MIN_REST_HOURS`.
- [ ] `GET /api/v1/validation/{id}` response shape unchanged for in-month cases.
- [ ] MCP `get_validation_warnings` returns the same payload as REST.
- [ ] Existing tests pass unmodified, except where a test encodes the old boundary behaviour —
      those are updated with a comment naming the fix.

## Dependencies

Blocked by #02 and #03.

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

Task: move assignment preflight, the validation endpoint and workload onto the rule layer, and
delete the month-scoped evaluation paths.

1. Read `backend/app/services/roster_matrix.py` (assignment upsert and preflight),
   `backend/app/api/v1/planning.py` (validation route) and `backend/app/services/workload.py`.
2. Replace each month-scoped assignment query with `build_plan_state(...)` over the appropriate
   window: for preflight the slot date +/- the maximum rule lookback; for validation the month
   plus lookback.
3. Preserve the API response shape exactly. The frontend reads `details` keys in
   `RosterMatrixEditor.tsx` and the planning conflict summary — check both before touching the
   payload.
4. Remove the evaluation body and month arithmetic from `services/constraints.py`.
5. Keep MCP parity: `get_validation_warnings` must call the same service function as REST.
6. Run the full backend suite. Where a test encodes the old month-boundary behaviour, update it
   with a comment naming the issue that changed it. Do not weaken an assertion to make a test
   pass.
7. Add a test that assigns across a month boundary through REST and asserts a 400 with the
   rest-period violation.
8. Update `README.md` (validation section), `AGENTS.md`, `CHANGELOG.md`.
```
