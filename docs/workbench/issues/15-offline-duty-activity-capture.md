---
title: "Offline duty activity capture: idempotent API and a durable queue in the member app"
labels: backend, frontend, compliance, schema
---

## Context

Part of ADR 0001 (`docs/decisions/0001-desktop-first-workbench.md`, decisions 4 and 5).
`ROLLOUT.md` F1 says: "Capture must cost seconds at 3 a.m. or it will not happen." In a hospital
that also means: capture must work where there is no signal (basements, operating theatres,
shielded rooms). A tap that fails because the network is gone is a lost record, and lost records
make the statutory numbers systematically too low.

What exists on `main`:

- `POST /api/v1/duty-activity` creates a `TimeEntry` with `kind` `call_out` or
  `in_duty_activity`, `source = "duty_activity"`, `roster_slot_id`, `started_at` and optional
  `ended_at` (open means running). `PATCH /api/v1/duty-activity/{id}` stops or annotates,
  `DELETE` revokes (`backend/app/api/v1/duty_activity.py`, `backend/app/services/duty_activity.py`).
- Validation in the service: the slot must be assigned to the member, the purpose statement must be
  acknowledged (`POST /api/v1/duty-activity/purpose/acknowledge`), the episode must fit the slot
  span (`_assert_episode_fits_slot`), and episodes on the same slot must not overlap
  (`_assert_no_overlap`).
- **There is no idempotency.** Retrying a `POST` after a timeout whose request actually reached the
  server creates a second episode or fails with an overlap error, depending on timing.
- `TimeEntry` (`backend/app/models/entities.py`, around line 347) has no client-generated id and no
  record of when the device captured the tap.
- The web capture (`frontend/components/DutyActivityControl.tsx`) sends
  `new Date().toISOString()` and has no retry.
- Times: this issue depends on #109. Before #109 slot times are wall-clock values labelled as
  UTC and a correctly timestamped offline episode would be rejected as outside the slot.
- Privacy (`ROLLOUT.md` F1, § 87 Abs. 1 Nr. 6 BetrVG): individual episodes are visible to the
  member and to no other role without an explicit grant. Anything stored on the device is the
  member's own data, but it is still personal data on a device that can be lost.

## Decision for this issue

**Backend: idempotent creation and stop.**

- `TimeEntry.client_request_id` (UUID string, nullable) with a unique constraint on
  `(organization_id, client_request_id)`. Not per member: the key must be unique across the
  organization so that a second member reusing an id is caught by the database, not only by a
  racy read. On an insert conflict, load the existing row and decide by its owner (below).
- `TimeEntry.captured_at` (`DateTime(timezone=True)`, nullable): when the device recorded the
  action. `created_at` stays the server receipt time. Both are kept so late sync is visible, not
  hidden.
- `POST /api/v1/duty-activity` accepts `client_request_id`. If a row with that id already exists
  for the member, return it with `200` and do not validate again. If it exists for another member,
  `409` without revealing that row. Handle the concurrent case through the unique constraint
  (insert, catch the violation, re-read), not a check-then-insert.
- `PATCH /api/v1/duty-activity/{id}` setting `ended_at` to the value already stored returns the
  row with `200` (idempotent stop). A different `ended_at` on an already stopped episode keeps
  today's behaviour.
- Plausibility: refuse `started_at` more than 5 minutes in the future (clock skew) with a clear
  code. Accept late submissions for as long as the retention policy allows
  (`duty_activity_privacy.py`); older ones are refused with `retention_expired`.
- Refusal codes are stable and machine-readable (`slot_not_assigned`, `outside_slot_span`,
  `overlap`, `purpose_not_acknowledged`, `retention_expired`, `future_start`), so the app can show
  the right message and decide whether to retry.
- The web `DutyActivityControl` also sends `client_request_id` (one line, same benefit).

**App: durable queue.**

- `expo-sqlite` table `pending_actions` (`id`, `client_request_id`, `kind` `start` / `stop` /
  `create_complete`, `roster_slot_id`, `activity_kind`, `started_at`, `ended_at`, `server_id`,
  `state` `pending` / `sending` / `done` / `needs_attention`, `last_error_code`, `attempts`,
  `created_at`).
- A tap writes to the queue first and updates the UI immediately (optimistic). The queue flushes on
  app start, on foreground, on connectivity change (`@react-native-community/netinfo` or
  `expo-network`) and after each enqueue, in order, one at a time.
- A start and a stop for the same episode that are both still pending collapse into one
  `create_complete` request. A stop for an episode whose start has been sent uses the stored
  `server_id`.
- Retry with backoff on network errors and 5xx. Stop retrying on stable refusal codes and move the
  item to `needs_attention` with a message and the options "discard" or "edit times".
