# Swap notifications: decision brief

Status: proposed; product and works-council decisions required before implementation
Issue: #101
Date: 2026-09-25

## Purpose

This document makes the four open product decisions in issue #101 cheap to resolve. It maps
the current swap state machine to recipients, inventories reusable infrastructure, compares the
available choices, and proposes a schema and service boundaries. It does not approve those
choices and does not authorize implementation.

The implementation should preserve one distinction throughout:

- creating a durable in-app notification is part of the swap transition transaction;
- delivering email is an asynchronous effect of that committed notification.

That distinction makes it impossible to commit a successful transition without its notification
while keeping SMTP latency and failures out of the request path.

## Current state machine and recipients

The state machine is centralized in `backend/app/services/shift_swaps.py`. Giveaway requests
normally follow `draft -> open -> claimed -> approved -> applied`; direct requests follow
`draft -> targeted -> accepted -> approved -> applied`. `withdrawn`, `rejected`, and `expired`
are terminal states.

Recipients below are organization memberships (`User` rows), not bare email addresses.
Team-member recipients are resolved through `TeamMember.user_id`; a team member without a
linked login cannot receive an in-app notification or account email. “Scoped planners” means
all admins in the organization plus planners assigned to the request's shift group. The actor is
excluded unless the row explicitly says otherwise.

| Transition or event | Service entry point | Actor | Durable notification recipients | Why |
|---|---|---|---|---|
| create `draft` | `create_shift_swap` | offering member | none | A private draft has no other participant and the creator already sees the result. |
| `draft -> open` giveaway | `open_shift_swap` | offering member | linked eligible claimants | Makes the pool discoverable without notifying members who cannot legally claim it. |
| `draft -> targeted` direct proposal | `open_shift_swap` | offering member | named target | Closes the undelivered-direct-proposal blind spot. |
| `open -> claimed` | `claim_shift_swap` | claimant | offeror and scoped planners | The offeror learns that the duty was taken; planners learn that approval is waiting. |
| `targeted -> accepted` | `accept_shift_swap` | named target | offeror and scoped planners | The offeror learns that the proposal was accepted; planners learn that approval is waiting. |
| active `-> withdrawn` | `withdraw_shift_swap` | offeror or planner | non-actor offeror/target/claimant; scoped planners when an approval item is removed | Prevents a participant or planner from waiting on a request that disappeared. An open-pool withdrawal is not broadcast again. |
| `targeted -> rejected` by target | `reject_shift_swap` | named target | offeror | Tells the proposer that the direct proposal was declined. |
| `open`, `claimed`, `targeted`, `accepted`, or `approved -> rejected` by planner | `reject_shift_swap` | planner | offeror and target/claimant | Tells both participants the planner's decision. |
| `claimed` or `accepted -> approved` | `approve_shift_swap` | planner | offeror and target/claimant | Closes the “did the planner agree?” blind spot. |
| `approved -> applied` | `apply_shift_swap` | planner | offeror and target/claimant | Confirms that the roster, not only the request state, changed. |
| active `-> expired` | proposed `expire_due_shift_swaps` service; replace the side effect in `_expire_if_past` | system | offeror and target/claimant; scoped planners if the request was awaiting approval | Makes expiry explicit and removes stale approval work. |
| duty enters warning window | proposed `warn_due_shift_swaps` service | system | offeror; target/claimant when present; scoped planners when awaiting approval | Warns the people who can still act before expiry. |

`ALLOWED_TRANSITIONS` also contains `open -> targeted`, but no service entry point performs it.
It should not receive a notification design until the product exposes that transition. Rejected
validation, authorization, legality, and concurrent-claim attempts do not change state and must
emit no notification.

The current `_expire_if_past` behavior is incomplete for scheduled expiry: it is called only by
open, claim, accept, and approve; it excludes `approved`; and it commits before raising without
an audit record. The scheduled service should process every status from which
`ALLOWED_TRANSITIONS` permits `expired`, including `approved`, and the lazy guard should call
the same service function rather than maintaining a second expiry path.

## Existing infrastructure

### Reusable

- `backend/app/scripts/solver_worker.py` and the `solver-worker` Compose service provide the
  established no-broker polling-worker pattern.
- `claim_next_queued_run` in `backend/app/services/solver_runs.py` demonstrates PostgreSQL
  `FOR UPDATE SKIP LOCKED` and conditional updates for safe concurrent workers.
- `backend/app/scripts/purge_duty_activity.py` demonstrates a callable batch job, although it is
  not scheduled by Compose.
- Swap mutations are already centralized in `backend/app/services/shift_swaps.py` and write an
  audit record in the same unit of work.
- Organization JSON policies and typed read/update services provide a pattern for configurable
  defaults.
