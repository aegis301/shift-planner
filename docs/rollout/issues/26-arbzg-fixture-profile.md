---
title: "R3: Add an ArbZG fixture profile that fires rest, weekly-average and documentation rules"
labels: rollout-r3, backend, solver, testing
---

## Context

The spike found that the TdL fixture from #24 never fires `min_rest_period`,
`rest_after_long_duty`, `weekly_average_cap` or `documentation_requirement`. The only relational
hard constraint it exercised was `WORKTIME_MAX_DAILY`.

That means #20 cannot encode those rules as CP-SAT constraints without shipping them untested —
which is why they are explicitly deferred there. This issue builds the data that unblocks them.

## Scope

A fourth profile in `backend/app/services/solver_fixture.py`, `arbzg`:

- Active rule set is the **`ArbZG-Grundmodell`** preset (#10), not TdL: 11 h rest reducible to
  10 h with compensation inside one month, 48 h weekly average over 6 months, daily 8 h
  extendable to 10 h, documentation duty above 8 h/day.
- Slot density tight enough that **rest periods actually bind**: consecutive-day duties with
  short gaps, at least one 24 h duty immediately followed by a next-day early shift, and at
  least one pair that crosses a month boundary.
- Enough history that the rolling 48 h average sits **close to the cap** for several members —
  some just under, at least one over. A comfortable average proves nothing.
- At least one member-day above the documentation threshold with no corresponding record, so
  `WORKTIME_DOCUMENTATION_GAP` fires.
- Same determinism contract as the other profiles: `--rng-seed` drives everything.

## Acceptance criteria

- [ ] Running validation over the `arbzg` target month produces at least one finding for each
      of `WORKTIME_MIN_REST`, `WORKTIME_REST_AFTER_LONG_DUTY`, `WORKTIME_WEEKLY_AVERAGE` and
      `WORKTIME_DOCUMENTATION_GAP` — asserted by test, one assertion per code.
- [ ] At least one rest violation spans a month boundary.
- [ ] At least one member is over the weekly average cap and at least one is just under.
- [ ] Reproducible: two runs with the same `--rng-seed` produce identical data.
- [ ] Documented in `README.md` alongside the other three profiles.

## Dependencies

Blocked by #24 and #28 (this profile seeds more than one org in tests, which the legacy index
blocks). Unblocks the tier B encodings deferred in #20.

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

Task: add an `arbzg` profile to the solver fixture so the statutory rest, weekly-average and
documentation rules can be encoded and tested.

1. Read `docs/rollout/solver-spike-findings.md` (finding 9) and
   `backend/app/services/solver_fixture.py`.
2. Add the profile as specified in the issue body. The point is not "more data" — it is that
   each of the four named rules must actually fire. Build the data backwards from that: decide
   which member-days should violate which rule, then generate the duties that cause it.
3. Use the `ArbZG-Grundmodell` preset, not TdL. The two differ in exactly the numbers this
   profile is meant to exercise.
4. Keep the determinism contract: one seeded `random.Random`, no module-level `random`, no
   reliance on set or dict iteration order.
5. Tests in `backend/app/tests/test_solver_fixture.py`: one assertion per validation code, plus
   the cross-month rest case and the over/under weekly-average pair.
6. Update `README.md`, `CHANGELOG.md`.
```
