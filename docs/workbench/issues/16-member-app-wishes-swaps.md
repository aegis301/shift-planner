---
title: "Member app: wishes, swaps, hours and calendar subscription"
labels: frontend, ux
---

## Context

Part of ADR 0001 (`docs/decisions/0001-desktop-first-workbench.md`, decision 4). After #122 the
app can sign in and show duties. This issue adds the other member jobs, so a member never needs the
web for day-to-day use.

The app relies on the member API from #120:

- `GET /api/v1/me/wishes/{planning_period_id}?shift_group_id=` with `editable` and a reason, and
  `PUT /api/v1/me/wishes/{id}/cells`, `PUT .../intents`, `PUT .../note`.
- `GET /api/v1/me/swaps?status=` (offered, claimed, targeted, eligible open giveaways).
- `GET /api/v1/me/hours?from=&to=`.
- `POST|DELETE /api/v1/me/calendar-token` and `GET /api/v1/me/calendar.ics?token=`.

Swap transitions use the existing endpoints under `/api/v1/shift-swaps` (`POST ""` create,
`/{id}/open`, `/{id}/claim`, `/{id}/accept`, `/{id}/decline`, `/{id}/withdraw`), which already
check that the caller is the right member and run legality through `evaluate_plan_state`. Refusals
come back as `SHIFT_SWAP_ILLEGAL` with the violated rule's findings. `AGENTS.md` **Shift swaps**
describes the state machine and the UI states from #99 (missing shift group, unlinked account,
draft plan, past slot).

Open concept issue #103 (wishes rework: priorities, finer wishes) may change the wishes payload.
Build the wishes screen so the day editor is one component that can grow.

## Decision for this issue

- **Tabs** become: Home, Duties, Wishes, Swaps, More (Hours, Calendar, Settings).
- **Wishes**: a month calendar for the next editable period (period and shift group pickers if the
  member has several groups). Each day shows its status color. Tapping a day opens a bottom sheet:
  status picker (org-defined statuses from the payload), comment, and per-template wish / no-go
  toggles. A multi-select mode selects a range of days and applies one status in one bulk request.
  The month note is its own screen. When `editable` is false, everything is read-only and the
  reason is shown (draft vs preliminary vs published, per `AGENTS.md`).
- **Swaps**:
  - "Needs you" list: targeted proposals to accept or decline, claims waiting.
  - "My requests": status timeline per request, withdraw where allowed.
  - "Open giveaways": duties I am eligible for, ranked as the API returns them; claim with a
    confirmation that shows the duty.
  - Offer from Duty detail: giveaway or direct swap (pick a colleague and their duty from the
    eligible list the API returns).
  - Which actions a request offers comes from `allowed_actions` in `/me/swaps` (#120); the offer
    button on Duty detail follows `can_offer` from `/me/duties`. The app holds no transition table.
  - Illegal actions show the finding messages from the API. The app never predicts legality.
  - The disabled-state reasons come from `disabled_reasons` and use the same dictionary keys as the
    web (#99).
- **Hours**: period totals and entries from `/me/hours`, statutory minutes and credited minutes
  **shown as two separate numbers** (the dual valuation invariant in `AGENTS.md`), never summed.
- **Calendar**: create or rotate the calendar token, show the subscription URL, "Add to calendar"
  opens the `webcal://` URL, and "Revoke" deletes the token.
- **Retrospective duty activity entry** on Duty detail for past duties (start and end pickers),
  through the same queue as #123 if it has landed, otherwise online only.

## Scope

1. The screens above with TanStack Query hooks and invalidation (a swap transition invalidates
   `me/swaps`, `me/home`, `me/duties`).
2. Strings in `@shift-planner/i18n`, both languages, reusing existing swap and wishes keys where
   the meaning is identical.
3. Tests: wishes editability states, bulk range apply sends one request, swap action availability
   per status, illegal claim shows findings, hours never shows a summed figure, calendar token
   rotate and revoke.

## Out of scope

- Push notifications (#125).
- #103 changes.
- Any planner capability.

## Acceptance criteria

- [ ] A member can do every wishes, swap, hours and calendar task from the app that they can do on
      the web member area (checklist in the PR, one line per web capability).
- [ ] Wishes: range apply is one request; read-only states show the correct reason (tests).
- [ ] Swaps: each item shows exactly the actions in its `allowed_actions` from `/me/swaps`, and
      disabled ones show their `disabled_reasons` (table-driven test over all statuses with mocked
      payloads); the app contains no transition table of its own; an illegal claim shows the API's
      findings.
- [ ] Hours shows statutory and credited minutes separately (test).
- [ ] Calendar subscription URL works in the iOS or Android calendar app (screenshot).
- [ ] Mobile typecheck, lint, test green; i18n parity green.

## Dependencies

Needs #122 and, through it, #120, whose `/me/swaps` returns `allowed_actions` and `disabled_reasons` and whose `/me/duties` returns `can_offer`. If those fields are missing, stop and add them to the backend first (a #120 follow-up), never derive them on the device. Uses #123 for retrospective entry if available. Related to #103 and #99.

## Implementation prompt

```text
You are working in the `aegis301/shift-planner` repository.
Start from the latest `main`: `git fetch origin && git switch -c feat/mobile-wishes-swaps origin/main`.
Do not continue on a branch from another issue.

Read these before writing any code, and follow them strictly:
1. `AGENTS.md`, especially **Matrix Planning Rule** (wishes editability), **Shift swaps**, **Time entry ledger**, **Style → Frontend surfaces** and **Testing Expectations**.
2. `docs/rollout/STATE.md`, especially **Decisions already made**.
3. `docs/decisions/0001-desktop-first-workbench.md`.
4. This issue's spec in full: `docs/workbench/issues/16-member-app-wishes-swaps.md`.
5. GitHub issues #99 and #103.

Standing rules that matter most here:
- The app contains no business logic. Legality, editability and eligibility come from the API.
- Statutory working time and tariff credit are never summed or shown as one figure.
- Every user-visible string lives in `@shift-planner/i18n` in both languages.
- Update `CHANGELOG.md`, `PLAN.md`, `AGENTS.md`, `mobile/README.md` and `docs/rollout/STATE.md` in the same change.
- Before you finish: mobile typecheck, lint and test, package tests, and the web build.

Task: add wishes, swaps, hours and calendar subscription to the member app.

1. List every member capability of the web member area (`/my`, `/my-planning`, `/my-hours`,
   `/profile`) and map each to an app screen or to "out of scope" with a reason. That list is the
   checklist.
2. Build Wishes, then Swaps, then Hours, then Calendar, each with tests, one commit each.
3. Reuse dictionary keys from the web where the meaning is identical; add new keys otherwise.

Do not change: backend code, web code, shared package APIs beyond backwards-compatible additions.

Stop and report instead of guessing if: a web capability has no `/api/v1/me` endpoint to back it,
or a swap action's availability cannot be derived from the API response without re-implementing
the state machine on the device.

Prove it: walk the acceptance criteria one by one in the PR and name the test or screenshot that
proves each.
```
