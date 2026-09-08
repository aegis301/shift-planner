---
title: "R1: Record call-outs and in-duty activity as duty activity episodes"
labels: rollout-r1, backend, compliance
---

## Context

Two facts are captured nowhere:

1. **Rufbereitschaft call-outs.** Stand-by time is not working time, but every call-out is.
   Without this record every statutory calculation is systematically too low.
2. **Work during a Bereitschaftsdienst.** TV-Ärzte grades on-call duty by measured work:
   Stufe I at 0–25 % (60 % credit), Stufe II at over 25–49 % (95 %), and above 49 % it is no
   longer on-call duty but full work. Today the grading rests on assertion.

These are the same thing — an episode of work inside a duty, with a start and an end — and must
be one mechanism.

## Scope

- Activate the `call_out` and `in_duty_activity` kinds reserved in #06. Both require
  `roster_slot_id`, `started_at`, `ended_at`, and carry an optional structured reason.
- `call_out` contributes statutory working time and interrupts the rest period.
- `in_duty_activity` contributes to a utilization ratio and adds no statutory time — the whole
  Bereitschaftsdienst already counts at `statutory_factor` 1.0.
- `backend/app/services/duty_utilization.py`:
  - per slot: `worked_minutes / duty_minutes`, the implied tariff band, and an explicit
    `exceeds_on_call_threshold` flag
  - per template and period: aggregate ratio plus **coverage** — the share of duties with any
    record, so thin data is visible as thin rather than reported as a result
- Band thresholds come from the rule set, not from constants — TdL and VKA differ.
- REST for own episodes, aggregates for planners and admins. MCP read resource plus guarded tool.

## Out of scope

Capture UI (#13), visibility and retention controls (#14), import from clinical systems.

## Acceptance criteria

- [ ] A call-out on a Rufbereitschaft slot appears as statutory working time and shortens the
      following rest period.
- [ ] A Bereitschaftsdienst with recorded activity reports a utilization percentage and band.
- [ ] A duty above 49 % measured utilization is flagged with a distinct field, not merely a
      different percentage.
- [ ] Every aggregate response includes coverage alongside the ratio.
- [ ] Episodes cannot be recorded against a slot the member is not assigned to.
- [ ] Overlapping episodes on the same slot are rejected.

## Dependencies

Blocked by #06, #07. Consumed by #09 (rest interruption) and #16.

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

Task: add duty activity episodes — Rufbereitschaft call-outs and in-duty work — as one
mechanism on the `TimeEntry` ledger from #06.

1. Activate the reserved `call_out` and `in_duty_activity` kinds. Both require
   `roster_slot_id`, `started_at` and `ended_at`; `all_day` is invalid. Validate that the
   episode falls inside the slot's span and that the member is the slot's assignee. Reject
   overlapping episodes on the same slot.
2. `call_out` sets `counts_toward_contract` per the contract group's `call_outs_count_as_work`
   and feeds `statutory_work_minutes`. `in_duty_activity` adds no statutory time.
3. Create `backend/app/services/duty_utilization.py` with the per-slot and aggregate functions
   above. Read band thresholds from the active rule set.
4. Always return coverage next to any aggregate ratio. An aggregate over 3 of 40 duties must be
   visibly that, so no caller can present it as a measured result.
5. REST under `/api/v1/duty-activity`: a member manages their own episodes; planners and admins
   read aggregates only — individual access is gated in #14, so do not expose it here.
6. MCP: `shift-planner://duty-utilization/{planning_period_id}` resource and a guarded
   `record_duty_activity_tool`.
7. Tests: statutory contribution of a call-out, rest interruption, utilization bands including
   the >49 % flag, coverage reporting, assignment and overlap validation.
8. Update `README.md`, `AGENTS.md`, `CHANGELOG.md`.
```
