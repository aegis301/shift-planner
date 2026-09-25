---
title: "Push delivery for notifications: device push tokens, delivery worker and deep links"
labels: backend, frontend, schema, compliance
---

## Context

Part of ADR 0001 (`docs/decisions/0001-desktop-first-workbench.md`, decision 5). Push is the main
reason the member companion is a native app.

This issue adds **push as one more delivery channel** to the notification system that #101
builds. It does not design notifications. #101's design is in
`docs/rollout/swap-notifications-design.md` (PR #127). Read it in full; this spec follows its
shape. The parts this issue builds on:

- **`Notification`**: one durable, recipient-private row per recipient and event, created inside the
  same transaction as the swap transition. Fields include `organization_id`, `recipient_user_id`,
  `event_type` (for example `swap.targeted`, `swap.claimed`, `swap.expiry_warning`), `category`,
  `subject_type` (`shift_swap_request`), `subject_id`, a versioned `payload` snapshot (which
  **does** contain display names and the duty date), `read_at`, `dismissed_at`, `expires_at`
  (90 days by default) and a `dedupe_key`.
- **`NotificationDelivery`**: one row per channel attempt, with `channel` (initially only `email`),
  `mode` (`immediate` / `digest`), `status` (`pending`, `sending`, `delivered`, `failed`,
  `suppressed`, `not_configured`), `deliver_after`, claim fields, `attempt_count`,
  `last_error_code`, `delivered_at`, `provider_message_id`, `digest_key`.
- **`UserNotificationPreference`**: per membership and category, with `in_app_enabled`,
  `email_enabled` and `delivery_mode`, plus documented code defaults for missing rows.
  Categories: `marketplace`, `direct_proposal`, `participant_update`, `approval_request`,
  `expiry_warning`.
- **`notification-worker`**: a dedicated Compose service that claims due delivery rows with
  `FOR UPDATE SKIP LOCKED` (the solver-worker pattern), runs the warning and expiry sweeps, and
  purges expired rows.
- **Delivery never rolls back a transition** and never removes the in-app record.
- **Works council**: notifications are recipient-private; admins and planners get only aggregate,
  non-identifying delivery health; no per-member counters. The brief explicitly recommends **no web
  push** in #101.

**Gate.** #101's design is a recommendation until the owner approves it, and this issue needs the
implemented tables and worker on `main`, not the brief. If the approved design differs from the
summary above (different table names, a different preference model, push rejected as a channel),
follow the approved design and adjust this spec in the same PR, or stop and ask when the difference
changes what this issue can do.

Other prerequisites:

- #119: `auth_device_sessions`, one row per signed-in device, revocable.
- #122: the Expo app with Expo Router, TanStack Query and secure storage.
- #109: `Organization.timezone`, which #101's warning window and digest also use.

## Decision for this issue

- **Channel**: Expo Push Service (`https://exp.host/--/api/v2/push/send`), which fronts APNs and
  FCM. One integration for both platforms. Authenticated with an `EXPO_ACCESS_TOKEN` (enable
  "enhanced push security" in the Expo project) from settings, never committed. Unconfigured push
  behaves like unconfigured email in #101: delivery rows get `not_configured`, nothing else breaks.
- **Reuse `NotificationDelivery` with `channel = "push"`.** Do not add a separate delivery table.
  Because one notification can fan out to several devices, add a nullable `push_token_id` column to
  `notification_deliveries` (one push delivery row per active token) plus `ticket_id` and
  `receipt_status` for Expo's two-step ticket and receipt protocol. The unique delivery key becomes
  `(notification_id, channel, push_token_id)`.
- **Tokens**: table `push_tokens` with `id`, `device_session_id` (FK to `auth_device_sessions`,
  cascade), `expo_push_token` (unique), `platform`, `created_at`, `last_seen_at`, `disabled_at`,
  `disabled_reason`. A token belongs to a device session, so revoking a device (or sign-out)
  stops its pushes immediately. Endpoints: `PUT /api/v1/me/push-token` (register or refresh,
  idempotent) and `DELETE /api/v1/me/push-token`.
- **Preferences**: add `push_enabled` to `UserNotificationPreference`, with code defaults that
  mirror #101's email defaults (on for `direct_proposal`, `participant_update`,
  `approval_request`, `expiry_warning`; off for `marketplace`, which follows the digest rule and
  the seven-day urgency bypass if #101 adopted it). Push never goes out for a category whose
  in-app record is disabled.
- **Creation of push delivery rows** happens where #101 creates its email delivery rows (the
  typed helper in the notification service, inside the transition transaction), one row per active
  push token of the recipient's account at that moment.
- **Worker**: extend #101's `notification-worker`, do not add a second worker. It sends push rows
  in batches of up to 100, stores tickets, and polls receipts after 15 minutes.
  `DeviceNotRegistered` disables the token. Transient errors retry with #101's backoff; after 5
  attempts the row is `failed`.
- **Content minimisation**: push payloads travel through Apple and Google, unlike the in-app
  record. The **visible text is generic** and rendered from `event_type` and the recipient
  locale ("A duty swap needs your answer", "Your swap was approved"). No colleague names, no duty
  date or time, no duty activity in the visible text or in `data`, even though #101's `payload`
  snapshot contains names. `data` carries only `{ event_type, notification_id, subject_type,
  subject_id }`; the app fetches details from the API after opening. Whether a member may opt into
  detailed push text is a follow-up preference, off by default. Add this rule to the works-council
  documentation #101 introduced.
