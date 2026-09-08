---
title: "R1: Add versioned, org-scoped statutory rule sets"
labels: rollout-r1, backend, schema, compliance
---

## Context

`RuleConfig` exists on `main` as a table read by nothing, so statutory limits are enforced
nowhere. The numbers differ between ArbZG, TV-Ärzte (TdL), TV-Ärzte (VKA) and church-sector
agreements, so they must be configuration.

A published roster was legal under the rules in force when it was published. Rule sets must be
versioned and immutable once referenced.

## Scope

`WorkTimeRuleSet` (org-scoped, named, versioned, `is_active`) with typed rules:

| Type | Parameters |
|---|---|
| `max_daily_working_time` | `base_hours`, `extended_hours`, `extension_requires_duty_hours` |
| `min_rest_period` | `hours`, `reducible_to_hours`, `compensation_window_days`, `call_out_handling` |
| `rest_after_long_duty` | `trigger_hours`, `mandatory_rest_hours` |
| `weekly_average_cap` | `hours`, `reference_period_months`, `rolling` |
| `opt_out_weekly_cap` | `hours_by_tier`, `reference_period_months` |
| `max_consecutive_work_days` | `days` |
| `max_duties_per_period` | `count`, `period`, `additional_allowance_per_quarter` |
| `documentation_requirement` | `threshold_hours`, `retention_months` |

Each carries `severity` (`info` / `warning` / `error`) and a `source_note`. Editing a referenced
set creates version N+1; `PlanningPlanVersion` gains `work_time_rule_set_version_id`. CRUD REST
(admin only) plus MCP. `RuleConfig` is dropped in the same migration.

## Out of scope

Rule implementations (#09), presets (#10).

## Acceptance criteria

- [ ] Creating a set, referencing it from a published plan version, then editing it produces a
      new version and leaves the published plan pointing at the old one.
- [ ] Only one active rule set per organization; switching is explicit.
- [ ] `RuleConfig` is gone from models, migrations and every import.
- [ ] MCP read plus admin-token-guarded writes with the same payloads as REST.

## Dependencies

None — parallel to #05–#07.

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

Task: add versioned statutory rule sets and remove the dead `RuleConfig` table.

1. Read `backend/app/models/entities.py` (`RuleConfig`, `PlanningPlanVersion`) and
   `backend/app/services/plan_versions.py` for the existing snapshot conventions.
2. Model `WorkTimeRuleSet` with the typed rule payloads as a Pydantic discriminated union in
   `backend/app/schemas/domain.py`, following exactly how `ShiftConstraint` does it. Every rule
   carries `severity` and a `source_note`.
3. Enforce immutability in the service layer: if a set is referenced by any
   `PlanningPlanVersion`, an update creates version N+1 and deactivates the old one rather than
   mutating it.
4. Add `work_time_rule_set_version_id` to `PlanningPlanVersion` and record it when a plan
   version is created.
5. Write `backend/app/services/work_time_rule_sets.py` and a REST router registered in
   `router.py`. Admin-only writes; reads for any planning user.
6. MCP: `shift-planner://work-time-rule-sets` resource plus guarded create/update tools.
7. Remove `RuleConfig` from models and `models/__init__.py` and drop the table in the migration.
   Grep first to confirm nothing reads it.
8. Tests: version-on-edit, single active set, plan-version pinning, admin-only writes, MCP
   parity.
9. Update `README.md`, `AGENTS.md`, `CHANGELOG.md`, `PLAN.md`.
```
