# Project state and roadmap

Read this first when picking up work on the compliance / fairness / solver / swaps rollout.
It says where the project stands, what happens next, and which decisions are already made so
they do not get relitigated. It is a living file: update the "Status" and "Roadmap" sections
when something lands.

Companion documents:

- `AGENTS.md` — how this repository is built and the standing rules for working an issue.
  Everything in the section **Working an issue** applies to every task and is not repeated here.
- `docs/rollout/ROLLOUT.md` — the rollout plan: problem statement, feature definitions F0–F8,
  release table R1–R4, risks, sources.
- `docs/rollout/issues/` — the full specification of every issue, including its implementation
  prompt. `created-issues.json` maps file prefix to GitHub issue number.
- `docs/rollout/solver-spike-findings.md` — the CP-SAT spike. Issue #75 is built on it.

Last updated: 2026-09-25.

## What this rollout is

Shift-planner already plans shifts. This rollout makes the plans defensible:

1. **Working-time law and tariff compliance** — evaluate German statutory rules (ArbZG) and
   tariff rules (TV-Ärzte) over a real time axis, per organization, with configurable rule sets.
2. **Rolling fairness** — 12-month rolling accounts, so "who gets the bad duties" is a number
   rather than an argument.
3. **Automatic roster generation** — a CP-SAT solver that proposes a full month, which the
   planner then edits.
4. **Shift swaps** — a giveaway pool plus direct 1:1 swaps, both checked for legality before
   they are offered.

Two things carry the whole design:

- **`PlanState` + the `Rule` protocol.** Every rule is a class with `code`, `severity`,
  `lookback`, `roster_lookback`, `evaluate(state)` and an optional `to_cpsat(...)`. `PlanState`
  is built from a **date window**, never from a `planning_period_id` — that is what makes a rule
  able to look across month boundaries, and it is why month-scoped evaluation was removed.
- **Dual valuation.** Statutory working time (ArbZG) and tariff credit (TV-Ärzte) are two
  independent numbers for the same duty. They are never summed and never collapsed into one
  figure. A Bereitschaftsdienst can be 24 h of statutory working time and 14.4 h of tariff
  credit at the same time, and both are correct.

## Status

`main` carries R1, R2, the solver fixture, the CP-SAT spike findings, SolverRun persistence,
the CP-SAT roster model (tier A), solver controls in `/planning`, shift swap requests, the
swap marketplace UI, and swap UI states that name why an offer or the approval queue is
unavailable. This change closes a duty activity privacy leak: time entry list, ledger,
reconciliation and the MCP time entry reads no longer return individual episodes to readers
the access policy does not grant.

Shipped:

- Time axis, contract groups, employment periods, opening balances, time entry ledger
- Statutory rule sets and presets (per-organization, `TV-Ärzte (TdL)` and ArbZG-Grundmodell)
- Opt-out consents, duty activity log, compliance report
- Rolling 12-month fairness accounts
- `seed_solver_fixture.py` with `comfortable` / `tight` / `infeasible` profiles plus an ArbZG
  profile that exercises rest, weekly-average and documentation rules
- Two production defects found along the way and fixed: `WORKTIME_MAX_DUTIES` counted every
  assignment instead of only Bereitschaftsdienste, and a leftover `ix_doctors_email` made member
  emails globally unique instead of unique per organization
- SolverRun persistence and the Compose solver-worker
- CP-SAT roster model, tier A (`#75`)
- Solver generate / inspect / apply in `/planning` plus MCP parity (`#76`)
- Shift swap and giveaway requests with legality checks (`#77`)
- Swap marketplace UI and planner approval queue (`#78`)
- Swap UI states that explain a missing group, an unlinked account, a draft plan, and an empty approval queue (`#99`)
- Duty activity privacy enforced on every `TimeEntry` read path (REST list / ledger / reconciliation and MCP), not only on `/api/v1/duty-activity`

In flight: write the Tier B encodings issue (`min_rest_period`, `rest_after_long_duty`, `weekly_average_cap`). The infeasible fixture with `--rng-seed 1` / 2026-10 now leaves `bd24` unstaffable on **2026-10-01** and **2026-10-21** (`eligible_member_ids_for_slot`); the spike note recorded 2026-10-25 as the second hole.

## Roadmap

