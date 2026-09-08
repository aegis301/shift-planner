---
title: "R1: Compliance report and audit export"
labels: rollout-r1, backend, frontend, compliance
---

## Context

The statutory rules produce findings during planning. An organization also needs a report for a
closed period: what the working time was, which limits were approached or breached, and under
which rule-set version it was assessed.

## Scope

Per member and period: statutory working time and tariff credit side by side; rolling weekly
average against the applicable cap with its source (base or opt-out tier, and the consent that
established it); rest violations with compensation status; consecutive working days; duty counts
against limits; documentation coverage; and the **rule-set version** used, printed on the report.

XLSX and PDF through the existing export layer; MCP read resource; a report view in the planning
workspace.

## Acceptance criteria

- [ ] The report reproduces exactly the findings the evaluation engine reports for the same
      window — no second implementation of any rule.
- [ ] The rule-set version is stated on every export.
- [ ] Re-running for a closed month produces identical output.
- [ ] Access follows the existing shift-group scope rules; planners are limited to their groups.

## Dependencies

Blocked by #09, #11.

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

Task: build the compliance report and its exports.

1. The report calls the rule layer; it must not reimplement any rule. If a number cannot be
   obtained from `services/rules/`, that is a gap in the rule layer to fix there.
2. Add `backend/app/services/compliance_report.py` producing a typed per-member structure with
   the fields above for a date window and shift group.
3. Add XLSX and PDF renderers in `backend/app/services/exports.py`, reusing the roster export
   layout conventions and `services/export_colors.py`. Print the rule-set version and generation
   timestamp in the header.
4. REST under `/api/v1/compliance-report/{planning_period_id}` following the existing
   `shift_group_id` scope rules — admins may omit it, planners must pass one of their groups.
5. MCP read resource `shift-planner://compliance-report/{planning_period_id}`.
6. Frontend: a report view in the planning workspace next to the analysis tab. DE and EN strings.
7. Tests: parity with engine findings for a fixture month, version pinning, determinism on
   re-run, planner scope enforcement.
8. Update `README.md`, `AGENTS.md`, `CHANGELOG.md`, `PLAN.md`.
```
