---
title: "R2: Surface fairness deviation in the planning workspace and roster picker"
labels: rollout-r2, frontend, ux
---

## Context

The analysis tab and the roster picker show raw shift counts. A count without a target does not
tell a planner who to assign next; a deviation does.

## Scope

- Analysis tab: actual / expected / deviation per dimension, sortable, with the rolling window
  stated. Keep existing shift-count columns as secondary information.
- Roster picker: each candidate's deviation for the relevant dimension inline, so the most
  under-served eligible person is visible at the moment of assignment.
- The per-member workload modal gains the rolling account next to the month view.
- Month and rolling figures must never be presentable as the same kind of number.

## Acceptance criteria

- [ ] The analysis table sorts by deviation and states the window.
- [ ] The roster picker shows deviation without an extra request per candidate.
- [ ] Month and rolling figures are visually distinct.
- [ ] DE and EN strings for every label.
- [ ] Tables scroll inside the existing `dataTableScrollShellClassName` shell.

## Dependencies

Blocked by #17.

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

Task: surface fairness deviation in the planning UI.

1. Read `frontend/lib/rosterWorkload.ts` (`buildMemberWorkloadRows`),
   `frontend/components/RosterMatrixEditor.tsx` (picker and workload modal) and the analysis
   section of `frontend/components/PlanningWorkspace.tsx`.
2. Extend the workload payload with the rolling account from #17 and render actual, expected and
   deviation per dimension. Keep the existing sortable-header behaviour (first activation A→Z
   for names, high→low for numbers).
3. In the roster picker, render deviation for the dimension relevant to the slot being filled.
   Fetch it once with the matrix payload; do not issue a request per candidate.
4. Label the window explicitly wherever a rolling figure appears, and keep month figures
   visually distinct from rolling ones.
5. Reuse `dataTableScrollShellClassName` for any new table so sticky headers keep working.
6. Add DE and EN strings. Run `npm run lint` and `npm run typecheck`.
7. Update `README.md` and `CHANGELOG.md`.
```