- The purpose acknowledgement must exist before the first offline capture. The app checks and
  caches it on sign-in and blocks capture with an explanation if it is missing.
- The duties the capture screen needs (today and tomorrow) are cached by TanStack Query persisted
  to storage (`@tanstack/query-async-storage-persister` or the SQLite store) so the capture screen
  works offline.
- **Sign-out wipes the queue and the cache.** If the queue has unsent items, sign-out warns first.
- The capture UI: one large start / stop button on the Duty detail and on Home when a duty is
  running, the running timer, and a small "saved on this phone, not yet sent" state.

## Scope

1. Backend columns, migration, service and route changes, refusal codes, pytest: duplicate POST
   returns the same row; duplicate from another member refused; idempotent stop; future start
   refused; late within retention accepted with `captured_at` preserved; beyond retention refused.
2. Regenerate API types (#111); update `DutyActivityControl` to send `client_request_id`.
3. App: queue module (`mobile/lib/offlineQueue/`) with unit tests for ordering, collapsing, retry
   classification and wipe on sign-out; capture UI; persisted duties cache.
4. Docs: `AGENTS.md` **Duty activity log** (idempotency, `captured_at`, refusal codes, the app's
   queue), `mobile/README.md` (how to test offline on a simulator).

## Out of scope

- Retrospective entry in the app (the web My shifts tab keeps it; the app can add it in #124).
- Background location or automatic detection of call-outs.
- Any change to who can read episodes.

## Acceptance criteria

- [ ] The backend scenarios in scope 1 have passing tests.
- [ ] Migration verified against Postgres with existing duty activity rows (paste the run).
- [ ] With the device in airplane mode: start and stop a duty activity, relaunch the app, go online,
      and see exactly one episode on the server with the device times and a later `created_at`
      (screen recording or step log in the PR).
- [ ] Killing the app between sending and receiving the response does not create a duplicate
      (simulate with a test that replays the same `client_request_id`).
- [ ] A refused item lands in `needs_attention` with the right message; discard and edit work.
- [ ] Sign-out with pending items warns, then wipes.
- [ ] `ruff check app`, `pytest`, MCP tests, web lint/typecheck/build, mobile typecheck/lint/test
      green.

## Dependencies

Needs #109 and #122.

## Implementation prompt

```text
You are working in the `aegis301/shift-planner` repository.
Start from the latest `main`: `git fetch origin && git switch -c feat/offline-duty-activity origin/main`.
Do not continue on a branch from another issue.

Read these before writing any code, and follow them strictly:
1. `AGENTS.md`, especially **Duty activity log**, **Working an issue** and **Testing Expectations**.
2. `docs/rollout/ROLLOUT.md` section F1 (co-determination and data quality).
3. `docs/rollout/STATE.md`, especially **Traps this project has already hit**.
4. `docs/decisions/0001-desktop-first-workbench.md`.
5. This issue's spec in full: `docs/workbench/issues/15-offline-duty-activity-capture.md`.

Standing rules that matter most here:
- Business logic lives in typed service functions under `backend/app/services/`.
- Duty activity privacy: individual episodes are visible to the member only unless a policy grants
  more. Nothing in this issue changes who can read episodes.
- Every capability is reachable from REST and MCP; the MCP `record_duty_activity_tool` accepts
  `client_request_id` too.
- Schema changes ship with a forward-only Alembic migration verified by hand against Postgres.
- Update `README.md`, `CHANGELOG.md`, `PLAN.md`, `AGENTS.md` and `docs/rollout/STATE.md` in the same change.
- Before you finish: backend ruff and pytest, MCP tests, web lint/typecheck/build, mobile
  typecheck/lint/test.

Task: make duty activity creation idempotent and add a durable offline queue to the member app.

1. Confirm #109 (slot times as instants) has landed: a slot generated in Europe/Berlin stores a
   real UTC instant. If it has not, stop and report; this issue cannot be correct without it.
2. Backend first: columns, migration, idempotent create and stop, refusal codes, plausibility
   checks, tests. Commit.
3. Web: send `client_request_id` from `DutyActivityControl`.
4. App: build the queue as a pure module with tests before any UI. Then the capture UI, the
   persisted cache and the sign-out wipe.
5. Test offline on a simulator and document the steps.

Do not change: who can read episodes, retention rules, the utilization bands, the web capture UI
beyond the one-line id.

Stop and report instead of guessing if: a refusal cannot be classified as retryable or permanent,
or the swap of a duty while the member is offline produces a case the refusal codes do not cover.

Prove it: walk the acceptance criteria one by one in the PR and name the test, recording or
pasted run that proves each.
```