- REST swap handlers already delegate to services and translate stable conflict codes.
- MCP already exposes swap resources and token-gated mutation tools.
- `frontend/components/AppShell.tsx` is the natural location for an unread marker, and Settings
  is the natural preference surface.

### Missing

- No notification, inbox, delivery, or preference model exists.
- No outbound email library, provider, SMTP settings, templates, bounce handling, or delivery
  status exists.
- No generic scheduler, notification worker, Redis, Celery, or durable background-job table
  exists.
- No eager swap-expiry sweep exists; expiry is lazy.
- No shell badge, notification list, read/dismiss API, or notification MCP resource exists.
- The PWA manifest does not provide web push.
- `Account.locale` and `User.locale` exist, but no notification-specific preference storage
  exists.

## Decision 1: delivery channel

### Options

| Option | Benefits | Cost and risk |
|---|---|---|
| In-app only | Smallest backend and operational scope; no external processor; no deliverability work. | Does not solve the core deadline problem when the recipient is not already opening the app. A shell badge is still pull-based. |
| In-app plus email from day one | Reaches direct targets, participants, and planners outside the app; email works without installing a PWA. | Requires a provider or SMTP relay, secrets, localized templates, retries, idempotency, delivery observability, and a preference/unsubscribe path. |
| In-app first, email in a later issue | Allows the record, inbox, and preferences to settle before operating email. | Ships an explicitly incomplete answer to the largest adoption risk and requires a second rollout and migration review. |
| In-app plus web push | Timely and app-like. | Requires service-worker, browser permission, subscription lifecycle, VAPID keys, and device-level revocation; it is more new machinery than email and is not a reliable sole channel. |

### Recommendation

Ship in-app and email together. Treat in-app as the durable source of truth and email as a
delivery channel derived from it. Do not add web push in this issue.

Email should be sent through a provider-neutral adapter with one configured production
provider, not directly from transition functions. The application must remain usable when email
is unconfigured: notifications still enter the inbox, while delivery rows record
`not_configured`. This avoids making local Docker setup depend on external credentials.

This recommendation cannot be approved from the codebase. It needs an operational owner to
choose and fund the mail provider, sender domain, bounce handling, and production support.

## Decision 2: per-user preferences

### Options

| Option | Benefits | Cost and risk |
|---|---|---|
| No preferences | Simplest schema and UI. | Creates alert fatigue and ignores the issue's explicit product concern. |
| One global email switch | Cheap and understandable. | Too coarse: marketplace announcements and direct duty changes have very different urgency. |
| Per-event switches | Maximum control. | A long, unstable settings form; new event types require preference migration and explanation. |
| Category-by-channel preferences | Stable categories with useful control. | Requires typed defaults and a small preference UI, but avoids event-by-event complexity. |

### Recommendation

Use category-by-channel preferences on the organization membership because swap visibility and
planner scope are organization-specific. Start with these categories:

| Category | Events | In-app default | Email default | User can disable |
|---|---|---|---|---|
| `marketplace` | eligible giveaway opened | on, immediate | off; daily digest if enabled | both channels |
| `direct_proposal` | direct proposal targeted | on, immediate | on, immediate | email; in-app can be dismissed but not suppressed |
| `participant_update` | claimed, accepted, withdrawn, rejected, approved, applied, expired | on, immediate | on, immediate | email; in-app can be dismissed but not suppressed |
| `approval_request` | claimed or accepted; pending item withdrawn/expired | on, immediate | on, immediate | email; in-app can be dismissed but not suppressed |
| `expiry_warning` | duty enters warning window | on, immediate | on, immediate | email; in-app can be dismissed but not suppressed |

The durable in-app record for a directly involved participant remains on because it is the
product's authoritative explanation of a roster-affecting workflow. “Cannot suppress” does not
mean “cannot silence”: it creates no external interruption, can be marked read or dismissed,
and is subject to retention. Marketplace notices are optional because they can be frequent and
the user is not yet a participant.

Preferences should be a typed `UserNotificationPreference` row rather than an unversioned JSON
blob on `User`. Columns should be `user_id`, category, `in_app_enabled`, `email_enabled`,
`delivery_mode`, `created_at`, and `updated_at`, with a unique constraint on
`(user_id, category)`. Missing rows resolve through documented code defaults so adding a future
category does not require rows for every user.

This recommendation cannot be approved from the codebase. Product ownership must confirm which
categories may be suppressed and whether mandatory in-app participant records meet the expected
meaning of “preference.”

## Decision 3: works-council and data-protection boundary

