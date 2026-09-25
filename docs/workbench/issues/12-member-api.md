---
title: "Member API: /api/v1/me endpoints shaped for one phone screen per request"
labels: backend, mcp, architecture, frontend
---

## Context

Part of ADR 0001 (`docs/decisions/0001-desktop-first-workbench.md`, decision 5). The member side
of the product will have two clients: the mobile-first web area from #114 and the Expo app from
#122. Both should read the same small, member-shaped endpoints instead of reusing planner
endpoints with flags.

What exists on `main`:

- Member views call planner endpoints with `team_member_portal=true`:
  `GET /api/v1/roster-matrix/{id}` and `GET|PUT /api/v1/matrix/{id}` (plus cell, note and intent
  routes). `AGENTS.md` (**Purpose**) documents the flag. Those payloads are whole-month matrices
  (`RosterMatrixRead`: `team_members`, `days`, `shift_templates`, `slots`, `assignments`,
  `planning_cells`, `day_status_definitions`, `shift_intents`), which is a lot for a phone and mixes
  two authorization paths in one route.
- `GET /api/v1/dashboard/team-member` (`TeamMemberDashboardRead`: `periods`, `shifts_by_month`,
  `current_period`, `wishes_day_statuses`, `my_validation_errors`, `my_validation_warnings`,
  `upcoming_slots`, `past_slots`) is the closest thing to a member endpoint. It takes `year` and
  `shift_group_id`.
- Swaps: `GET /api/v1/shift-swaps?planning_period_id=&shift_group_id=&status=&kind=` computes a
  `viewer_team_member_id` for linked members. Eligible claimants:
  `GET /api/v1/shift-swaps/eligible-members`.
- Duty activity: `GET|POST /api/v1/duty-activity`, `PATCH|DELETE /api/v1/duty-activity/{id}`,
  `GET /api/v1/duty-activity/slots/{id}/utilization`, purpose acknowledgement routes.
- Hours: `GET /api/v1/time-entries/ledger?team_member_id=&team_member_portal=true`.
- Calendar: `GET /api/v1/exports/roster-slots/{roster_slot_id}.ics` and the member shifts ICS in
  `backend/app/api/v1/roster_matrix.py` (`export_member_shifts_ics`).
- The linked member is found with `get_linked_team_member(db, user)`.

## Decision for this issue

A new router, `backend/app/api/v1/me.py`, mounted at `/api/v1/me`. Every route resolves the linked
`TeamMember` from the session (cookie or bearer) and returns **only that member's** data. No route
takes a `team_member_id`. Every route returns 403 `{ "code": "no_linked_team_member" }` when the
user has no linked member, the same message the web UI shows today.

Business logic lives in a new `backend/app/services/member_portal.py` that **composes existing
services**. It adds no new rule logic.

| Route | Returns | Built from |
|---|---|---|
| `GET /me/home` | next 5 duties, open swap actions needing me (claims to answer, targeted requests), the next period in `draft` with its wishes deadline if the org has one, and the unread notification count from #101's notification service (omit the field if #101 has not landed) | dashboard service, `shift_swaps` |
| `GET /me/duties?from=&to=` | my assigned slots in the window: slot facts (template, variant, times as instants with offset, `slot_date`, category), shift group, plan status of that group and period, open swap request on it, whether duty activity can be recorded and whether an episode is running | roster assignments, `shift_swaps`, `duty_activity` |
| `GET /me/wishes/{planning_period_id}?shift_group_id=` | my day cells, my intents, my month note, day status definitions, templates of the group, and `editable` with a reason | `matrix` services |
| `PUT /me/wishes/{planning_period_id}/cells` (bulk) and `PUT /me/wishes/{planning_period_id}/intents` (bulk) and `PUT /me/wishes/{planning_period_id}/note` | same writes as the planner matrix, restricted to me | `matrix` services |
| `GET /me/swaps?status=` | requests I offered, claimed, was targeted by, and open giveaways I am eligible for, across my groups | `shift_swaps` |
| `GET /me/hours?from=&to=` | my ledger totals and entries (my own duty activity is visible to me) | `hours_ledger` |
| `GET /me/calendar.ics?token=` | my duties as ICS for calendar subscription, authenticated by a per-member calendar token (see below) | `ics_export` |

**Calendar subscription token.** Calendar apps cannot send cookies or bearer tokens. Add
`team_members.calendar_token` (random, nullable, unique) with `POST /me/calendar-token` (create or
rotate) and `DELETE /me/calendar-token`. The ICS route accepts only this token and exposes only
duty times and template names, no colleagues and no duty activity.

**Times** are ISO 8601 with offset, computed as in #109. If #109 has not landed yet, return
what the slot stores and add a TODO referencing it; do not implement a local fix here.

