---
title: "R3: Solver controls in the planning workspace and MCP"
labels: rollout-r3, frontend, mcp, solver
---

## Context

Full generation with post-editing is the chosen model. Planners will adopt it only if they can
see what the solver optimized for and what it could not fill.

## Scope

- Planning workspace: a generate action with parameters (time budget, objective weights, whether
  to overwrite existing assignments), run status, and a result view.
- Result view: objective breakdown per component, unfilled slots with binding constraints,
  post-check findings, and an explicit apply action behind confirmation.
- Applying is a normal roster change: it bumps the working version and every assignment stays
  editable.
- MCP: guarded `run_roster_solver_tool`, a read resource for runs and results, and a guarded
  `apply_solver_run_tool`. "Fill March for the on-call group fairly" should be satisfiable
  through these tools alone.

## Acceptance criteria

- [ ] A planner can generate, inspect and apply a run without leaving `/planning`.
- [ ] Unfilled slots are listed with the reason they could not be filled.
- [ ] Applying is never implicit and always confirmed.
- [ ] Published shift groups offer no generate action.
- [ ] MCP tools reach the same service functions as REST.
- [ ] DE and EN strings throughout.

## Dependencies

Blocked by #20.

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

Task: add solver controls to the planning workspace and expose the solver through MCP.

1. Read `frontend/components/PlanningWorkspace.tsx`, particularly the existing destructive month
   actions (regenerate, sync roster) and their confirmation dialogs, and follow the same
   interaction pattern.
2. Add a generate action with a parameter form: time budget, objective weights, overwrite
   existing assignments. Poll the run until it completes; show status.
3. Build the result view: objective breakdown per component, unfilled slots with binding
   constraints, post-check findings, and an apply action behind a confirmation dialog stating
   how many assignments will be written.
4. Hide the generate action for shift groups in `published` status.
5. MCP: `run_roster_solver_tool` and `apply_solver_run_tool` (admin-token guarded) and a
   `shift-planner://solver-runs/{planning_period_id}` resource, calling the same service
   functions as REST — no duplicated logic in the MCP layer.
6. Add DE and EN strings for every label, including objective component names.
7. Tests: MCP tool authorization and parity in `mcp-server/tests/test_server.py`.
   Run `npm run lint` and `npm run typecheck`.
8. Update `README.md`, `AGENTS.md`, `CHANGELOG.md`, `PLAN.md`.
```
