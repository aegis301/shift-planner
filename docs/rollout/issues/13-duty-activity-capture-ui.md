---
title: "R1: One-tap duty activity capture on the team-member portal"
labels: rollout-r1, frontend, ux
---

## Context

Capture happens at 3 a.m., during work, on a phone. If it costs more than a tap it will not
happen — and an activity log with sparse data is worse than none, because it invites conclusions
from noise.

## Scope

- On `/my-planning` and the team-member dashboard: when a duty is running now, a prominent
  start/stop control. One tap starts an episode, one tap ends it. No typing required.
- Optional reason selection **after** stopping, never before.
- Retrospective entry from the "My shifts" tab, with a time picker.
- Per-duty summary: recorded minutes, utilization percentage, implied band.
- Offline tolerance: a failed start or stop is retried; a running episode is never lost to a
  dropped connection.
- Mobile-first, per the project's styling rules.

## Acceptance criteria

- [ ] Starting and stopping on a running duty takes two taps and no typing.
- [ ] A dropped connection during start or stop does not lose the episode.
- [ ] Retrospective entry validates against the slot span and surfaces the API's overlap error.
- [ ] Every string exists in DE and EN.
- [ ] Works at 360 px width.

## Dependencies

Blocked by #12. Must not ship before #14.

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

Task: build the duty activity capture UI on the team-member portal.

1. Read `frontend/app/my-planning/page.tsx`, `frontend/components/PlanningWorkspace.tsx`
   (team-member portal mode) and `frontend/components/DashboardUpcomingShiftsTable.tsx` to find
   where the member's current and past duties are already known.
2. Build a `DutyActivityControl` component: when a duty is running now, render a large
   start/stop control. Start posts an episode with `started_at = now`; stop patches
   `ended_at = now`. No modal, no required fields on either action.
3. Offer an optional reason only after stopping, as a dismissible follow-up.
4. Add retrospective entry from the "My shifts" tab: pick a past duty, enter start and end.
   Surface the API's overlap and span errors inline rather than as a generic failure.
5. Show a compact per-duty summary using the band the API returns. Do not compute thresholds in
   the frontend — they are org configuration.
6. Keep the running episode in component state and retry a failed start or stop. Do not use
   localStorage or sessionStorage.
7. Add every string to both dictionaries in `frontend/lib/i18n.ts`. Verify at 360 px.
   Run `npm run lint` and `npm run typecheck`.
8. Update `README.md` and `CHANGELOG.md`.
```
