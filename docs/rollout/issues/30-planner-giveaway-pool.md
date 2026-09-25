---
title: "R4: The planner cannot see the open giveaway pool"
labels: rollout-r4, frontend, backend, ux
---

## Context

`ShiftSwapApprovalQueue` filters the request list to `claimed`, `accepted` and `approved`
(`QUEUE_STATUSES`, `ShiftSwapApprovalQueue.tsx:24`). Those are the requests that have found a
counterparty and are waiting for a decision.

The two statuses it drops are the ones a planner actually needs to worry about:

- `open` — a duty was given away and **nobody has claimed it**. The duty is still assigned to the
  original member, who has mentally checked out of it.
- `targeted` — a direct 1:1 proposal that the other member has not answered.

Nothing in the product surfaces either. Expiry is lazy: `_expire_if_past` only fires when
someone happens to touch the row, so an unclaimed giveaway for tomorrow's duty sits in `open`
indefinitely and is reported to no one. The exchange quietly accumulates duties that everyone
believes someone else is handling.

This is the difference between a marketplace and a message board. The planner is accountable for
the roster being staffed; they need to see what the exchange has failed to place, early enough to
act on it.

## Scope

- A planner-facing view of unresolved requests for the selected period and shift group: `open`
  and `targeted`, sorted by how soon the duty falls, with the age of the request and the days
  remaining until the duty.
- Visual urgency by proximity of the duty, not by the age of the request. A giveaway posted this
  morning for a duty in two days matters more than one posted three weeks ago for a duty in
  April.
- Planner actions from that view, reusing the existing service functions: withdraw a stale
  request, and reach the existing approval path once something is claimed. **No new state
  transitions** — if an action the planner needs does not exist in the state machine, that is a
  finding to report, not a transition to invent.
- Whether this is a second panel beside the approval queue or one panel with two sections is a
  judgement call; one panel with a clear separation is probably right, because the planner asks
  one question ("what still needs me?") and should not have to ask it twice.
- Server-side: check whether the existing listing endpoint and the `shift_swaps` MCP resource can
  answer "unresolved for this period and group" without the client filtering everything. If the
  client currently pulls all requests and filters in the browser, fix that here — the filter
  belongs in the service function.
- MCP parity: the same information must be reachable from the MCP resource.

## Out of scope

Notifying anyone (#31). A scheduled job that eagerly expires stale requests — worth doing, but it
belongs with notifications, since expiry that nobody is told about is not much better than no
expiry. Empty and disabled states (#29).

## Acceptance criteria

- [ ] A planner sees every `open` and `targeted` request for the selected period and shift group,
      with days-until-duty and request age.
- [ ] Ordering is by duty date ascending, and urgency styling follows duty proximity.
- [ ] The filter is a service function with pytest coverage, not a `.filter()` in a component.
- [ ] The MCP resource exposes the same unresolved set.
- [ ] No new status transitions were added to `services/shift_swaps.py`.
- [ ] Both dictionaries; `ruff check app`, `pytest`, `npm run lint`, `npm run typecheck`.

## Dependencies

Follows #23. Independent of #29. Shares a boundary with #31 — read that issue before deciding
where eager expiry belongs.

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

Task: give the planner visibility of shift swap requests that have not found a counterparty.

Read docs/rollout/issues/30-planner-giveaway-pool.md in full first, then read
backend/app/services/shift_swaps.py — in particular ALLOWED_TRANSITIONS, ACTIVE_STATUSES and
_expire_if_past — before you design anything. The state machine there is the constraint.

1. Add a service function that returns unresolved requests (status `open` or `targeted`) for a
   planning period and shift group, with the fields the UI needs to sort and rank: duty date,
   days until the duty, request age, offering member, and for `targeted` the member who has not
   answered. pytest coverage for it, including a request whose duty is in the past.
2. Expose it through the REST API and the MCP resource. Do not let the frontend fetch everything
   and filter client-side.
3. Build the planner view next to the existing approval queue in PlanningWorkspace. Sort by duty
   date ascending. Urgency styling follows how soon the duty is, not how old the request is.
4. Planner actions reuse existing transitions only. If the planner plainly needs an action the
   state machine does not allow, STOP and report it — do not add a transition.
5. Both dictionaries, key parity.
6. Do not implement notifications or a background expiry job here; issue #31 owns those.
7. Run ruff check app, pytest, npm run lint, npm run typecheck, and show the new tests passing
   in the PR.
```
