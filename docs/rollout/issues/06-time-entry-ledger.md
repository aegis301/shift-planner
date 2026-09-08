---
title: "R1: Add the time entry ledger"
labels: rollout-r1, backend, schema, compliance
---

## Context

`main` models assignments to slots, not time. Statutory limits, the time account and the
fairness dimensions all need a ledger of actual minutes, derived from the roster but
correctable by hand and extensible with the episodes from #12.

## Scope

**`TimeEntry`**: `organization_id`, `team_member_id`, `entry_date`, `kind`, `source`,
`all_day`, `started_at`, `ended_at`, `duration_minutes`, `counts_toward_contract`,
`shift_template_category`, `planning_day_status_code`, `roster_slot_id | null`, `comment`.

- `kind`: `work`, `absence` in this issue; `call_out` and `in_duty_activity` are added by #12.
  Define the enum so those two slot in without a migration.
- `source`: `roster` (derived from an assignment), `day_status` (derived from a wishes-matrix
  cell via the contract group's `status_mappings`), `manual`.
- Derivation: a service that materializes `roster` and `day_status` entries for a member and
  window, idempotently, preserving `manual` entries and manual corrections to derived ones.
  Re-running derivation must never silently discard a correction.
- Reconciliation view: derived vs. corrected, so a planner can see where the ledger diverges
  from the roster.

REST for own entries (member) and scoped reads (planner/admin), MCP resource plus guarded tool.

## Out of scope

Duty activity episodes (#12), valuation (#07), the ledger UI (#15).

## Acceptance criteria

- [ ] Re-running derivation for a window is idempotent and preserves manual corrections.
- [ ] Removing a roster assignment removes or supersedes its derived entry, and a test covers it.
- [ ] A day status mapped to `vacation` produces an all-day absence entry with
      `consumes_vacation` respected.
- [ ] Entries are queryable by member and date range across planning periods in one query.
- [ ] A member cannot write an entry for another member.
- [ ] Adding `call_out` and `in_duty_activity` later requires no migration.

## Dependencies

Blocked by #05.

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

Task: build the time entry ledger.

1. Model `TimeEntry` as described. Index `(team_member_id, entry_date)` and `roster_slot_id` —
   every downstream consumer queries by member and date range across planning periods, so this
   index is load-bearing, not an optimization.
2. Define `kind` as a string column with a validated Literal in the schema layer, listing
   `call_out` and `in_duty_activity` from the start so #12 needs no migration.
3. Write `backend/app/services/time_entries.py` with:
   - `derive_entries(db, *, member_ids, start_date, end_date)`: materializes `roster` entries
     from `RosterSlotAssignment` and `day_status` entries from `PlanningCell` via the contract
     group's `status_mappings`.
   - Idempotency: derivation is a reconcile, not an insert. Match existing derived entries by
     (member, date, source, roster_slot_id), update in place, remove derived entries whose
     source is gone, and never touch `manual` entries or fields a user has corrected. Track
     corrections explicitly rather than inferring them.
4. Add a reconciliation read that returns derived vs. effective values for a window so a
   planner can see divergence.
5. REST: members manage their own entries; planners and admins read within their shift-group
   scope. Follow the existing `team_member_portal=true` convention used by the roster and
   matrix routes for the self-scoped path.
6. MCP: `shift-planner://time-entries/{team_member_id}` read resource and a guarded
   `upsert_time_entry_tool`.
7. Tests: idempotent re-derivation, correction preservation, assignment removal, day-status
   absence mapping, cross-period range query, authorization.
8. Update `README.md`, `AGENTS.md`, `CHANGELOG.md`.
```