- **Deep links**: the app maps `event_type` / `subject_type` to routes (a swap request opens
  Swaps → request detail) and marks the notification read through #101's REST API.
- **In-app inbox in the app**: the Expo app gets the inbox that #101 builds for the web, using
  #101's REST endpoints (list, unread count, mark read, dismiss, preferences). This is where the
  push toggle per category lives.
- **Web**: no web push, per #101's brief.
- **MCP**: only the aggregate delivery health #101 exposes, extended with the push channel. No
  token-level or per-member data.

## Scope

1. Migration: `push_tokens`; `push_token_id`, `ticket_id`, `receipt_status` on
   `notification_deliveries`; `push_enabled` on `user_notification_preferences`.
2. `services/push_delivery.py` (token registration, fan-out rows, Expo client, receipt handling),
   wired into #101's notification helper and worker.
3. Token endpoints under `/api/v1/me`. Settings in `config.py` and `.env.example`.
4. App: permission prompt at a moment that makes sense (after the first swap interaction, not on
   first launch), token registration with `expo-notifications`, re-registration on token change,
   removal on sign-out, deep-link routing, inbox screen, per-category push toggles.
5. pytest with the Expo API mocked: fan-out to two devices; revoked device receives nothing;
   `push_enabled = false` produces `suppressed`; unconfigured push produces `not_configured`;
   `DeviceNotRegistered` disables the token; retry then fail; a rejected swap transition creates
   no push row; the exact JSON sent contains no names, dates or times.
6. Docs: `AGENTS.md` (push channel, content rule), `deploy/README.md` (egress to `exp.host`,
   `EXPO_ACCESS_TOKEN`), `mobile/README.md` (testing push on a device), and the works-council
   section #101 added.

## Out of scope

- Deciding which events notify, categories, defaults for in-app and email, digest rules (#101).
- Email delivery (#101).
- Web push.

## Acceptance criteria

- [ ] #101's notification record, delivery table, preferences and worker exist on `main` (link the
      PR) before this work starts.
- [ ] Push uses `notification_deliveries` with `channel = "push"`; no second delivery table and no
      second worker exist.
- [ ] Every scenario in scope 5 has a passing test.
- [ ] A real device receives a push for a swap event and opens the right screen (recording).
- [ ] Revoking the device from the web settings stops pushes to it (test and manual check).
- [ ] The app shows #101's inbox and per-category push toggles.
- [ ] Migration verified against Postgres (paste the run).
- [ ] `container-smoke` still passes.
- [ ] Backend ruff and pytest, MCP tests, mobile typecheck/lint/test green.

## Dependencies

Needs #101 implemented (design: PR #127), #109, #119 and #122.

## Implementation prompt

```text
You are working in the `aegis301/shift-planner` repository.
Start from the latest `main`: `git fetch origin && git switch -c feat/push-delivery origin/main`.
Do not continue on a branch from another issue.

Read these before writing any code, and follow them strictly:
1. `AGENTS.md`, especially **Shift swaps**, the notifications section added by #101, **Working an issue** and **Testing Expectations**.
2. `docs/rollout/STATE.md`, especially **Traps this project has already hit**.
3. `docs/decisions/0001-desktop-first-workbench.md`.
4. `docs/rollout/swap-notifications-design.md` in full, GitHub issue #101 and the PRs that
   implemented it.
5. This issue's spec in full: `docs/workbench/issues/17-push-delivery.md`.

Standing rules that matter most here:
- Business logic lives in typed service functions under `backend/app/services/`.
- Notifications are recipient-private. Push payloads contain no colleague names, duty dates, duty
  times or duty activity, even though the in-app payload does.
- Delivery never rolls back a swap transition and never removes the in-app record.
- Schema changes ship with a forward-only Alembic migration verified by hand against Postgres.
- Update `README.md`, `deploy/README.md`, `CHANGELOG.md`, `PLAN.md`, `AGENTS.md`, `.env.example`
  and `docs/rollout/STATE.md` in the same change.
- Before you finish: backend ruff and pytest, MCP tests, mobile typecheck/lint/test, and a local
  `docker compose up` showing the notification worker sending a push row.

Task: add push as a delivery channel to #101's notification system and give the member app the
inbox.

1. Check that #101's `Notification`, `NotificationDelivery`, `UserNotificationPreference` (or
   whatever the approved design named them) and the notification worker are on `main`. If they
   are not, stop and report; do not build a notification model here. If the implemented design
   differs from this spec's summary, list the differences in the PR and adapt.
2. Backend: migration, `services/push_delivery.py`, hook into #101's helper and worker, token
   endpoints, tests with the Expo API mocked. Commit.
3. Config and deploy docs. Commit.
4. App: permission timing, registration, deep links, inbox, push toggles, sign-out removal.
5. Test on a real device and record it.

Do not change: which events notify, categories, in-app or email defaults, digest rules, swap
state transitions, email delivery.

Stop and report instead of guessing if: #101's implementation cannot fan one notification out to
several devices without changing its delivery key in a way its own tests forbid, or its
preferences cannot express push per category.

Prove it: walk the acceptance criteria one by one in the PR and name the test, recording or
pasted run that proves each.
```
