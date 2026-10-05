---
title: "Wishes, blocks, and comments are readable in the grid and the inspector"
github: 145
labels: frontend, ux
---

## Context

The planner wishes grid (`frontend/components/planning/WishesGrid.tsx`) paints a day status as an
8px dot plus a pale badge (`frontend/components/planning/WishesCell.tsx`,
`frontend/lib/planningDayStatus.ts`). Wish, no-go, and the comment are small words. On the roster
cell (`frontend/components/planning/RosterGrid.tsx`) the wish is the same pale word.

The inspector already edits the selected day's comment, status, and per-template wish
(`frontend/components/planning/WishesInspectorPanels.tsx`). It does not list the rest of that
person's month. The roster slot panel does not show the assignee's status, wish, or comment.

The matrix payload already includes cells, comments, and shift intents. No new API.

## Decision

- Paint the wishes cell with the status color. Use the existing preset: dark text on the light
  background, contrast at least 4.5:1. A status with `blocks_roster_assignment` uses that fill
  plus a clear block mark.
- Wish and no-go are filled chips on the wishes grid and on the roster cell.
- When a wishes cell or a member is selected, the inspector keeps the selected day's status,
  comment, and per-template wish editor, and adds the month overview underneath. The overview
  lists each day that has a comment (date and the text) and each wish or no-go (date and
  template) for that member only. Choosing a row selects that day.
- The roster slot panel shows the assignee's status, wish or no-go, and comment for that day.

## Scope

1. Cell fill and block mark from the existing color preset.
2. Filled wish and no-go chips on the wishes grid and the roster cell.
3. Month overview in the wishes cell panel and the member panel. A row selects that day.
4. Assignee day status, wish or no-go, and comment on the roster slot panel.
5. Vitest for the month list. A loose Playwright flow that opens a commented wishes cell and
   sees the comment in the inspector.
6. German and English labels. Docs that describe the wishes cell or the inspector.

## Out of scope

- A new API, or a change to how slots are generated.
- Wish priorities (#103).
- Member app issues #122–#125.
- The member wishes page (`MatrixEditor` on `/my-planning`).

## Acceptance criteria

- [ ] A wishes cell uses the status preset as its fill: dark text on the light background,
      contrast at least 4.5:1. A blocking status adds a clear block mark.
- [ ] Wish and no-go are filled chips on the wishes grid and on the roster cell.
- [ ] The wishes inspector keeps the selected day's status, comment, and per-template wish
      editor, and lists that member's comments and wishes for the month. Another member's rows
      are omitted. Choosing a row selects that day.
- [ ] The roster slot panel shows the assignee's status, wish or no-go, and comment for that day.
- [ ] German and English dictionaries both have the new labels.
- [ ] Frontend lint, typecheck, unit tests, and build pass. Playwright opens a commented wishes
      cell and sees the comment text in the inspector, without screenshots.