Section 87(1)(6) BetrVG covers the introduction and use of technical facilities intended to
monitor employee conduct or performance. The Bundesarbeitsgericht applies an objective test:
technical suitability to collect or record conduct or performance information is enough; the
employer's subjective intent is irrelevant. See
[§ 87 BetrVG](https://www.gesetze-im-internet.de/betrvg/__87.html) and
[BAG, 16 July 2024, 1 ABR 16/23](https://www.bundesarbeitsgericht.de/entscheidung/1-abr-16-23/).

Swap notifications necessarily create individual, timestamped facts about who offered,
claimed, accepted, declined, approved, and acted late. Those facts can be used to compare
working-time behavior even if the feature is described only as coordination. The notification
system is therefore objectively suitable for monitoring and must be taken to the works council
before rollout. This is engineering guidance, not legal advice; counsel and the relevant works
council must determine the applicable agreement and rollout gate.

### Options

| Option | Consequence |
|---|---|
| Retain a full event and delivery history visible to admins | Best support diagnostics, but creates a readily usable per-member behavior log and the highest co-determination and privacy risk. |
| Recipient-private notifications plus aggregate delivery health | Supports the workflow while reducing secondary monitoring capability. |
| Ephemeral delivery with no durable inbox | Minimizes retained data, but cannot support unread state, reliable retries, or an explanation of what changed. |

### Recommendation

Use recipient-private notifications plus non-identifying aggregate delivery health:

- a user may read only notifications addressed to their membership;
- admins and planners do not receive an API for browsing another person's inbox or delivery
  history;
- operational metrics expose counts and failure rates without member, duty, or subject
  breakdown;
- payloads contain only the identifiers and display snapshot required to render the message;
- no derived counters such as “duties offered per member,” rankings, or cross-member history are
  built;
- inbox content and delivery details are retained for 90 days by default, then deleted by the
  worker; the existing audit trail remains governed separately;
- the purpose statement, recipients, event categories, retention, admin visibility, exports,
  and permitted support access are written into the works agreement;
- rollout is gated until the organization records that consultation and the applicable legal
  approval are complete.

The codebase cannot answer whether a works council exists, what agreement already applies, or
whether 90 days is acceptable. Those are mandatory external decisions.

## Decision 4: immediate delivery versus digest

### Options

| Option | Benefits | Cost and risk |
|---|---|---|
| Everything immediate | Simplest dispatch rule and fastest awareness. | A large giveaway pool can generate noise and train users to ignore email. |
| Everything in a daily digest | Low interruption and efficient delivery. | Direct proposals and near-term approval work can wait almost a day. |
| Event-specific delivery | Predictable urgency by category. | Does not account for how close the duty is. |
| Hybrid category plus deadline threshold | Matches both event importance and time remaining. | Requires `deliver_after`, digest grouping, organization time zone, and clear override rules. |

### Recommendation

Use the hybrid:

- direct proposals, participant updates, approval requests, and expiry warnings are immediate;
- marketplace notices are included in one daily digest;
- any marketplace notice for a duty within seven calendar days bypasses the digest and is sent
  immediately;
- the expiry-warning window is three calendar days before the duty;
- expiry occurs on the first sweep after the duty date has passed, matching the current
  `_utc_today` semantics;
- unread in-app state appears immediately regardless of email scheduling.

The seven-day urgency threshold, three-day warning window, digest time, and time zone are product
decisions. The repository has no organization time-zone setting. Before implementation, choose
either an organization time zone or explicitly adopt `Europe/Berlin` for this Germany-focused
product; do not silently use the worker host's local time.

## Proposed records

One row cannot accurately represent both an in-app event and several email attempts. Use a
durable recipient event plus channel deliveries.

### `Notification`

| Field | Purpose |
|---|---|
| `id` | Stable notification identifier. |
| `organization_id` | Tenant boundary and indexed filter. |
| `recipient_user_id` | Organization membership that owns the inbox item. |
| `event_type` | Stable event key such as `swap.targeted`, `swap.claimed`, or `swap.expiry_warning`. |
| `category` | Preference category resolved at creation time. |
| `subject_type` | Initially `shift_swap_request`; leaves room for later subjects without shipping their events now. |
| `subject_id` | `ShiftSwapRequest.id`. |
| `actor_user_id` | Nullable membership actor; null for system sweeps or MCP where no membership actor exists. |
| `payload` | Versioned, minimal JSON display snapshot: swap kind/status, duty date, shift label, and relevant display names. No email address. |
| `created_at` | Event time in UTC. |
| `read_at` | Nullable first-read time. |
| `dismissed_at` | Nullable inbox dismissal time. |
| `expires_at` | Retention deadline. |
| `dedupe_key` | Unique deterministic key per recipient and semantic event. |

Use a unique constraint on `(organization_id, recipient_user_id, dedupe_key)`. A transition key
can include request id and destination status. An expiry-warning key also includes the configured
warning boundary so repeated sweeps do not create duplicates.

Messages should be rendered from `event_type`, payload version, and recipient locale rather than
persisting pre-rendered HTML. The payload snapshot prevents later roster edits from changing the
meaning of an old notification.

### `NotificationDelivery`

| Field | Purpose |
|---|---|
| `id`, `notification_id` | Stable delivery attempt group. |
| `channel` | Initially `email`; in-app availability is represented by the notification row itself. |
| `mode` | `immediate` or `digest`. |
| `status` | `pending`, `sending`, `delivered`, `failed`, `suppressed`, or `not_configured`. |
| `deliver_after` | UTC schedule time. |
| `claimed_at`, `claimed_by` | Safe worker claim and recovery. |
| `attempt_count`, `last_attempt_at`, `last_error_code` | Retry and support state without storing provider response bodies. |
| `delivered_at` | Successful handoff time. |
| `provider_message_id` | Nullable provider reference. |
| `digest_key` | Nullable grouping key for one user and digest window. |
| `created_at`, `updated_at` | Lifecycle timestamps. |

The email address used for a send comes from the recipient's `Account` at delivery time. It
should not be copied into notification payloads. A provider's acceptance is “delivered” for this
system; bounce state can be added only if the selected provider supplies and the product accepts
webhook handling.

## Emission and transaction boundaries

Notification rows and their initial delivery rows must be added before the same `db.commit()`
that persists the successful transition:

- `open_shift_swap`: giveaway-opened or direct-targeted;
- `claim_shift_swap`: claimed plus approval-requested;
- `accept_shift_swap`: accepted plus approval-requested;
- `withdraw_shift_swap`: withdrawn for affected non-actors;
- `reject_shift_swap`: member-declined or planner-rejected;
- `approve_shift_swap`: approved;
- `apply_shift_swap`: applied;
- proposed `warn_due_shift_swaps`: expiry warning;
- proposed `expire_due_shift_swaps`: expired.

`create_shift_swap` emits nothing for a draft. With `open_immediately`, its existing call to
`open_shift_swap` creates the relevant event.

Add one typed helper in a notification service that receives the committed-intent event data,
resolves recipients and preferences, and adds rows to the current session without committing.
The swap service owns when that helper is called. Route handlers, React components, and MCP
tools must not emit notifications.

Email sending begins only after the transaction commits. A notification worker claims pending
delivery rows using the solver worker's PostgreSQL locking pattern, sends them, and records the
result. Retries use bounded exponential backoff. A failed email never rolls back a swap and
never removes the in-app record.

For the atomic claim path, create notifications only after the conditional update reports one
updated row and before its commit. A lost claim race rolls back and emits nothing. Every other
validation or permission failure exits before notification insertion. Tests must assert both
successful event creation and the absence of rows after rejected transitions.

## Scheduled sweep

Add a dedicated notification worker Compose service rather than putting notification behavior
inside the solver worker. It should:

1. claim and send due delivery rows continuously;
2. run `warn_due_shift_swaps` at an idempotent interval;
3. run `expire_due_shift_swaps` at an idempotent interval;
4. purge rows past `expires_at`.

The sweep services query due requests in bounded batches, lock rows with `SKIP LOCKED`, recheck
status and duty date under the lock, create notifications in the same transaction as any status
change, and commit once per batch. Multiple worker replicas must be safe. The lazy
`_expire_if_past` guard remains for request-time correctness but delegates to the same expiry
transition helper.

The interval is not the business schedule. Warning and expiry eligibility are derived from
stored dates and the chosen organization time zone, so a worker restart catches up without
losing events.

## Required API surfaces for a later implementation

- REST: list own notifications, unread count, mark read, dismiss, read/update own preferences.
- MCP: recipient-scoped read resources require an identity model that MCP does not currently
  have. Admin-token access must not expose individual inboxes. Until MCP gains a membership
  identity, MCP parity should cover aggregate delivery health and guarded sweep operations, not
  impersonated personal reads.
- Web: shell unread marker, inbox list, read/dismiss actions, and Settings preferences.
- Worker: token-free internal process using the backend service layer and database session.

The MCP identity limitation is a design blocker for literal inbox parity and must be resolved in
the implementation specification rather than bypassed with `MCP_ADMIN_TOKEN`.

## Decisions that remain external

None of the four open questions can be conclusively answered from the codebase alone:

1. **Channel:** provider, sender domain, budget, bounce operations, and support ownership are
   business and operations decisions.
2. **Preferences:** which categories may be disabled and which defaults are acceptable are
   product decisions.
3. **Works council:** the applicable agreement, consultation result, lawful retention, and
   rollout gate require the relevant works council and legal counsel.
4. **Timing:** urgency thresholds, warning window, digest time, and organization time-zone
   policy are product and operational decisions.

The recommendations in this brief are concrete defaults for that decision round, not decisions
made by the repository.
