---
title: "Roster viewing options: template, day/night, and variant columns"
github: 143
labels: frontend, ux
---

## Context

The planner roster grid (`frontend/components/planning/RosterGrid.tsx`) builds columns in
`frontend/lib/rosterColumns.ts`. Each column is one template, variant, and position
(`templateId:variantId:position`). A template with weekday, weekend, and holiday variants
therefore keeps a column for every variant all month, and most cells are an empty dash.

Issue #117 asked for one column per template and position. The variant split was added so a
weekend day shift and a night shift both stay visible. That part stays. The empty variant
columns do not.

The planning context bar and `?period=` / `?shiftGroup=` already make the workbench linkable.
The command palette lists the primary planner actions.

## Decision

Three roster views, chosen in the planning context bar and stored in `?rosterView=`. The
command palette lists them. The default is `template`.

- **Template** (`template`): one column per shift template and position (`BD #1`, `BD #2`).
  A cell stacks every real slot that exists that day, earlier start first. A weekend with a
  day shift and a night shift shows both names in that one cell. A weekday variant and a
  weekend variant do not become two columns.
- **Day/night** (`day-night`): the same grouping, except a template that has both a day slot
  and a night slot somewhere in the month gets two columns, day and night. Night means the
  slot’s local start, in the organization time zone, is 14:00 or later, or the shift crosses
  midnight. The day column is empty on days that have no day slot. Templates that never split
  stay one column.
- **Variant** (`variant`): the current columns, for when the variant label itself matters.

Selection stays one slot. Each stacked name keeps `data-roster-slot`. Clicking a name edits
that slot. Arrow keys move between columns. Inside a stack, Up and Down move between that
day’s slots before leaving the cell. Copy, paste, fill, and undo still target the active
slot, so one cell is still one write. Placeholder dashes are not slots and are skipped.

Column building stays in `frontend/lib/rosterColumns.ts`. No backend or slot-generation change.

## Scope

1. `rosterGridColumns` accepts the view and the organization time zone.
2. Context bar control and `?rosterView=` on `/planning`.
3. Command palette entries for the three views.
4. Stacked cell rendering, click-to-edit the named slot, and Up/Down inside the stack.
5. Vitest for the three views and a loose Playwright flow.
6. German and English labels. Docs that describe the roster columns.

## Out of scope

- Wishes color, block marks, and the month overview in the inspector (the next issue).
- Member app issues #122–#125.
- Changing how slots are generated.
- Removing variant view.

## Acceptance criteria

- [ ] The planning context bar offers template, day/night, and variant, and the choice is in
      `?rosterView=`. Template is the default.
- [ ] The command palette lists the three views.
- [ ] Template view is one column per template and position. Slots that day stack, earlier
      start first, each with `data-roster-slot`. Weekday and weekend variants share a column.
- [ ] Day/night view adds day and night columns only for a template that has both somewhere
      in the month. Night is a local start at 14:00 or later, or a shift that crosses
      midnight. Templates that never split stay one column.
- [ ] Variant view keeps the current headers.
- [ ] Clicking a stacked name edits that slot. Up/Down moves inside the stack before leaving
      the cell. Copy, paste, fill, and undo still write the active slot. Dashes are not slots.
- [ ] German and English dictionaries both have the new labels.
- [ ] Frontend lint, typecheck, unit tests, and build pass. Playwright covers the template
      view flow without screenshots.