**Existing `team_member_portal=true` routes stay** until the web member area has moved to `/me`.
This issue moves the web member area (`/my`, `/my-planning`, `/my-hours` after #114) onto the
new endpoints and then marks the flag deprecated in `AGENTS.md`. Removing the flag is a follow-up.

**MCP**: `/me` is per-person by definition and the MCP server has no person. Do not add MCP tools
for `/me`. The underlying data is already reachable for admins through the existing resources.
State this in the PR and in `AGENTS.md` as the explicit exception to the AI-first rule, with the
reason.

## Scope

1. `services/member_portal.py`, `api/v1/me.py`, response schemas in `app/schemas/domain.py`.
2. Calendar token column, migration and routes.
3. pytest for every route: happy path, no linked member, member cannot see another member's data
   (try every route with ids from another member where an id appears in a path), published and
   draft editability for wishes, swaps list completeness against the existing swaps service.
4. Regenerate the OpenAPI types from #111.
5. Move the web member area to the `/me` endpoints and the query hooks from #113.
6. Docs: `AGENTS.md` (new **Member API** section, the MCP exception, the flag deprecation),
   `README.md`.

## Out of scope

- Notifications (#101, #125). #101 (design in `docs/rollout/swap-notifications-design.md`,
  PR #127) owns the notification REST surface: list own notifications, unread count, mark read,
  dismiss, own preferences. Do not duplicate those routes under `/me`. If they live elsewhere,
  the app calls them directly; `/me/home` only reads the unread count through #101's service.
- Idempotent duty activity creation (#123).
- Removing `team_member_portal=true` from the planner routes.

## Acceptance criteria

- [ ] All routes in the table exist, take no member id, and return only the caller's data. pytest
      proves isolation for every route.
- [ ] Calendar token routes and the token-only ICS route work; the ICS contains no colleague data
      (test).
- [ ] `GET /me/home` and `GET /me/duties` each run a bounded number of queries independent of the
      number of duties (assert with a SQLAlchemy event counter, for 5 and for 50 duties).
- [ ] The web member area uses only `/api/v1/me/...` (grep in the PR shows no
      `team_member_portal=true` left in member pages).
- [ ] Generated API types updated.
- [ ] Migration verified against Postgres (paste the run).
- [ ] `ruff check app`, `pytest`, MCP tests, `npm run lint`, `npm run typecheck`, `npm run build`,
      `npm run test`, `npm run test:e2e` green.

## Dependencies

Needs #111. Moving the web member area needs #113 and #114; if those have not landed, ship
the backend and leave the frontend move as a checked follow-up in the PR. Blocks #122.

## Implementation prompt

```text
You are working in the `aegis301/shift-planner` repository.
Start from the latest `main`: `git fetch origin && git switch -c feat/member-api origin/main`.
Do not continue on a branch from another issue.

Read these before writing any code, and follow them strictly:
1. `AGENTS.md`, especially **Purpose**, **Duty activity log**, **Shift swaps**, **Working an issue** and **Testing Expectations**.
2. `docs/rollout/STATE.md`, especially **Decisions already made** and **Traps this project has already hit**.
3. `docs/decisions/0001-desktop-first-workbench.md`.
4. This issue's spec in full: `docs/workbench/issues/12-member-api.md`.

Standing rules that matter most here:
- Business logic lives in typed service functions under `backend/app/services/`, never in route
  handlers. `member_portal.py` composes existing services and adds no rules.
- Duty activity privacy: a member always sees their own episodes; nothing in `/me` may expose
  another member's episodes, even indirectly (for example through a swap counterparty's duty).
- Schema changes ship with a forward-only Alembic migration verified by hand against Postgres.
- Update `README.md`, `CHANGELOG.md`, `PLAN.md`, `AGENTS.md` and `docs/rollout/STATE.md` in the same change.
- Before you finish: `cd backend && ruff check app && pytest`, `cd mcp-server && pytest`,
  `cd frontend && npm run lint && npm run typecheck && npm run build && npm run test && npm run test:e2e`.

Task: add the member API under `/api/v1/me` and move the web member area onto it.

1. Read the services behind the existing member paths: `backend/app/services/dashboard.py`,
   `matrix.py`, `roster_matrix.py`, `shift_swaps.py`, `duty_activity.py`, `hours_ledger.py`,
   `ics_export.py`, and `get_linked_team_member`. Note which already filter to one member and which
   rely on the route to do it.
2. Write the isolation tests first (they fail until the routes exist).
3. Implement `member_portal.py` and `me.py` route by route with tests.
4. Add the calendar token.
5. Regenerate API types and move the web member area to the new endpoints.
6. Update the docs, including the explicit MCP exception.

Do not change: planner endpoints' behaviour, the `team_member_portal` flag's behaviour, rule
evaluation, the swap state machine.

Stop and report instead of guessing if: an existing service can only be called in a way that
loads other members' data and filters afterwards in a place where that data could leak into the
response. Name the service and propose the fix.

Prove it: walk the acceptance criteria one by one in the PR and name the test or pasted run that
proves each.
```