| Order | Issue | What | Notes |
|---|---|---|---|
| 1 | #74 | SolverRun persistence + async execution | shipped |
| 2 | #75 | Build the CP-SAT model from the rule layer — **Tier A only** | shipped |
| 3 | *(to write)* | Tier B encodings: `min_rest_period`, `rest_after_long_duty`, `weekly_average_cap` | write this issue; the ArbZG fixture profile exists |
| 4 | #76 | Solver controls in the planning workspace and MCP | shipped |
| 5 | #77 | Shift swap and giveaway requests with legality checks | shipped |
| 6 | #78 | Swap marketplace UI and planner approval queue | shipped |
| 7 | #99 | Swap UI states that explain why the exchange is unavailable | shipped |

Backlog, not part of the rollout: #34, #44, #51, #52, #53, #54.

**Why #75 is split.** The spike showed that encoding all 18 rules at once is the way to get a
model nobody can debug. Tier A is the set the TdL fixture actually exercises and that the spike
proved solvable in under a second. Tier B is the ArbZG rest and averaging family, which needs
its own fixture profile to be testable at all — that profile now exists, but mixing the two into
one issue means a PR whose failures cannot be attributed.

## Decisions already made

Do not reopen these without a reason that is new:

- **Fairness is rolling over 12 months**, not per-period or per-year.
- **Rule sets are configurable per organization.** There is no single hardcoded German rule set;
  presets seed an organization and are then owned by it.
- **The solver runs fully automatically and the planner post-edits.** It does not propose
  fragments for a human to assemble.
- **Swaps are a giveaway pool plus direct 1:1 swaps.** Both paths, not one.
- **Unfilled slots are a heavily penalized slack variable**, not a hard cover constraint, so a
  deliberately infeasible month still returns a partial roster. Coverage remains the dominant
  objective term (default weight 10 000).
- **Solver reproducibility is `num_search_workers = 1` plus a stored `random_seed`**, both
  persisted on the run. Multi-worker CP-SAT is not reproducible at the roster level even when the
  objective value is, and a planner who re-runs and gets a different plan will not trust the
  feature.
- **Weight ordering** (from the spike): unfilled (dominant) → no-gos → duty-count overflow →
  fairness deviation → unmet wishes. No-gos are currently `error`, so they are hard and are *not*
  in the objective. Pick one or the other, never both.
- **Severity is mapped from `ValidationWarning`, not from `Rule.severity`.**
- **Eligibility comes from `to_cpsat` or explicit masks.** Overlaying `evaluate()` on every
  (slot, member) pair takes 40–60 s on the fixture and does not terminate with opt-out enabled.

## Traps this project has already hit

- **`git branch --contains <sha>` lies after a squash merge.** It matches exact SHAs, not
  content. A commit whose changes are on `main` inside a squashed commit will look missing. Check
  the file content, not the ref graph.
- **Chain shell commands with `&&`.** A failed `git switch` followed by an unconditional
  `gh pr create` opens a pull request against the wrong branch.
- **`pytest` never runs Alembic.** The suite builds SQLite via `Base.metadata.create_all`. A
  migration is only verified by `container-smoke` in CI, or by hand against Postgres.
- **CI only triggers on pull requests and pushes to `main`.** Long-lived feature branches are
  checked by nothing until a PR exists.
- **Scratch code belongs in `backend/scratch/`** (git-ignored) and never in `app/`. The spike
  once added a DNS-probe fallback in `backend/app/db/session.py` that silently redirected the
  application to `127.0.0.1:5433`. Pass `DATABASE_URL=...` on the command line instead.

## Prompting an agent for an issue

Each issue body already contains its own implementation prompt, and `AGENTS.md` carries the
standing rules. What still has to be said out loud, because it is not in either:

1. **Which branch to start from and what is already on it.** "Branch off `main` at <sha>" —
   agents otherwise inherit whatever is checked out.
2. **Which decision above applies**, when the issue text predates it. #75 in particular must be
   read together with `solver-spike-findings.md`, not on its own.
3. **The scope boundary in the negative.** Name the files or subsystems that must not change.
   Scope drift in this repository has consistently been an agent "helpfully" fixing something
   adjacent.
4. **How the acceptance criteria get proven.** If a criterion needs Postgres and a migration run,
   say so; the agent will otherwise show a green `pytest` and call it done.
5. **Whether a finding should stop the work.** For anything solver-shaped the answer is usually
   yes: report and stop rather than work around it.
