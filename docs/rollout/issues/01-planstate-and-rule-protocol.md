---
title: "R1: Introduce PlanState and the Rule protocol"
labels: rollout-r1, backend, architecture
---

## Context

Rule evaluation lives in three disconnected places: `services/constraints.py` (one candidate
assignment), `services/validation.py` (one planning month) and `services/workload.py` (counts
only). None can answer "is this set of assignments legal over this date window", which is what
the solver, the swap workflow and every statutory rule need.

This issue creates the shared layer. It adds no user-visible behaviour.

## Scope

Create `backend/app/services/rules/`:

- `state.py` — `PlanState`, an immutable snapshot built from a **date window**
  (`start_date`, `end_date`), never a `planning_period_id`. Carries members, roster slots with
  resolved template/variant metadata, assignments, planning cells and day-status definitions,
  member planning patterns and member property values. Time entries and employment periods are
  added by #06 once they exist; leave typed placeholders.
- `protocol.py` — the `Rule` protocol: `code`, `severity`, `lookback: timedelta`,
  `evaluate(state) -> list[ValidationWarning]`, and an optional `to_cpsat(...)` that is part of
  the contract but unused here.
- `registry.py` — resolves the active rule instances for an organization and window.
- `builder.py` — `build_plan_state(db, *, organization_id, start_date, end_date, shift_group_id=None)`,
  widening the loaded window by `max(rule.lookback)`.

Keep `ValidationWarning` as the output type so consumers and the frontend do not change shape.

## Out of scope

Migrating existing rules (#02, #03), any behaviour change, any UI.

## Acceptance criteria

- [ ] `build_plan_state` returns assignments from two adjacent planning periods when the window
      spans a month boundary.
- [ ] Lookback widening is driven by registered rules, not hard-coded.
- [ ] Bounded query count: a test asserts no N+1 on slots, assignments and property values for
      a 31-day window with 20 members.
- [ ] Unit tests cover an empty window, a single-day window and a cross-year window.
- [ ] No existing module imports the new package yet.

## Dependencies

None.

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

Task: create the shared rule-evaluation layer described in section 2 of
`docs/rollout/ROLLOUT.md`. Additive only; no behaviour changes.

1. Read `backend/app/services/constraints.py`, `validation.py` and `workload.py` for the
   current evaluation inputs, and `ValidationWarning` in `backend/app/schemas/domain.py`.
2. Create `backend/app/services/rules/` with `state.py`, `protocol.py`, `registry.py` and
   `builder.py` as specified above.
3. `PlanState` is a frozen dataclass. Load everything in `build_plan_state` with explicit
   eager loading; rules never lazy-load. Index collections by the keys rules use (member id,
   date, slot id) so rule code does no scanning.
4. Reserve typed, empty fields for `time_entries` and `employment_periods`; #06 populates them.
   Do not stub them as `None` — use empty collections so rules can be written against them.
5. Compute window widening from registered rules' `lookback`. The registry is empty at this
   point, so write the mechanism and test it by injecting a fake rule with a 40-day lookback.
6. Add `backend/app/tests/test_plan_state.py`: cross-month loading, lookback widening, empty
   window, and a query-count assertion using SQLAlchemy event listeners.
7. Wire no consumers in this change.
8. Add a short `AGENTS.md` subsection describing the rule layer and the rule that new rules go
   there rather than into `constraints.py`.
9. Run `ruff check app` and `pytest`.
```
