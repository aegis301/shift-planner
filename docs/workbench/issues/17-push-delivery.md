---
title: "Push delivery for notifications: device push tokens, delivery worker and deep links"
labels: backend, frontend, schema, compliance
---

## Context

Part of ADR 0001 (`docs/decisions/0001-desktop-first-workbench.md`, decision 5). Push is the main
reason the member companion is a native app.

This issue is the **delivery channel only**. What gets notified, to whom, with which preferences,
and the works-council position are decided in #101 ("Nobody is told anything about a swap"). #101
is explicitly design-first: its first session writes `docs/rollout/swap-notifications-design.md`
and settles four open questions (channel, per-user preferences, works council, digest or
immediate). **Do not start this issue before #101's notification record and emission points
exist on `main`.** If #101's design does not list push as a channel, reopen that decision with the
owner first.

What exists or will exist when this starts:

- From #101: a notification record (recipient, event type, subject reference, created, read,
  delivered), emission from the swap service transitions, per-user preferences, an in-app list.
- From #119: `auth_device_sessions`, one row per signed-in device, revocable.
- From #122: the Expo app with Expo Router, TanStack Query and secure storage.
- Background execution pattern: the Compose `solver-worker` service runs
  `python -m app.scripts.solver_worker`, which polls `solver_runs` and claims work with
  `SELECT ... FOR UPDATE SKIP LOCKED` (`backend/app/services/solver_runs.py`,
  `claim_next_queued_run`). Reuse the pattern, not the table.

## Decision for this issue

- **Channel**: Expo Push Service (`https://exp.host/--/api/v2/push/send`), which fronts APNs and
  FCM. One integration for both platforms. Authenticated with an `EXPO_ACCESS_TOKEN` (enable
  "enhanced push security" in the Expo project) from settings, never committed.
- **Tokens**: table `push_tokens` with `id`, `device_session_id` (FK to `auth_device_sessions`,
  cascade), `expo_push_token` (unique), `platform`, `created_at`, `last_seen_at`, `disabled_at`,
  `disabled_reason`. A token belongs to a device session, so revoking a device (or sign-out)
  stops its pushes immediately.
  Endpoints: `PUT /api/v1/me/push-token` (register or refresh, idempotent) and
  `DELETE /api/v1/me/push-token`.
- **Delivery table**: `notification_deliveries` with `notification_id`, `push_token_id`, `state`
  (`queued`, `sent`, `failed`, `skipped`), `ticket_id`, `receipt_status`, `error`, timestamps.
  One notification can fan out to several devices.
- **Worker**: a new Compose service `notification-worker` (`python -m app.scripts.notification_worker`)
  that claims undelivered notifications with `FOR UPDATE SKIP LOCKED`, applies the recipient's
  preferences (from #101), sends in batches of up to 100, stores tickets, and polls receipts
  after 15 minutes. `DeviceNotRegistered` disables the token. Transient errors retry with backoff;
  after 5 attempts the delivery is `failed`.
- **Content minimisation**: push payloads travel through Apple and Google. The visible text is
  generic by default ("A duty swap needs your answer", "Your swap was approved"). No colleague
  names, no duty times, no duty activity in the visible text or in `data`. `data` carries only
  `{ type, notification_id, subject_type, subject_id }`. Whether a member may opt into detailed
  text is a #101 preference question; default is generic. This is part of the works-council
  documentation #101 requires.
- **Deep links**: the app maps `data.type` / `subject_type` to routes (for example a swap request
  opens Swaps → request detail) and marks the notification read through the #101 API.
- **Web**: no web push in this issue. The web keeps the in-app list from #101.
- **MCP**: read-only resource of delivery state per notification for admins, no token-level data.

## Scope

1. Tables, migration, `services/push_delivery.py`, worker script, Compose services in
   `docker-compose.yml` and `docker-compose.prod.yml`, settings in `config.py` and `.env.example`.
2. Token endpoints under `/api/v1/me`.
3. App: permission prompt at a moment that makes sense (after the first swap interaction, not on
   first launch), token registration with `expo-notifications`, re-registration on token change,
   removal on sign-out, deep-link routing, a settings row showing whether push is on.
4. pytest with the Expo API mocked: fan-out to two devices, revoked device receives nothing,
   preference off produces `skipped`, `DeviceNotRegistered` disables the token, retry then fail,
   payload contains no names or times (assert on the exact JSON sent).
5. Docs: `AGENTS.md` (push delivery, content rule), `deploy/README.md` (worker, egress to
   `exp.host`, token), `mobile/README.md` (testing push on a device).

## Out of scope

- Deciding which events notify or the preference model (#101).
- Email delivery.
- Web push.

## Acceptance criteria

- [ ] #101's notification record exists on `main` (link the PR) before this work starts.
- [ ] Every scenario in scope 4 has a passing test.
- [ ] A real device receives a push for a swap event and opens the right screen (recording).
- [ ] Revoking the device from the web settings stops pushes to it (test and manual check).
- [ ] Migration verified against Postgres (paste the run).
- [ ] Worker runs in Compose and in the production stack; `container-smoke` still passes.
- [ ] Backend ruff and pytest, MCP tests, mobile typecheck/lint/test green.

## Dependencies

Needs #101 (implemented, not only designed), #119 and #122.

## Implementation prompt

```text
You are working in the `aegis301/shift-planner` repository.
Start from the latest `main`: `git fetch origin && git switch -c feat/push-delivery origin/main`.
Do not continue on a branch from another issue.

Read these before writing any code, and follow them strictly:
1. `AGENTS.md`, especially **Solver runs** (worker pattern), **Shift swaps**, **Working an issue** and **Testing Expectations**.
2. `docs/rollout/STATE.md`, especially **Traps this project has already hit**.
3. `docs/decisions/0001-desktop-first-workbench.md`.
4. `docs/rollout/swap-notifications-design.md` and GitHub issue #101 with its linked PRs.
5. This issue's spec in full: `docs/workbench/issues/17-push-delivery.md`.

Standing rules that matter most here:
- Business logic lives in typed service functions under `backend/app/services/`.
- Push payloads contain no colleague names, duty times or duty activity.
- Schema changes ship with a forward-only Alembic migration verified by hand against Postgres.
- Update `README.md`, `deploy/README.md`, `CHANGELOG.md`, `PLAN.md`, `AGENTS.md`, `.env.example`
  and `docs/rollout/STATE.md` in the same change.
- Before you finish: backend ruff and pytest, MCP tests, mobile typecheck/lint/test, and a local
  `docker compose up` showing the worker start.

Task: deliver #101's notifications to the member app by push.

1. Check that #101's notification record, emission points and preferences are on `main`. If they
   are not, stop and report; do not build a notification model here.
2. Backend: tables, service, worker, endpoints, tests with the Expo API mocked. Commit.
3. Compose and deploy changes. Commit.
4. App: permission timing, registration, deep links, sign-out removal.
5. Test on a real device and record it.

Do not change: which events notify, the preference model, swap state transitions, email.

Stop and report instead of guessing if: #101's design sends content that would put names or duty
times into the push payload, or its preferences cannot express "push off" per event type.

Prove it: walk the acceptance criteria one by one in the PR and name the test, recording or
pasted run that proves each.
```
