---
title: "R3: Seed a realistic planning month with history for solver work"
labels: rollout-r3, backend, solver, testing
---

## Context

There is no seed for a realistic planning month. `backend/app/scripts/` contains only
`seed_admin`, `seed_planner_user`, `seed_team_member_users` and `seed_work_time_presets`.

A solver cannot be evaluated without one. On an empty month with no wishes, every model solves
trivially and tells you nothing; and the interesting behaviour — infeasibility handling, weight
ordering, binding constraints — only appears on data that is actually tight. The statutory rules
from #64 and the fairness accounts from #72 also need **history**: a rolling weekly average and a
12-month expected share have nothing to compute against a database that starts this month.

This seed is a prerequisite for the solver spike (#25), for #74–#76, and for
R4. It is also the fixture that makes every future regression test in this area realistic.

## Scope

A new `backend/app/scripts/seed_solver_fixture.py`.

**It is a generator with a difficulty knob, not one fixed month.** Three profiles:

| Profile | Members | No-go density | Purpose |
|---|---|---|---|
| `comfortable` | 20 | ~10 % of member-days | baseline; a good solution must exist |
| `tight` | 14 active (rest on leave) | ~30 % | the realistic case; tests weight ordering |
| `infeasible` | 10 | ~50 % + a scarce property requirement | tests partial solutions and binding-constraint reporting |

**Deterministic.** A `--rng-seed` parameter drives every random choice, so two runs with the same
parameters produce byte-identical data. Without this, a failing solver test cannot be reproduced.

**Organization shape** (all profiles):

- 2 shift groups: `anaesthesie` and `intensiv`, members split roughly 60/40 with a few in both
- 1 contract group at 42 h/week, 30 vacation days, TdL-style category rules
- Employment percentages mixed: roughly 60 % at 100, 25 % at 75, 15 % at 50 — a uniform
  distribution makes fairness expectation uniform and hides the bug this data is meant to expose
- Shift templates:

| Code | Category | Variants | required_count |
|---|---|---|---|
| `bd24` | bereitschaftsdienst | weekday Mo–Do 08:00 → 08:00+1; weekend/holiday Fr–So | 1 |
| `spaet` | spaetdienst | weekday Mo–Fr 14:00–22:00 | 2 |
| `ruf` | rufdienst | weekend Sa–So 08:00 → 08:00+1 | 1 |

  This yields roughly 30 on-call duties per 30-day month. Against 20 members that is about
  1.5 each — comfortably under the TdL limit of 4 per month — and against 10 members it is 3
  each, which starts to bind. That is the intended difficulty gradient; keep the ratio.

- Active rule set: the `TV-Ärzte (TdL)` preset from #65
- Opt-out consents for ~60 % of members, so both the base cap and the opt-out cap path are
  exercised in the same fixture
- Two team member property definitions: `facharzt` (select: ja / nein, ~50 % ja) and
  `sonografie_zertifikat` (select, ~30 % ja). In the `infeasible` profile, put a
  `team_member_property_requirement` on `bd24` requiring `facharzt = ja` and reduce the
  qualifying members to 3, so a 1-per-day template cannot be staffed

**History** (`--history-months`, default 6):

Completed months before the target month, each fully assigned and moved to `published`, with
derived `TimeEntry` rows so `statutory_minutes_by_member_date` and the fairness accounts have
real input. Distribute duties **unevenly** across members on purpose — an even history makes
every fairness deviation zero and the fairness objective untestable.

**Target month** (`--year`, `--month`, default: next month):

Created in `draft`, roster slots generated, **no assignments**, with:

- day statuses on ~8 % of member-days (vacation, research, teaching)
- template no-gos at the profile's density
- wishes on ~10 % of member-days

**Safety.** This writes a lot of data. It must refuse to run against an organization that has
any `PlanningPlanVersion` rows unless `--force` is passed, and it must never target the
organization named in `DEFAULT_ORGANIZATION_ID` without `--force`. Default behaviour is to
create a fresh organization with a generated slug (`solver-fixture-<profile>-<rng-seed>`).

## Out of scope

Any solver code. Performance benchmarking. Frontend.

## Acceptance criteria

- [ ] Two runs with identical parameters produce identical data (compare a stable digest of the
      generated rows).
- [ ] `comfortable`: a valid full assignment demonstrably exists — prove it with a greedy
      assignment in a test, not by assertion.
- [ ] `infeasible`: at least one `bd24` slot cannot be filled by any eligible member, and a test
      asserts this.
- [ ] History produces non-zero, **unequal** fairness deviations across members.
- [ ] The rolling weekly average from #64 returns non-zero values for every member.
- [ ] Running against an organization with plan versions is refused without `--force`.
- [ ] Documented in `README.md` with the exact command for each profile.

## Dependencies

Needs R1 and R2 on the branch (contract groups, time entries, rule sets, presets, consents,
fairness). Blocks the solver spike and #74.

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

Task: build a deterministic, difficulty-tunable seed script that generates a realistic planning
month plus history, for solver development and regression testing.

1. Read the existing seeds in `backend/app/scripts/` for the conventions (idempotency, argument
   handling, how they are invoked from Docker Compose). This one is NOT idempotent in the same
   sense — it creates a fresh organization per run by default — but it must be safe to re-run.
2. Build the data through the existing **service functions**, not raw model inserts. Contract
   groups via `services/contract_groups.py`, employment periods via `services/employment_periods.py`,
   shift templates and variants via `services/shift_templates.py`, roster generation via the
   existing period-roster path, time entries via `services/time_entries.py` derivation. If a
   service makes this awkward, that is a finding worth reporting — do not bypass it silently,
   because the fixture must exercise the same code paths production does.
3. Implement the three profiles and every parameter exactly as specified in the issue body
   above. The numbers there are deliberate: the slot-to-member ratio is what makes the
   difficulty gradient work, so do not "round them off".
4. Determinism: seed a `random.Random(rng_seed)` instance and pass it everywhere. Do not use the
   module-level `random` functions, and do not rely on set or dict iteration order for any
   choice that affects output.
5. History months must be fully assigned, published, and **unevenly distributed** across members.
   An even distribution makes every fairness deviation zero and silently defeats the purpose.
6. Safety guards: refuse to write into an organization that has any `PlanningPlanVersion` rows
   without `--force`; never target `DEFAULT_ORGANIZATION_ID` without `--force`; default to
   creating a fresh organization.
7. Tests in `backend/app/tests/test_solver_fixture.py` covering every acceptance criterion. The
   `comfortable` feasibility test must construct an actual valid assignment greedily rather than
   asserting that one exists.
8. Document the three commands in `README.md`. Update `CHANGELOG.md` and `AGENTS.md`.
9. Run `ruff check app` and `pytest`.
```
