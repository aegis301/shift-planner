---
title: "Workbench grid primitive and the roster matrix on it: keyboard, ranges, paste, undo"
labels: frontend, ux, architecture
---

## Context

Part of ADR 0001 (`docs/decisions/0001-desktop-first-workbench.md`, decision 2). The roster
matrix is where planners spend their time. Today it is a mouse-only table.

What exists on `main` (after #114 and #115):

- `frontend/components/RosterMatrixEditor.tsx` (1,567 lines) renders **three** layouts of the same
  data: a template-column table (around line 684), a per-day list (around line 768) and a per-day
  card layout (around line 863), the last two for narrow screens. After #114 only the planner
  uses it, so only the first layout is needed.
- Layout of the table: rows are days (`matrix.days`), columns are shift templates
  (`matrix.shift_templates`), and a cell holds **every slot** of that template on that day
  (`slotsForTemplateDay`, around line 306). Templates with a required count above one produce
  several slots per cell, distinguished by `slot.position` (`#2`, `#3`).
- Editing is click, then a `Popover` + `Combobox` picker (after #112), then save one slot through
  a mutation (after #113). No keyboard navigation, no range selection, no copy, no paste, no
  undo. Sticky headers only.
- `formatTimeRange` parses times from the ISO string with a regex (around line 165). After #109
  it must use `lib/orgTime.ts`.
- #116 provides `POST /api/v1/roster-matrix/{id}/change-sets` (atomic bulk writes with per-row
  results), `GET .../change-sets` (history) and `POST .../change-sets/{id}/revert` (undo and redo).
  Every single-cell edit already returns a `change_set_id`.
- #115 provides the inspector, the `?slot=` selection in the URL, and the shortcut registry
  `lib/shortcuts.ts`.

## Decision for this issue

**Library.** TanStack Table (headless model: columns, rows, pinning) plus TanStack Virtual (row and
column virtualization), with our own cell rendering and our own selection and keyboard model.
AG Grid is allowed only if you show, in the PR, a short comparison on: custom multi-part cells,
virtualization with pinned day column, licence cost of the features we need, and bundle size.
The recommendation is TanStack.

**Grid primitive** in `frontend/components/grid/`, reused by the wishes matrix (#118):

- `Grid` renders a virtualized table with a pinned first column (days) and pinned header rows.
- `useGridSelection`: active cell, rectangular range, extend with `Shift+arrows` and
  `Shift+click`, select row (`Shift+Space`), select column (`Ctrl+Space`), select all (`Ctrl+A`).
- `useGridKeyboard`: arrows, `Home`/`End`, `Ctrl+Home`/`Ctrl+End`, `PageUp`/`PageDown` (one week),
  `Tab`/`Shift+Tab`, `Enter` or `F2` opens the cell editor, typing a character opens the editor
  with a filter, `Escape` cancels, `Delete`/`Backspace` clears the range.
- `useGridClipboard`: copy the range as TSV (for Excel) and as an internal JSON format with ids on
  the clipboard; paste from both. Pasting TSV resolves member display names (nickname, else last
  name, as `team_member_planning_display_name` does) and emails to member ids, and reports
  unresolved names instead of guessing.
- Accessibility: `role="grid"`, `aria-rowcount`/`aria-colcount` with virtualization,
  `aria-selected`, roving `tabindex`, visible focus ring from the tokens.
- Every key binding is registered in `lib/shortcuts.ts` so the `?` overlay lists it.

**Roster column model.** One grid column per (template, position) pair: a template with a maximum
required count of 2 in the month becomes columns "BD #1" and "BD #2", grouped under one template
header. One grid cell is exactly **one slot**, or empty and not editable when no slot exists that
day. This is what makes ranges, paste and keyboard movement well-defined.

**Cell content.** Assignee display name; severity marker from validation findings for that slot
(token colors from #112); wish / no-go / day-status hint for the assignee; a swap badge when an
open swap request touches the slot; `manual_override` marker. Compact and comfortable densities.
Details live in the inspector, not in the cell.

**Edits go through change sets.**

- Single pick in the editor: existing single-cell mutation (it returns `change_set_id`).
- Paste, clear range, fill down (`Ctrl+D`) and fill right (`Ctrl+R`): one
  `POST .../change-sets` with `mode: "all_or_nothing"` by default. If refused, show a results panel
  in the inspector listing each row's refusal reason and offer "Apply what is legal"
  (`best_effort`).
- Optimistic rendering for the set, rolled back on refusal.

**Undo and redo.** A per-page undo stack of `change_set_id`s created in this session.
`Ctrl+Z` reverts the top set through `.../revert`; `Ctrl+Shift+Z` / `Ctrl+Y` reverts the revert.
Items refused as `changed_since` are shown in the inspector. The stack survives reload through the
`GET .../change-sets` history filtered to the current user. The inspector's slot history from
#115 reads the same history.

## Scope

1. Build `components/grid/` with unit tests for selection, keyboard and clipboard logic (pure
   functions where possible, tested with Vitest).
2. Rebuild the planner roster matrix on it as `components/planning/RosterGrid.tsx`. Delete the
   list and card layouts from `RosterMatrixEditor.tsx` (members have their own views since
   #114). Remove `RosterMatrixEditor.tsx` when nothing uses it.
3. Wire selection to the inspector (`?slot=`), edits to the mutations, bulk edits and undo to change
   sets.
4. Performance: 31 days x 40 slot columns renders and scrolls at 60 fps on a mid-range laptop;
   keyboard movement has no perceptible lag. Add a Playwright perf smoke test that fails if
   moving the active cell 100 times takes over 2 s.
5. Playwright: navigate with the keyboard, select a range, copy, paste into another range, see
   one change-set request, undo, redo; paste an illegal assignment and see the per-row refusal and
   the best-effort option; paste TSV from a string with one unknown name and see it reported.

## Out of scope

- Wishes matrix (#118).
- Backend changes (if the change-set API is missing something, stop and report).
- Drag and drop.

## Acceptance criteria

- [ ] `components/grid/` exists with Vitest coverage for selection, keyboard and clipboard.
- [ ] The planner roster matrix uses it; one cell equals one slot; the list and card layouts are
      gone from the planner path.
- [ ] Keyboard-only: a planner can assign a whole week without touching the mouse (Playwright).
- [ ] Paste of N cells sends exactly one change-set request (Playwright request count).
- [ ] Undo and redo work across a reload (Playwright).
- [ ] Refused paste shows per-row reasons and the best-effort option (Playwright).
- [ ] `role="grid"` semantics and focus handling pass an axe check (`@axe-core/playwright`).
- [ ] Golden screenshots of the roster tab are regenerated and reviewed in the PR.
- [ ] Both dictionaries. `npm run lint`, `npm run typecheck`, `npm run build`, `npm run test`,
      `npm run test:e2e` green.

## Dependencies

Needs #115 and #116. Should follow #109. Blocks #118.

## Implementation prompt

```text
You are working in the `aegis301/shift-planner` repository.
Start from the latest `main`: `git fetch origin && git switch -c feat/roster-grid origin/main`.
Do not continue on a branch from another issue.

Read these before writing any code, and follow them strictly:
1. `AGENTS.md`, especially **Working an issue**, **Matrix Planning Rule**, **Style → Frontend surfaces** and **Testing Expectations**.
2. `docs/rollout/STATE.md`, especially **Traps this project has already hit**.
3. `docs/decisions/0001-desktop-first-workbench.md`.
4. This issue's spec in full: `docs/workbench/issues/09-roster-grid.md`, and the change-set API
   section of `AGENTS.md` added by #116.

Standing rules that matter most here:
- Business logic lives in backend services. The grid never decides legality; it shows what the
  change-set API and validation return.
- Planners always send `shift_group_id`.
- Every user-visible string exists in both dictionaries in `frontend/lib/i18n.ts`.
- Update `README.md`, `CHANGELOG.md`, `PLAN.md`, `AGENTS.md` and `docs/rollout/STATE.md` in the same change.
- Before you finish: `cd frontend && npm run lint && npm run typecheck && npm run build && npm run test && npm run test:e2e`.

Task: build the shared grid primitive and move the planner roster matrix onto it, with keyboard
navigation, range selection, clipboard, bulk edits through change sets, and undo and redo.

1. Confirm the Playwright suite is green on `main`. If not, stop and report.
2. Build the selection, keyboard and clipboard logic as pure, tested functions first, then the
   `Grid` component around them.
3. Build `RosterGrid` with the (template, position) column model. Keep every piece of information
   the current table cell shows; list them in the PR and tick each off.
4. Wire single edits, bulk edits, undo and redo. Use the query keys and invalidation map from
   #113; a change set invalidates roster matrix, validation and fairness for the period and
   group.
5. Remove the narrow layouts and, when unused, `RosterMatrixEditor.tsx`.
6. Write the Playwright tests and the perf smoke test.

Do not change: backend code, the wishes matrix, the inspector's content beyond wiring the slot
selection and change-set results.

Stop and report instead of guessing if: the change-set API cannot express an edit the grid needs
(for example moving an assignee between two slots as one step), or TSV paste cannot map columns
unambiguously to (template, position) pairs.

Prove it: walk the acceptance criteria one by one in the PR and name the test, command output or
CI run that proves each.
```
