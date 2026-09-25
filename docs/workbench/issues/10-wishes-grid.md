---
title: "Wishes matrix on the workbench grid"
labels: frontend, ux
---

## Context

Part of ADR 0001 (`docs/decisions/0001-desktop-first-workbench.md`, decision 2). Second consumer
of the grid primitive from #117.

What exists on `main`:

- `frontend/components/MatrixEditor.tsx` (2,100 lines). Rows are days, columns are team members
  (the period roster of the selected shift group). Each cell holds exactly one org-defined day
  status (`PlanningCell.status`, codes from `planning_day_status_definitions`) plus an optional
  comment. Per member, date and shift template, `PlanningShiftIntent` stores a wish or a no-go.
  Month notes per member (`TeamMemberPeriodNote`) are opened from the column header
  (`TeamMemberNoteModal`, around line 1670) and the member's own monthly comment
  (`MonthlyCommentModal`, around line 828).
- `components/PlanningDayIntervalBar.tsx` sets one status over a day interval for one member.
- Writes: `PUT /api/v1/matrix/{id}/cells`, `PUT .../cells/bulk`, `PUT .../shift-intents/bulk`,
  `POST .../cells/clear`, `PUT .../notes` (`backend/app/api/v1/matrix.py`). Planners pass
  `shift_group_id`. Wishes are editable while the group is `draft` or `preliminary`.
- Wishes have **no legality check**, so they do not need server-side change sets. Undo can be
  client-side: the inverse of a bulk write is another bulk write with the previous values.
- Open concept issue #103 ("wishes rework": priorities, finer-grained wishes, comments visible to
  planners). This issue does **not** implement #103. It must not make #103 harder: keep the cell
  renderer and editor as separate components so a priority or a per-template wish can be added to
  the cell later without touching the grid.

## Decision for this issue

- `components/planning/WishesGrid.tsx` on `components/grid/`. Rows days, columns members, pinned
  day column, member header with display name, employment percentage and a note indicator.
- Cell shows the status color and short label (tokens), a comment marker, and wish / no-go
  markers for templates. The full detail (comment text, intents per template, day status history)
  is in the inspector (#115) for the selected cell.
- Editing: typing opens a status combobox filtered by label or code; `Delete` clears; paste of
  status codes or labels (TSV) and of the internal format; fill down and fill right.
  All multi-cell writes use `PUT .../cells/bulk` or `.../cells/clear` in one request.
  Intents are edited in the inspector, not in the cell, and saved with
  `PUT .../shift-intents/bulk`.
- Undo and redo: a client-side stack of inverse operations built from the pre-edit values in the
  query cache. Each entry is one bulk request. Conflicts (the cell changed on the server since) are
  detected by comparing the current cached value before undoing; changed cells are skipped and
  listed in a toast.
- Member notes and the monthly comment move into the inspector's member panel. The two modals
  are deleted.
- `PlanningDayIntervalBar` becomes unnecessary for planners (range selection plus typing a
  status does the same). Keep it only if the member view from #114 still uses it.
- Read-only when the group is `published`, with the reason shown in the context bar.

## Scope

1. `WishesGrid` with the behaviour above. Keep every piece of information the current cell shows;
   list them in the PR.
2. Client-side undo stack with conflict detection, as a tested pure module
   (`lib/wishesUndo.ts`).
3. Inspector panels for a wishes cell and for a member's notes.
4. Remove `MatrixEditor.tsx` from the planner path (and delete it if the member path does not use
   it after #114).
5. Playwright: keyboard-set a status over a range with one request, paste codes from TSV, undo,
   redo, undo skips a cell changed by another session, published group is read-only.

## Out of scope

- #103 (priorities, finer wishes, planner-visible comments beyond showing what exists).
- Backend changes.
- Member-facing wishes UI (that is #114 on web and #124 in the app).

## Acceptance criteria

- [ ] The planner wishes matrix uses the grid primitive; `MatrixEditor.tsx` is not used on
      `/planning`.
- [ ] Range edits send one bulk request (Playwright request count).
- [ ] Undo and redo, with conflict skip, work (Vitest for `lib/wishesUndo.ts`, Playwright for the
      flow).
- [ ] Member notes are edited in the inspector; the two modals are gone.
- [ ] Published groups are read-only with a visible reason.
- [ ] Golden screenshots of the wishes tab regenerated and reviewed in the PR.
- [ ] Both dictionaries. `npm run lint`, `npm run typecheck`, `npm run build`, `npm run test`,
      `npm run test:e2e` green.

## Dependencies

Needs #117. Related to #103 (do not implement it here).

## Implementation prompt

```text
You are working in the `aegis301/shift-planner` repository.
Start from the latest `main`: `git fetch origin && git switch -c feat/wishes-grid origin/main`.
Do not continue on a branch from another issue.

Read these before writing any code, and follow them strictly:
1. `AGENTS.md`, especially **Working an issue**, **Matrix Planning Rule**, **Planning day status**, **Style → Frontend surfaces** and **Testing Expectations**.
2. `docs/rollout/STATE.md`, especially **Traps this project has already hit**.
3. `docs/decisions/0001-desktop-first-workbench.md`.
4. This issue's spec in full: `docs/workbench/issues/10-wishes-grid.md`, and GitHub issue #103 so
   you know what not to block.

Standing rules that matter most here:
- Business logic lives in backend services.
- Planners always send `shift_group_id`; the member path sends `team_member_portal=true`.
- Every user-visible string exists in both dictionaries in `frontend/lib/i18n.ts`.
- Update `README.md`, `CHANGELOG.md`, `PLAN.md`, `AGENTS.md` and `docs/rollout/STATE.md` in the same change.
- Before you finish: `cd frontend && npm run lint && npm run typecheck && npm run build && npm run test && npm run test:e2e`.

Task: move the planner wishes matrix onto the grid primitive from #117, with range edits,
clipboard, client-side undo and inspector panels for cells and notes.

1. Confirm the Playwright suite is green on `main`. If not, stop and report.
2. Inventory what the current wishes cell and header show and do; that list is the checklist.
3. Write `lib/wishesUndo.ts` with tests first.
4. Build `WishesGrid`, the inspector panels, and wire bulk writes.
5. Remove the modals and `MatrixEditor.tsx` from the planner path.
6. Write the Playwright tests.

Do not change: backend code, the grid primitive's public API (extend it only if the roster grid
keeps working unchanged), anything #103 asks for.

Stop and report instead of guessing if: a cell edit needs a backend endpoint that does not exist,
or undo cannot be expressed as bulk writes for some edit.

Prove it: walk the acceptance criteria one by one in the PR and name the test, command output or
CI run that proves each.
```
