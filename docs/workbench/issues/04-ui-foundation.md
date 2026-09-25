---
title: "UI foundation: Radix primitives, design tokens and dialog migration"
labels: frontend, architecture, ux
---

## Context

Part of ADR 0001 (`docs/decisions/0001-desktop-first-workbench.md`, decision 3). The workbench
redesign (#115, #117) needs dense, keyboard-first building blocks. Today there are none.

What exists on `main`:

- `frontend/package.json` depends on `next`, `react`, `lucide-react` and `recharts`. No component
  library, no headless primitives.
- `frontend/tailwind.config.ts` defines four colors (`mint`, `coral`, `ink`, `cloud`) and one
  shadow. Everything else is raw Tailwind palette classes: about 966 uses of `slate-`,
  `emerald-`, `rose-`, `amber-` across `components/` and `app/`, plus 44 arbitrary values
  (`text-[...]`, `bg-[...]`, `...px]`).
- `frontend/app/globals.css` sets a gradient background on `body` and a print rule.
- **Dialogs are hand-rolled** with a `fixed inset-0` overlay in 14 files:
  `StaffDirectoryPanel`, `PlanningDayStatusDefinitionsPanel`, `SolverGenerateDialog`,
  `OrganizationManagementPanel`, `PlanningDayIntervalBar`, `ShiftGroupForms`, `MatrixEditor`,
  `PlanningWorkspace`, `PlanVersionPanel`, `TeamMemberPropertyDefinitionModal`, `ResourceForms`,
  `ShiftSwapOfferDialog`, `RosterMatrixEditor`, `ContractGroupsPanel` (all in
  `frontend/components/`). Focus trapping, `Escape`, scroll lock, `aria-modal` and return focus
  are implemented differently or not at all in each.
- **Menus and popovers are hand-rolled**: the user and organization menus in `AppShell.tsx`, the
  status menu in `PlanningPeriodStatusMenu.tsx`, and the roster cell picker in
  `RosterMatrixEditor.tsx` (a `createPortal` with a manually positioned `fixed` box and a search
  input, around line 1225).

## Decision for this issue

- **Radix UI primitives** (`@radix-ui/react-dialog`, `-alert-dialog`, `-dropdown-menu`,
  `-popover`, `-tooltip`, `-tabs`, `-select`, `-toggle-group`, `-scroll-area`) wrapped in
  `frontend/components/ui/`. Generate the wrappers with the shadcn/ui CLI as a starting point if it
  helps, then own them. shadcn is not a runtime dependency.
- **Combobox** for member pickers: `cmdk` (also used by the command palette in #115).
- **Design tokens** as CSS variables in `globals.css` (`--color-surface`, `--color-surface-muted`,
  `--color-border`, `--color-text`, `--color-text-muted`, `--color-accent` (mint),
  `--color-danger` (coral), `--color-warning`, `--color-info`, `--radius-sm/md/lg`,
  `--space-cell-x`, `--space-cell-y`, `--font-size-cell`), mapped in `tailwind.config.ts` so
  classes read `bg-surface`, `text-muted`, `border-default`, `text-danger`.
- **Severity colors are tokens**: `info`, `warning`, `error` map to one set of tokens used by
  validation badges, grid cell highlights and the inspector. Today the same meaning is expressed by
  several different Tailwind classes (see `inlineValidationBadgeClass` and
  `inlineValidationRowClasses` in `PlanningWorkspace.tsx`).
- **Density**: a `data-density="compact|comfortable"` attribute on `<html>` switches the cell
  and table spacing tokens. Default `comfortable`. The toggle UI comes in #115; the tokens and
  attribute come here.
- **No dark mode** in this issue. Tokens make it possible later.

## Scope

1. Install the Radix packages and `cmdk`. Add `frontend/components/ui/` with: `Dialog`,
   `AlertDialog` (for destructive confirmations), `DropdownMenu`, `Popover`, `Tooltip`, `Tabs`,
   `Select`, `Combobox` (cmdk inside a Popover), `Button` (variants primary, secondary, ghost,
   danger; sizes sm, md), `Badge` (severity variants), `Input`, `Textarea`, `Kbd`.
   Every component forwards refs, accepts `className`, and uses tokens only.
2. Tokens in `globals.css` and `tailwind.config.ts` as described above.
3. Migrate every hand-rolled dialog in the 14 files to `Dialog` or `AlertDialog`. Destructive
   confirmations (delete month, regenerate roster, delete template, remove membership) use
   `AlertDialog`.
4. Migrate the `AppShell` user and organization menus and `PlanningPeriodStatusMenu` to
   `DropdownMenu`.
5. Migrate the roster cell picker in `RosterMatrixEditor.tsx` to `Popover` + `Combobox`, keeping
   its current behaviour: search, clear assignment, show wish and no-go hints, show fairness
   deviation, save on pick, restore on failure.
6. Vitest + Testing Library tests for each `ui/` component's keyboard behaviour (open, close
   with `Escape`, focus return, arrow navigation in menus and combobox).
7. Document the component inventory and the token list in a short `frontend/components/ui/README.md`.

## Out of scope

- Restyling pages or changing layouts. Pages should look the same, apart from the dialog and menu
  chrome, which will look consistent now.
- Replacing all 966 raw palette classes. Do it for code you touch in this issue. New code uses
  tokens (the `AGENTS.md` rule).
- Dark mode, command palette, inspector.

## Acceptance criteria

- [ ] `frontend/components/ui/` exists with the listed components, each with keyboard tests.
- [ ] No `fixed inset-0` overlay remains in `frontend/components/` outside `components/ui/`
      (`grep -rn "fixed inset-0" frontend/components | grep -v components/ui` is empty).
- [ ] Every destructive confirmation uses `AlertDialog`.
- [ ] The roster cell picker is a `Popover` + `Combobox` with unchanged behaviour. The Playwright
      roster assignment flow from #110 passes unchanged.
- [ ] Golden screenshots from #110 either match or each changed baseline is justified in the PR
      (dialog chrome only).
- [ ] `data-density` switches cell spacing tokens (unit test on computed style is enough).
- [ ] `npm run lint`, `npm run typecheck`, `npm run build`, `npm run test`, `npm run test:e2e`
      green.

## Dependencies

Needs #110. Blocks #114, #115, #117.

## Implementation prompt

```text
You are working in the `aegis301/shift-planner` repository.
Start from the latest `main`: `git fetch origin && git switch -c feat/ui-foundation origin/main`.
Do not continue on a branch from another issue.

Read these before writing any code, and follow them strictly:
1. `AGENTS.md`, especially **Working an issue**, **Style → Frontend surfaces** and **Testing Expectations**.
2. `docs/rollout/STATE.md`, especially **Traps this project has already hit**.
3. `docs/decisions/0001-desktop-first-workbench.md`.
4. This issue's spec in full: `docs/workbench/issues/04-ui-foundation.md`.

Standing rules that matter most here:
- Every user-visible string exists in both dictionaries in `frontend/lib/i18n.ts` (key parity is
  type-checked). Components in `components/ui/` take their labels as props; they never import
  the dictionary themselves.
- Update `README.md`, `CHANGELOG.md`, `AGENTS.md` and `docs/rollout/STATE.md` in the same change.
- Before you finish: `cd frontend && npm run lint && npm run typecheck && npm run build && npm run test && npm run test:e2e`.

Task: add Radix-based UI primitives and design tokens, and migrate every hand-rolled dialog and
menu onto them. This is a behaviour-preserving refactor.

1. Run the Playwright suite from #110 on a clean `main` and confirm it is green before you
   change anything. If it is not green, stop and report.
2. Add tokens and the `components/ui/` primitives with keyboard tests.
3. Migrate dialogs file by file, one commit per file, running `npm run test:e2e` after each file
   that has an e2e flow. Keep each dialog's content, validation and submit behaviour identical.
4. Migrate the menus and the roster cell picker.
5. Update screenshot baselines only where the dialog or menu chrome changed, and list each updated
   baseline with a one-line reason in the PR.

Do not change: page layouts, the planning workflow, API calls, i18n keys beyond adding labels the
primitives need (for example "Close").

Stop and report instead of guessing if: a dialog's behaviour depends on the hand-rolled overlay in
a way the primitive cannot reproduce (for example a dialog that must stay open on outside click
while a nested picker is used). Describe the case and propose an approach before implementing it.

Prove it: walk the acceptance criteria one by one in the PR and name the test, command output or
CI run that proves each.
```
