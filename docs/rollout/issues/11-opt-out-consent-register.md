---
title: "R1: Add the working-time consent register with revocation handling"
labels: rollout-r1, backend, frontend, compliance
---

## Context

The extended weekly cap is available only with individual written consent, revocable on six
months' notice, with no detriment for refusing. That is a dated record with a workflow, not a
boolean on the member.

A revocation can make an already published future roster non-compliant. The system must surface
that rather than silently re-evaluating.

## Scope

`WorkTimeConsent`: `team_member_id`, `consent_type` (`opt_out`), `tier` (matching
`opt_out_weekly_cap.hours_by_tier`), `valid_from`, `signed_document_reference`,
`recorded_by_user_id`, `revoked_at`, `notice_period_months`, derived `effective_until`.

`applicable_weekly_cap(member_id, on_date, rule_set)` resolves **per date**. A revocation
triggers a scan of future published plan versions and produces findings where they no longer
comply — surfaced, never auto-corrected.

REST under `/api/v1/team-members/{id}/work-time-consents` (admin write, self read), MCP
resource plus guarded tools, admin UI in the staff directory row detail, read-only card on
`/profile`.

## Acceptance criteria

- [ ] A member without effective consent is evaluated against the base weekly cap.
- [ ] A revocation dated today applies the opt-out cap up to `today + notice_period_months` and
      the base cap after, within one evaluation run.
- [ ] Revoking lists the affected future published plans.
- [ ] Consent records are immutable; corrections create a new record.
- [ ] DE and EN strings for every new label.

## Dependencies

Blocked by #08. Consumed by #09.

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

Task: implement the working-time consent register and per-date cap resolution.

1. Model `WorkTimeConsent` as described. Make records immutable in the service layer:
   corrections create a new record rather than editing one, so the history stays auditable.
2. `effective_until` is derived, not user input: `revoked_at + notice_period_months` when
   revoked, otherwise null.
3. Implement `applicable_weekly_cap(member_id, on_date, rule_set)` in
   `backend/app/services/work_time_consents.py`. The averaging rule from #09 calls this **per
   date**, not once per member — a reference period can span a revocation, and resolving once
   would silently apply the wrong cap to half the window.
4. On revocation, scan `PlanningPlanVersion` rows for future months in the member's shift groups,
   re-evaluate against the rules and return findings. Surface them; modify no published plan.
5. REST with admin-only writes and self-read for the linked team member. MCP: read resource plus
   `record_work_time_consent_tool` and `revoke_work_time_consent_tool`, admin-token guarded.
6. Frontend: admin panel in `frontend/components/StaffDirectoryPanel.tsx` row detail, read-only
   card on `/profile`. DE and EN strings.
7. Tests: per-date resolution across a revocation boundary, immutability, affected-plan scan,
   authorization (a member cannot record their own consent).
8. Update `README.md`, `AGENTS.md`, `CHANGELOG.md`.
```
