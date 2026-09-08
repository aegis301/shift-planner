---
title: "R3: Add SolverRun persistence and asynchronous execution"
labels: rollout-r3, backend, solver
---

## Context

Roster generation for a month takes seconds to minutes and must not block a request. Before any
optimization code is written, the surrounding machinery needs to exist: a record of what was run,
with which parameters, what it produced and why.

## Scope

- `SolverRun`: `organization_id`, `planning_period_id`, `shift_group_id`, `status`
  (`queued` / `running` / `succeeded` / `failed` / `cancelled`), `parameters`,
  `objective_breakdown`, `unfilled_slots`, `post_check_findings`, `rule_set_version_id`,
  timings, `created_by_user_id`.
- Execution out of the request cycle: a background worker in the existing Docker Compose stack
  polling for queued runs. No broker unless something else already needs one.
- Cancellation, a configurable time budget per run, and a hard organization-level ceiling.
- Applying a run writes ordinary `RosterSlotAssignment` rows through the existing service path,
  so preflight, validation and versioning all behave as for manual assignment. Never automatic.
- Refused for shift groups in `published` status, like the other destructive roster actions.

## Acceptance criteria

- [ ] Triggering a run returns immediately with a run id.
- [ ] A run exceeding its budget ends `failed` with a reason, never hangs.
- [ ] Applying produces assignments identical in shape to manual ones.
- [ ] A run against a published shift group is refused with 409.
- [ ] Runs are visible with parameters and objective breakdown after completion.
- [ ] Two workers cannot claim the same run.

## Dependencies

Blocked by #04.

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

Task: build the persistence and execution machinery for roster solving, with no optimization
logic yet.

1. Model `SolverRun` as described. Record `rule_set_version_id` so a run's result can be
   interpreted later.
2. Add a background worker: a small process started from `docker-compose.yml` that polls for
   `queued` runs, claims one atomically (`SELECT ... FOR UPDATE SKIP LOCKED`), runs it and
   writes the result. Do not introduce Celery, Redis or a broker.
3. Enforce a per-run time budget from the run parameters, capped by an organization ceiling. A
   run exceeding it ends `failed` with a reason. Support cancellation.
4. The solve function is a stub here: it returns no assignments and lists every slot as
   unfilled. #20 replaces the stub.
5. Applying goes through the existing assignment service in
   `backend/app/services/roster_matrix.py` so preflight, validation and plan versioning behave
   as for manual assignment. Applying is always an explicit user action.
6. Refuse runs for shift groups in `published` status with 409, consistent with
   `regenerate-roster` and `sync-roster`.
7. REST: `POST /api/v1/planning-periods/{id}/solver-runs`, `GET .../solver-runs`,
   `GET .../solver-runs/{run_id}`, `POST .../solver-runs/{run_id}/apply`,
   `POST .../solver-runs/{run_id}/cancel`.
8. Tests: async return, budget expiry, cancellation, apply-path equivalence with manual
   assignment, published refusal, concurrent claim safety.
9. Update `README.md`, `AGENTS.md`, `CHANGELOG.md`, `docker-compose.yml`.
```
