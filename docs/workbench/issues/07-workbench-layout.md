---
title: "Workbench layout: context bar, inspector panel, command palette and density"
labels: frontend, backend, ux
---

## Context

Part of ADR 0001 (`docs/decisions/0001-desktop-first-workbench.md`, decision 2). After #114
the planner has a desktop shell. This issue gives it the three things a desktop allows that a phone
does not: persistent context, detail next to the work instead of on top of it, and keyboard reach.

What exists on `main` (after #114):

- Period and shift group are chosen in a toolbar inside the planner workspace and mirrored in the
  URL (`?period=`, `?shiftGroup=`; see `updateShiftGroup` in the old `PlanningWorkspace.tsx`
  around line 454). Plan status is changed through `PlanningPeriodStatusMenu`.
- Detail is shown in modals: the member workload and fairness modal in `RosterMatrixEditor.tsx`
  (`workloadModalMemberId`, around line 1034), notes and comment modals in `MatrixEditor.tsx`,
  the solver dialog, the swap offer dialog.
- The roster cell picker (a `Popover` + `Combobox` after #112) shows, per candidate, wish and
  no-go hints, day status and fairness deviation. It computes those hints **in the browser** from
  the roster matrix payload (`RosterMatrixRead`: `team_members`, `slots`, `assignments`,
  `planning_cells`, `shift_intents`, `day_status_definitions`) plus the fairness payload. It does
  **not** know which candidates would violate a rule. The planner finds out only after saving,
  when `upsert_roster_slot_assignment` refuses (`backend/app/services/roster_matrix.py`, preflight
  via `_preflight_assignment_warnings`).
- The backend can already answer "who may take this slot and what would it break":
  `eligible_members_for_slots` in `backend/app/services/solver/model.py` (masks plus mask-phase
  `to_cpsat`), and `overlay_candidate_assignment` + `evaluate_plan_state` as used by preflight and
  swap legality. `STATE.md` records that evaluating every (slot, member) pair for a whole month
  takes 40 to 60 s. For **one** slot and only the eligible members it is cheap enough.
- There is no keyboard shortcut anywhere in the app and no command palette.

## Decision for this issue

**Layout of `/planning`** (and reused by `/hours` and the analysis views):

```
┌ WorkbenchShell sidebar ┬──────────────────────────────────────────────┬──────────────┐
│                        │ Context bar: period ▾  group ▾  status ▾  … │              │
│                        ├──────────────────────────────────────────────┤  Inspector   │
│                        │ Tabs: Wishes | Roster | Analysis             │  (360-440px, │
│                        │                                              │  resizable,  │
│                        │ main view (matrix, analysis panels)          │  collapsible)│
└────────────────────────┴──────────────────────────────────────────────┴──────────────┘
```

- **Context bar** (`components/workbench/ContextBar.tsx`): period select, shift group select,
  plan status with the transition menu, plan version indicator, and a right-aligned slot for page
  actions (solver, exports, sync, regenerate). All state is in the URL: `?period=`,
  `?shiftGroup=`, `?tab=`, `?slot=` (selected roster slot), `?member=` (selected member),
  `?day=` (selected day). Reload and shared links restore the exact view.
- **Inspector** (`components/workbench/Inspector.tsx`): shows detail for the current selection.
  Selection kinds and their panels:
  - **Roster slot**: slot facts (template, variant, times in org time zone, day class); current
    assignee; **candidate list** from the new endpoint below, grouped "can take it", "can take it
    with warnings", "blocked", each with the findings that decide it, plus wish or no-go, day
    status and fairness deviation; assignment history for the slot from the audit log; swap
    requests touching the slot. Assigning from the candidate list is the same mutation as the
    picker.
  - **Member** (column header or row): employment and contract group, period workload, fairness
    actual / expected / deviation per dimension (what the workload modal shows today), consents,
    open swap requests, monthly note.
  - **Day**: holiday and day class, slots of the day with fill state, wishes and statuses of the
    day.
  - **Validation finding**: the finding with its rule code, the affected slots and members as
    links that change the selection.
  The workload modal in `RosterMatrixEditor` and the member note modal in `MatrixEditor` become
  inspector panels. Destructive confirmations stay `AlertDialog`s.
- **Command palette** (`components/workbench/CommandPalette.tsx`, `cmdk`), opened with
  `Ctrl+K` / `Cmd+K`: go to page, go to member (opens inspector), go to date, switch period, switch
  shift group, run solver, publish, set preliminary, export. Actions respect capabilities and
  plan status exactly as the buttons do (disabled with a reason, not hidden).
- **Shortcuts** registry (`lib/shortcuts.ts`): one place that declares key, scope and label, used
  by the palette and by a `?` help overlay. Initial set: `Ctrl/Cmd+K` palette, `?` help, `[` / `]`
  previous / next period, `g w` / `g r` / `g a` tabs, `i` toggle inspector, `Esc` clear selection.
  Grid navigation keys come in #117.
- **Density toggle** in the user menu, stored per user in `localStorage` key
  `shift-planner-density`, applied through the `data-density` attribute from #112.

**New backend endpoint** for the inspector's candidate list:

`GET /api/v1/roster-matrix/{planning_period_id}/slots/{roster_slot_id}/candidates?shift_group_id=`

- Service `list_slot_candidates(db, slot_id, *, organization_id, shift_group_id)` in
  `backend/app/services/roster_matrix.py` (or a new `roster_candidates.py`).
- Candidates are the period roster members for the slot's group. For each: `eligible` (from
  `eligible_members_for_slots`), and for eligible ones the findings from overlaying the candidate on
  **one** `PlanState` built for the slot's date window and evaluating it once per candidate,
  filtered with the same `_warning_targets_slot` logic preflight uses. Build the `PlanState` once,
  not per candidate.
- Response per candidate: `team_member_id`, `status` (`ok` / `warning` / `blocked` /
  `ineligible`), `findings` (list of `ValidationWarning`), `wish` / `no_go` flags, `day_status`,
  `fairness_deviation` for the slot's dimensions (reuse the payload the picker already reads),
  `is_current_assignee`.
- Planner scope checks exactly as the roster matrix route. MCP read tool
  `get_slot_candidates_tool` with the same service.
- Performance budget: under 1.5 s for any slot of the `comfortable` fixture month on a laptop,
  asserted loosely in a pytest (skip on CI if flaky, but log the timing).

## Scope

1. Backend endpoint, service, MCP tool, pytest (status per candidate on the `tight` fixture,
   planner scope, timing log).
2. Context bar, inspector with the four selection kinds, URL state.
3. Move the workload modal and member note modal into inspector panels.
4. Command palette, shortcut registry, help overlay.
5. Density toggle.
6. Apply the same layout to `/hours` (member list in the main area, ledger in the inspector).
7. Playwright: select a slot, see candidates grouped with findings, assign from the inspector,
   deep link with `?slot=` restores the selection, palette opens with the shortcut and switches
   period, density toggle persists across reload.

## Out of scope

- Grid keyboard navigation, range selection, paste, undo (#117).
- Admin pages under `/organization/*` (they keep their current layout inside the new shell).
- Any change to rule evaluation.

## Acceptance criteria

- [ ] `GET .../slots/{id}/candidates` returns every period roster member with a status and
      findings; `blocked` matches what the assignment API would refuse. pytest compares the two
      for every member of one slot on the `tight` fixture.
- [ ] The endpoint builds `PlanState` once per request (assert with a counter or mock).
- [ ] MCP `get_slot_candidates_tool` returns the same payload (MCP test).
- [ ] Context bar, inspector and palette work as specified; every selection is in the URL.
- [ ] No modal remains for workload or member notes on `/planning`.
- [ ] Every palette action is disabled with a visible reason when the user lacks the capability or
      the plan status forbids it (test for planner vs admin, published vs draft).
- [ ] Both dictionaries. `ruff check app`, `pytest`, MCP tests, `npm run lint`,
      `npm run typecheck`, `npm run build`, `npm run test`, `npm run test:e2e` green.

## Dependencies

Needs #114 (and therefore #112, #113). Blocks #117. Benefits from #109 for correct
times in the slot facts.

## Implementation prompt

```text
You are working in the `aegis301/shift-planner` repository.
Start from the latest `main`: `git fetch origin && git switch -c feat/workbench-layout origin/main`.
Do not continue on a branch from another issue.

Read these before writing any code, and follow them strictly:
1. `AGENTS.md`, especially **Working an issue**, **Rule evaluation layer**, **Style → Frontend surfaces** and **Testing Expectations**.
2. `docs/rollout/STATE.md`, especially **Decisions already made** (eligibility comes from masks and
   `to_cpsat`, never from `evaluate()` over every pair) and **Traps this project has already hit**.
3. `docs/decisions/0001-desktop-first-workbench.md`.
4. This issue's spec in full: `docs/workbench/issues/07-workbench-layout.md`.

Standing rules that matter most here:
- Business logic lives in typed service functions under `backend/app/services/`, never in route
  handlers or React components. The candidate classification is backend logic.
- Every capability is reachable from the web UI, REST and MCP (`mcp-server/mcp_app/server.py`).
- `PlanState` is built from a date window, never a `planning_period_id`.
- Every user-visible string exists in both dictionaries in `frontend/lib/i18n.ts`.
- Update `README.md`, `CHANGELOG.md`, `PLAN.md`, `AGENTS.md` and `docs/rollout/STATE.md` in the same change.
- Before you finish: `cd backend && ruff check app && pytest`, `cd mcp-server && pytest`,
  `cd frontend && npm run lint && npm run typecheck && npm run build && npm run test && npm run test:e2e`.

Task: give the planner workbench a context bar, an inspector panel, a command palette and a
density setting, backed by a new slot-candidates endpoint.

1. Backend first. Read `_preflight_assignment_warnings`, `_warning_targets_slot` and
   `upsert_roster_slot_assignment` in `backend/app/services/roster_matrix.py`, and
   `eligible_members_for_slots` in `backend/app/services/solver/model.py`. Build the candidates
   service so its `blocked` verdict is exactly what the assignment API would refuse. Write the
   pytest that proves that equivalence for one slot on the `tight` fixture before the frontend.
2. Build the context bar with URL state, then the inspector with the four selection kinds, then
   move the two modals into it.
3. Build the shortcut registry, the palette and the help overlay.
4. Add the density toggle.
5. Apply the layout to `/hours`.
6. Write the Playwright tests.

Do not change: rule evaluation, the assignment API's behaviour, admin pages' layout, the solver
or swap state machines.

Stop and report instead of guessing if: the candidates endpoint cannot meet roughly 1.5 s on the
fixture without evaluating fewer rules, or its `blocked` verdict cannot be made identical to the
assignment API's refusal. Either needs a decision, not a workaround.

Prove it: walk the acceptance criteria one by one in the PR and name the test, command output or
CI run that proves each.
```
