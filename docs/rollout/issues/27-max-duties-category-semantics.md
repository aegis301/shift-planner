---
title: "R1 defect: WORKTIME_MAX_DUTIES counts every assignment, not on-call duties"
labels: rollout-r1, backend, compliance, bug
---

## Context

Found by the CP-SAT spike (#25, finding 3) while trying to linearize the rule.

`MaxDutiesPerPeriodRule.evaluate` in `backend/app/services/rules/statutory.py` iterates
`state.assignments_by_id.values()` with **no category filter**. Spätdienst and Rufdienst
therefore count as "Dienste" against the limit.

TV-Ärzte (TdL) § 7 Abs. 5a limits **Bereitschaftsdienste** — four per month with one additional
per quarter. Spätdienst is Regelarbeitszeit and is not a Dienst in that sense.

This is not a solver problem. **The rule has been reporting wrong numbers since #9 shipped**,
in both the validation warnings and the compliance report. The spike also showed the
consequences downstream: as a cheap penalty the rule does not bind, and as a hard cap on the
`tight` fixture it leaves 14 holes (14 people × 5 allowed).

## Scope

- Add a `categories` parameter to the `max_duties_per_period` rule type: the shift template
  categories that count toward the limit. Default and preset value for TdL:
  `["bereitschaftsdienst"]`.
- Filter by `slot.shift_template.category` — or the stored `TimeEntry.shift_template_category`
  where that is the cheaper read — in `evaluate`.
- Update the TdL preset (#10) to carry the category scope, with a `source_note` naming
  § 7 Abs. 5a.
- Migration for existing rule sets: add the field with the on-call default rather than leaving
  it null, and note in `CHANGELOG.md` that previously reported counts were too high.

## Out of scope

The CP-SAT encoding. Once the semantic is correct, #20 can decide whether to linearize it or
leave it post-solve — that decision belongs there.

## Acceptance criteria

- [ ] A member with 4 Bereitschaftsdienste plus 6 Spätdienste in one month produces **no**
      `WORKTIME_MAX_DUTIES` finding.
- [ ] A member with 5 Bereitschaftsdienste produces one.
- [ ] The quarterly allowance still applies on top.
- [ ] Existing rule sets migrate to the on-call default and a test asserts the counts change
      for a fixture that previously over-reported.
- [ ] The TdL preset carries the category scope and its `source_note`.
- [ ] The compliance report reflects the corrected counts.

## Dependencies

None. Should land before #20 decides what to do with the rule, and before #26, which seeds
several orgs.

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

Task: fix the counting semantic of the `max_duties_per_period` statutory rule.

1. Read `docs/rollout/solver-spike-findings.md` (finding 3) and
   `backend/app/services/rules/statutory.py`, class `MaxDutiesPerPeriodRule`. The loop over
   `state.assignments_by_id.values()` has no category filter — that is the defect.
2. Add a `categories` field to the rule's typed payload in `backend/app/schemas/domain.py`,
   defaulting to `["bereitschaftsdienst"]`, and filter on it in `evaluate`.
3. Update the TdL preset in `backend/app/services/work_time_preset_catalog.py` with the scope
   and a `source_note` naming "§ 7 Abs. 5a TV-Ärzte (TdL)".
4. Write the Alembic migration so existing stored rule sets get the on-call default rather than
   a null. Add a test that seeds a rule set on the old shape, migrates, and asserts the reported
   count changes for a member with mixed duty categories.
5. This rule feeds both `GET /api/v1/validation/{id}` and the compliance report. Check both
   surfaces and add a regression test for the report.
6. Add a dated `CHANGELOG.md` entry stating plainly that counts reported before this fix were
   too high, so anyone who looked at an old report knows.
7. Do NOT add a `to_cpsat` for this rule. That decision belongs to #20.
```
