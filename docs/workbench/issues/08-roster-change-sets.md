---
title: "Roster change sets: atomic bulk assignment writes with per-row results and revert"
labels: backend, mcp, schema, architecture
---

## Context

Part of ADR 0001 (`docs/decisions/0001-desktop-first-workbench.md`, decision 5). The workbench
grid (#117) needs to paste a range of assignments and to undo. The backend can do neither
properly today.

What exists on `main`:

- The only roster write is one slot at a time: `PUT /api/v1/roster-matrix/assignments` and
  `POST /api/v1/roster-matrix/assignments/clear` (`backend/app/api/v1/roster_matrix.py`), backed by
  `upsert_roster_slot_assignment` and `clear_roster_slot_assignment` in
  `backend/app/services/roster_matrix.py`.
- Each upsert with the defaults (`commit=True`, `enforce_preflight=True`):
  1. checks period roster membership and `team_member_may_cover_template`,
  2. refuses a template no-go unless `manual_override`,
  3. builds a full `PlanState` for the slot date (`_preflight_assignment_warnings`), overlays the
     candidate, evaluates every rule, and refuses on `error`,
  4. commits,
  5. calls `refresh_derived_window`, which runs `derive_entries` and **commits again**
     (`backend/app/services/time_entries.py`, `db.commit()` around line 339).
  So a paste of 40 cells would be 40 `PlanState` builds, 80 commits, and a half-applied roster if
  cell 23 is refused.
- The solver apply has exactly that defect today: `apply_solver_run`
  (`backend/app/services/solver_runs.py`, around line 264) loops over proposed assignments and
  calls `upsert_roster_slot_assignment` for each. A refusal part-way through leaves earlier
  assignments committed and `run.applied_at` unset.
- Swap apply (`backend/app/services/shift_swaps.py`) already writes with `commit=False,
  enforce_preflight=False` after its own legality check, then commits once. That is the pattern
  to generalize.
- `AuditLog` (`backend/app/models/entities.py`, around line 1021) stores `actor`, `source`,
  `action`, `entity_type`, `entity_id`, `details`. It has no `organization_id` and does not store
  the previous assignee, so it cannot drive an undo.
- `overlay_candidate_assignment` (`backend/app/services/rules/shift_constraints.py`, line 274)
  overlays one candidate on a `PlanState`. `_overlay_proposed` in
  `backend/app/services/solver/solve.py` overlays many. There is no overlay for clearing a slot.

## Decision for this issue

**Model.** Two new tables:

- `roster_change_sets`: `id`, `organization_id`, `planning_period_id`, `shift_group_id`
  (nullable for admin full-org edits), `created_by_user_id` (nullable for MCP), `actor`, `source`
  (`ui`, `mcp`, `solver`, `swap`, `revert`), `mode` (`all_or_nothing` / `best_effort`), `status`
  (`applied`, `refused`, `partially_applied`, `reverted`), `reverts_change_set_id` (nullable FK),
  `label` (optional, for example "Paste 12 cells"), `created_at`.
- `roster_change_set_items`: `id`, `change_set_id`, `roster_slot_id`, `before_team_member_id`,
  `after_team_member_id` (null means clear), `before_manual_override`, `after_manual_override`,
  `before_comment`, `after_comment`, `outcome` (`applied`, `refused`, `unchanged`), `findings`
  (JSON list of `ValidationWarning`), `refusal_code` (nullable).

**Service** `backend/app/services/roster_change_sets.py`:

- `apply_roster_change_set(db, *, organization_id, planning_period_id, shift_group_id, items,
  mode, actor, source, created_by_user_id, label=None) -> RosterChangeSet`
  1. Load all target slots in one query. Refuse the whole set with 409 if any target shift group is
     `published` (same rule as regenerate and sync).
  2. Per item, run the non-rule checks (slot in org and period, member on the period roster for
     the slot's group, `team_member_may_cover_template`, template no-go unless `manual_override`).
     Failures become `refused` items with a `refusal_code`.
  3. Build **one** `PlanState` for the date window spanning all target slots (the builder widens
     it by the rules' lookbacks). Overlay every surviving change at once, including clears (add an
     overlay helper for clearing a slot next to `overlay_candidate_assignment`). Evaluate once.
     Attribute findings to items with the same targeting logic preflight uses
     (`_warning_targets_slot`).
  4. `all_or_nothing`: any refused item or any `error` finding refuses the whole set. Nothing is
     written. `best_effort`: drop items with `error` findings, re-overlay and re-evaluate the rest,
     repeat until stable (cap at 3 passes; if still unstable, refuse the remainder and say so).
  5. Write surviving items with `upsert_roster_slot_assignment(..., commit=False,
     enforce_preflight=False)` / the clear equivalent, store before and after values, store
     `warning` and `info` findings on the items.
  6. Refresh derived time entries for the union of affected members and dates **inside the same
     transaction**. Add a `commit: bool = True` parameter to `derive_entries` and
     `refresh_derived_window` and pass `False`.
  7. One `record_audit` for the set with the item count. Commit once.
- `revert_roster_change_set(db, change_set_id, *, organization_id, actor, source, ...)`: builds a
  new change set whose items restore `before_*` values, **only for items whose slot still has the
  `after_*` value**. Items changed since are `refused` with `refusal_code = "changed_since"`.
  Default mode `all_or_nothing`. Marks the original `reverted` when the revert applies fully.
  Reverting a revert is allowed (that is redo).
- `list_roster_change_sets(db, planning_period_id, shift_group_id, limit=50)` newest first, for
  the undo stack and the inspector's slot history.

**Single-cell writes use it too.** `PUT /assignments` and `POST /assignments/clear` go through a
one-item `all_or_nothing` change set, so every manual edit is undoable. The existing response
stays; add an optional `change_set_id` to `RosterSlotAssignmentRead` and to the clear response.
Existing error messages and status codes stay identical (the existing API tests must pass
unchanged).

**Solver apply uses it.** `apply_solver_run` builds one change set with `source = "solver"`. Mode
follows a new optional request field `mode` (default `best_effort`, because a solver proposal that
went stale while queued should still apply what is still legal). `run.applied_at` is set only when
the set is `applied` or `partially_applied`, and the run stores `change_set_id`.

**REST** (`backend/app/api/v1/roster_matrix.py`, planner scope checks as the existing routes):

- `POST /api/v1/roster-matrix/{planning_period_id}/change-sets?shift_group_id=` body
  `{ mode, label?, items: [{ roster_slot_id, team_member_id | null, manual_override?, comment? }] }`
  returns the change set with items. `200` when applied or partially applied, `409` when refused,
  with the same body so the client can show per-row reasons.
- `GET /api/v1/roster-matrix/{planning_period_id}/change-sets?shift_group_id=&limit=`
- `POST /api/v1/roster-matrix/change-sets/{change_set_id}/revert`

**MCP**: resource `shift-planner://roster-change-sets/{planning_period_id}/shift-group/{shift_group_id}`,
token-gated `apply_roster_change_set_tool` and `revert_roster_change_set_tool`.

Limits: at most 500 items per set (422 above that).

## Scope

Everything in the decision section, plus:

- Alembic migration for both tables and the new `solver_runs.change_set_id` column.
- pytest: all-or-nothing refusal writes nothing; best-effort applies the legal subset; two items in
  the same set that conflict with each other (same member, overlapping slots) are both flagged;
  clear plus assign in one set; revert restores; revert refuses changed-since items; redo; single
  PUT creates a one-item set and keeps its old response; published group refused; planner scope;
  derived `TimeEntry` rows are consistent after one commit (assert no intermediate commit with a
  session event counter); solver apply with one stale proposal applies the rest.
- A timing test: 100 items on the `comfortable` fixture month apply in one `PlanState` build (assert
  the builder is called once).
- MCP tests for both tools, including token enforcement.

## Out of scope

- Any frontend change (#117 consumes this).
- Change sets for wishes cells (wishes have no legality check; #118 handles undo client-side
  with the existing bulk endpoints).
- Rewriting swap apply onto change sets (possible later; it already commits once).

## Acceptance criteria

- [ ] Tables, migration, service, REST, MCP as specified. Migration verified against Postgres with
      pre-existing solver runs and assignments (paste the run in the PR).
- [ ] Every scenario in the pytest list above exists and passes.
- [ ] `apply_roster_change_set` builds `PlanState` exactly once per pass (asserted).
- [ ] The existing roster, solver and swap API tests pass without modification.
- [ ] A refused `all_or_nothing` set leaves no assignment, audit row or time entry change behind.
- [ ] `AGENTS.md` documents change sets under a new heading next to **Solver runs**, and the
      solver apply section is updated.
- [ ] `ruff check app`, `pytest`, MCP tests green.

## Dependencies

None. Blocks #117. Can run in parallel with #110 to #115.

## Implementation prompt

```text
You are working in the `aegis301/shift-planner` repository.
Start from the latest `main`: `git fetch origin && git switch -c feat/roster-change-sets origin/main`.
Do not continue on a branch from another issue.

Read these before writing any code, and follow them strictly:
1. `AGENTS.md`, especially **Working an issue**, **Rule evaluation layer**, **Solver runs**, **Shift swaps** and **Testing Expectations**.
2. `docs/rollout/STATE.md`, especially **Decisions already made** and **Traps this project has already hit**.
3. `docs/decisions/0001-desktop-first-workbench.md`.
4. This issue's spec in full: `docs/workbench/issues/08-roster-change-sets.md`.

Standing rules that matter most here:
- Business logic lives in typed service functions under `backend/app/services/`, never in route
  handlers.
- Every capability is reachable from REST and MCP (`mcp-server/mcp_app/server.py`). Mutating MCP
  tools require `MCP_ADMIN_TOKEN`.
- `PlanState` is built from a date window, never a `planning_period_id`.
- Schema changes ship with a forward-only Alembic migration. `pytest` never runs Alembic; verify
  the migration by hand against Postgres and paste the run in the PR.
- Update `README.md`, `CHANGELOG.md`, `PLAN.md`, `AGENTS.md` and `docs/rollout/STATE.md` in the same change.
- Before you finish: `cd backend && ruff check app && pytest` and `cd mcp-server && pytest`.

Task: add roster change sets: atomic, evaluated-once bulk assignment writes with per-row results
and revert, and route single-cell writes and solver apply through them.

1. Read `upsert_roster_slot_assignment`, `clear_roster_slot_assignment`,
   `_preflight_assignment_warnings` and `_warning_targets_slot` in
   `backend/app/services/roster_matrix.py`; `apply_solver_run` in
   `backend/app/services/solver_runs.py`; the apply path in `backend/app/services/shift_swaps.py`;
   `derive_entries` and `refresh_derived_window` in `backend/app/services/time_entries.py`.
2. Before changing production code, write a golden test that records the exact status codes and
   error messages of the existing single-cell PUT and clear for: success, not on period roster,
   template no-go, blocking rule, published group. Commit it first. It must still pass at the end.
3. Add the models and migration. Add the clear-overlay helper next to
   `overlay_candidate_assignment`. Add `commit` to `derive_entries` / `refresh_derived_window`.
4. Implement the service, then REST, then MCP, each with its tests.
5. Route the single-cell endpoints and `apply_solver_run` through the service.
6. Verify the migration on Postgres and paste the run.

Do not change: rule evaluation logic, the swap state machine, any frontend file, the single-cell
endpoints' existing response fields and error messages.

Stop and report instead of guessing if: evaluating the whole overlaid set once produces a
different verdict for an item than preflight would for that item alone, in a case where the other
items do not involve the same member. That would mean findings are attributed wrongly, which needs
a decision on attribution before you continue.

Prove it: walk the acceptance criteria one by one in the PR and name the test or pasted run that
proves each.
```
