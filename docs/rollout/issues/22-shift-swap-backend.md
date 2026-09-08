---
title: "R4: Shift swap and giveaway requests with legality checks"
labels: rollout-r4, backend
---

## Context

Once a plan is published there is no way for a member to hand over a duty; the only path is a
planner reopening the month. Both requested exchange modes — giving a duty to a pool and
proposing a direct 1:1 swap — need the same legality check against the hypothetical post-swap
state, which the rule layer already supports.

## Scope

State machine on `ShiftSwapRequest`:

```
draft → open ─┬─→ claimed  → approved → applied
              ├─→ targeted → accepted → approved → applied
              └─→ withdrawn / rejected / expired
```

- `giveaway`: offered to the shift group's members; anyone eligible may claim.
- `direct`: proposed to a named member, who accepts or declines; optionally an exchange of two
  duties rather than a one-way handover.
- Legality: build a `PlanState` for the post-swap window and evaluate. `error` findings refuse
  the transition; `warning` findings are attached and shown to the approver.
- Planner approval required before `applied`. Applying writes through the normal assignment
  service and bumps the plan version.
- Claim eligibility is the same eligibility the solver uses — one definition.

## Acceptance criteria

- [ ] A swap breaching a statutory rule is refused, naming the specific violation.
- [ ] A swap producing only warnings reaches the approver with them attached.
- [ ] Applying creates a new plan version and preserves the audit trail.
- [ ] Two members claiming the same giveaway concurrently: exactly one succeeds.
- [ ] A member cannot claim a duty they are not eligible for.
- [ ] MCP read resource plus guarded transition tools.

## Dependencies

Blocked by #04, #09. Independent of R3.

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

Task: implement shift swap and giveaway requests.

1. Model `ShiftSwapRequest` with the states above. Keep the state machine in a service function
   with explicit allowed transitions; do not scatter status checks across routes.
2. Legality checking builds a `PlanState` over the affected window with the swap applied
   hypothetically, then runs the rule registry. `error` refuses the transition; `warning` is
   stored on the request and surfaced to the approver. Reuse the engine — no swap-specific rule
   path.
3. Claim eligibility must reuse the same eligibility computation the solver uses, so a duty
   nobody may legally take is never offered as claimable.
4. Concurrency: claiming a giveaway must be atomic so exactly one of two simultaneous claims
   wins. Add a test that exercises it.
5. Applying goes through `backend/app/services/roster_matrix.py` and bumps the working version
   via `services/plan_versions.py`, exactly as a manual change would.
6. REST under `/api/v1/shift-swaps` with role-appropriate scoping: members act on their own and
   their group's open requests; planners approve within their shift groups.
7. MCP: read resource and guarded transition tools.
8. Tests: each transition, statutory refusal, warning pass-through, concurrent claim, ineligible
   claim, version bump, authorization.
9. Update `README.md`, `AGENTS.md`, `CHANGELOG.md`, `PLAN.md`.
```
