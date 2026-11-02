---
title: "Resizable workbench panes: roster grid, workload, and inspector in one panel"
github: 156
labels: frontend, ux
---

## Context

The roster tab of `/planning` is built from three independent boxes. `rosterSection` in
`frontend/components/planning/PlannerWorkspace.tsx` is a CSS grid
`xl:grid-cols-[minmax(0,1fr)_340px]` with `gap-4`: the roster grid's own card on the left and the
workload card, fixed at 340 px and sticky, on the right. The inspector
(`frontend/components/workbench/Inspector.tsx`) is a separate `aside` with its own border, a gap
from the workspace, and a width slider limited to 360–440 px.

The roster grid's columns have fixed widths, so the grid is narrower than its card. That leaves
an empty strip inside the card, and the gaps between the cards add more. The planner cannot give
the workload table or the inspector more room when they need it.

## Decision

- Add a custom `SplitPane` primitive in `frontend/components/ui/SplitPane.tsx`. No new
  dependency, no Radix, design tokens like the other primitives.
- One bordered surface. Panes sit edge to edge and are separated by a thin divider (about 6 px
  of hit area, a 1 px line in `border-default`). No gaps and no nested cards.
- Each pane has an `id`, `minSize`, `maxSize`, `defaultSize`, and `collapsible`. One pane is
  `flex` and takes the remaining space. Horizontal and vertical layouts are both supported.
- Drag uses pointer events with pointer capture. A double-click on a divider collapses or
  restores the neighbouring collapsible pane.
- Every divider is `role="separator"` with `aria-orientation`, `aria-valuenow`,
  `aria-valuemin`, and `aria-valuemax`. Arrow keys move it 16 px, Shift+Arrow 64 px, Home and
  End jump to the minimum and maximum, Enter collapses or restores. The keys are registered in
  `lib/shortcuts.ts` and appear in the `?` help.
- Sizes persist per layout key in `localStorage` (`shift-planner-split:<key>`). When the window
  shrinks, sizes are clamped so the `flex` pane never drops below its minimum.
- Size math lives in a pure module, `frontend/lib/splitPane.ts`.

## Scope

1. `SplitPane` and `lib/splitPane.ts` with Vitest coverage.
2. Roster tab: one `SplitPane` with the roster grid (`flex`, min 480 px), the workload table
   (default 340 px, 260–600 px, collapsible), and the inspector (default 400 px, 320–640 px,
   collapsible). The panel fills the viewport height under the context bar and each pane scrolls
   on its own.
3. Wishes tab: the wishes grid and the inspector in the same component.
4. Remove the 340 px grid column, the workload sticky wrapper, and the inspector width slider.
   The inspector toggle (`i`) collapses its pane instead of unmounting it.
5. Below 1280 px the workload pane starts collapsed. The stacked view keeps its order, and its
   roster block uses the same panel.
6. A loose Playwright flow: drag the grid/workload divider and see the workload pane grow, keep
   the width after a reload, press Enter on the inspector divider and see it collapse. The axe
   check on the roster tab still passes. No screenshots.
7. German and English labels. `frontend/components/ui/README.md`, `AGENTS.md`, `CHANGELOG.md`.

## Out of scope

- Column widths inside the roster grid.
- More analysis tables in the panel.
- The member companion pages.
- Any API change.

## Acceptance criteria

- [ ] `SplitPane` exists in `frontend/components/ui/` without a new dependency, and its size
      math in `frontend/lib/splitPane.ts` is covered by Vitest: clamping to min and max, the
      flex pane never below its minimum, keyboard steps, collapse and restore, persisted sizes
      reapplied and clamped.
- [ ] Every divider is a focusable `role="separator"` with `aria-orientation`,
      `aria-valuenow`, `aria-valuemin`, and `aria-valuemax`, and its keys are listed in
      `lib/shortcuts.ts`.
- [ ] The roster tab shows the grid, workload, and inspector in one panel. The 340 px column,
      the sticky workload wrapper, and the inspector width slider are gone.
- [ ] The wishes tab shows the wishes grid and the inspector in the same panel component.
- [ ] Dragging the grid/workload divider widens the workload pane, and the width survives a
      reload.
- [ ] Enter on the inspector divider, or the inspector toggle, collapses the inspector pane.
- [ ] The axe check on the roster tab passes with the separators added.
- [ ] German and English dictionaries both have the new labels.
- [ ] Frontend lint, typecheck, unit tests, and build pass.
