---
title: "R1: Implement dual valuation — statutory working time and tariff credit"
labels: rollout-r1, backend, compliance
---

## Context

The most common modelling error in this domain is treating "how much this duty counts" as one
number. It is two:

| Duty type | Statutory working time | Tariff credit |
|---|---|---|
| Bereitschaftsdienst | 100 % of duty time | TV-Ärzte TdL: 60 % (Stufe I), 95 % (Stufe II), +25 pp on public holidays |
| Rufbereitschaft | 0 % + 100 % of each call-out | per tariff |
| Regular / Spätdienst | 100 % | 100 % |

A single figure produces either a plausible time account with a wrong statutory average, or the
reverse. Both numbers come from the same inputs and must be computed by the same module.

## Scope

`backend/app/services/work_time_valuation.py`, pure functions with no database access:

- `tariff_credit_minutes(*, slot, contract_group, template, day_class, episodes)`
- `statutory_work_minutes(*, slot, contract_group, template, day_class, episodes)`

Resolution order: template override wins over contract-group category rule. A
Bereitschaftsdienst-Stufe attaches to a concrete duty, so `ShiftTemplate` carries an optional
valuation override with the same payload shape as a category rule.

Wire `TimeEntry` to store both `statutory_minutes` and `credited_minutes` at derivation time, so
historical entries keep the valuation in force when they were derived.

## Acceptance criteria

- [ ] A 24-hour Bereitschaftsdienst on a weekday under Stufe I yields 1440 statutory minutes and
      864 credited minutes.
- [ ] The same duty on an NRW public holiday yields 1224 credited minutes (60 % + 25 pp).
- [ ] A Rufbereitschaft duty with two call-out episodes yields 0 statutory minutes plus the
      episode durations, and tariff credit per its rule.
- [ ] A template override beats the contract-group rule, with a test.
- [ ] Changing a contract group's factors does not retroactively alter stored entries.
- [ ] Both functions are pure: a test calls them with plain fixtures and no session.

## Dependencies

Blocked by #05 and #06.

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

Task: implement dual valuation of duty time per section 3 of `docs/rollout/ROLLOUT.md`.

1. Create `backend/app/services/work_time_valuation.py` with the two functions above. Keep them
   pure — resolved inputs in, minutes out, no session, no queries. This is what makes them
   usable from the solver's inner loop later.
2. Use `services/holidays.py` `classify_day` for the holiday bonus. The bonus is in percentage
   points added to the credit factor, not a multiplier.
3. Add the optional per-template valuation override on `ShiftTemplate` (JSON column, same
   payload shape as a category rule) and implement the template-wins resolution order.
4. Extend `TimeEntry` with `statutory_minutes` and `credited_minutes`, populated at derivation.
   Historical entries must keep the valuation in force when derived — a later change to a
   contract group must not silently rewrite last year's account. Add a test for exactly that.
5. Add `backend/app/tests/test_work_time_valuation.py` covering every acceptance criterion,
   including the holiday bonus arithmetic and the call-out case.
6. Update the contract-group admin UI to expose `statutory_factor` alongside the credit fields,
   with help text explaining that they are deliberately independent. DE and EN strings.
7. Update `README.md`, `AGENTS.md`, `CHANGELOG.md`.
```
