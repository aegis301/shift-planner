---
title: "R1: Hours ledger UI for members and planners"
labels: rollout-r1, frontend, ux
---

## Context

The ledger from #06 is invisible without a surface. Members need to see and correct their own
time; planners need the group view and the divergence between derived and corrected entries.

## Scope

- `/my-hours`: the signed-in member's entries for a selected period — derived and manual —
  with contract hours, credited and statutory minutes, absences, and the running account
  including the opening balance. Inline correction of a derived entry, with the original still
  visible.
- `/hours` (planner/admin, shift-group scoped): the same per member, plus the reconciliation
  view showing where corrections diverge from the roster.
- Both use the existing `dataTableScrollShellClassName` shell so sticky headers keep working.
- Navigation entries in `AppShell.tsx` gated by capability, following the existing pattern.

## Acceptance criteria

- [ ] A member sees their own entries only; a planner sees their shift groups only.
- [ ] Correcting a derived entry keeps the derived value visible alongside the correction.
- [ ] Statutory and credited minutes are shown as two distinct columns, never summed together.
- [ ] The running account includes the opening balance.
- [ ] DE and EN strings; works at 360 px.

## Dependencies

Blocked by #06, #07.

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

Task: build the hours ledger UI.

1. Read `frontend/components/AppShell.tsx` for capability-gated navigation and
   `frontend/lib/dataTableLayout.ts` for the table shell every data table uses.
2. Build `/my-hours` for the signed-in member and `/hours` for planners and admins, following
   the existing shift-group scoping conventions (`shift_group_id` required for planners).
3. Show statutory minutes and credited minutes as two separate columns with distinct labels and
   a short explanation of why they differ. They must never be summed or presented as one figure
   — that is the modelling error the whole design guards against.
4. Inline correction of a derived entry must keep the derived value visible next to the
   correction, so the divergence is legible rather than overwritten.
5. Planner view adds the reconciliation read from #06.
6. Add DE and EN strings. Verify at 360 px. Run `npm run lint` and `npm run typecheck`.
7. Update `README.md` and `CHANGELOG.md`.
```
