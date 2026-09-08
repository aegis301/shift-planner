---
title: "R1: Visibility, retention and works-council export for duty activity data"
labels: rollout-r1, backend, frontend, compliance
---

## Context

A module recording per-person activity is a technical device under § 87 Abs. 1 Nr. 6 BetrVG.
Objective suitability to monitor behaviour or performance is sufficient; intent is not required.
Introduced without a works agreement, measures based on it are void and the data unusable as
evidence.

This is not a compliance afterthought — it is what makes the module adoptable in a hospital, and
it gates #13.

## Scope

- **Aggregate-first defaults.** Individual episodes are visible to the recording member. Every
  other role sees aggregates unless an explicit grant exists.
- `DutyActivityAccessPolicy` per organization: which roles may see individual episodes
  (default none), retention period, purpose statement text.
- **Retention**: configurable, with a purge job and an audit entry per run.
- **Works-council export**: aggregate utilization per duty type per period, no individual
  attribution, XLSX and PDF via the existing export layer, with small-group suppression.
- **Purpose statement** shown to members before first capture and on the admin page.
- Every access to individual episode data written to `AuditLog`.

## Acceptance criteria

- [ ] With default settings a planner requesting an individual member's episodes receives 403;
      aggregates succeed.
- [ ] Granting individual access is an explicit, audited admin action.
- [ ] Episodes past retention are removed by the purge job and the run is logged.
- [ ] The works-council export contains no individual attribution and suppresses cells for
      groups too small to aggregate safely.
- [ ] A member sees the purpose statement before recording their first episode.
- [ ] DE and EN strings throughout.

## Dependencies

Blocked by #12. Ships before or with #13.

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

Task: implement visibility, retention and co-determination controls for duty activity data.
Treat this as a precondition for shipping the capture UI, not a follow-up.

1. Add `DutyActivityAccessPolicy` to organization settings: which roles may read individual
   episodes (default: none besides the recording member), retention in months, purpose statement.
2. Enforce it in `backend/app/services/authz.py` alongside the existing scope checks. The
   default path for a planner or admin requesting individual episodes is 403; aggregate
   endpoints are unaffected.
3. Write an `AuditLog` entry for every read of individual episode data and every policy change,
   following `services/audit.py` conventions.
4. Implement the retention purge as a service function plus a script in
   `backend/app/scripts/`, safe to re-run, logging one audit entry per run with the row count.
   Delete nothing outside the configured retention.
5. Add the works-council export to `backend/app/services/exports.py`: aggregate utilization per
   duty type per period, XLSX and PDF, no individual attribution, and suppress any cell where
   the group is small enough that a member could be re-identified.
6. Frontend: an admin configuration page under `/organization/team/` for policy, retention and
   purpose statement, plus a first-run acknowledgement shown to members before first capture.
7. Tests: default denial, granted access, audit entries, purge boundaries, export contains no
   individual data, small-group suppression.
8. Update `README.md`, `AGENTS.md`, `CHANGELOG.md`.
```
