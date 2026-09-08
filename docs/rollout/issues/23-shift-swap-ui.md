---
title: "R4: Swap marketplace UI and planner approval queue"
labels: rollout-r4, frontend, ux
---

## Context

The exchange only works if offering a duty is as easy as the capture control from #13, and if
approving is a short queue rather than inbox archaeology.

## Scope

- Team-member portal: offer a duty (giveaway or direct proposal) from the "My shifts" tab and
  from a roster cell; a board of open giveaways for the member's shift groups with a claim
  action; a status list of the member's own requests.
- Planner: an approval queue in the planning workspace showing pending swaps with attached
  warnings, the resulting roster change, and approve/reject actions.
- Candidate suggestions when R3 is available: rank legal partners by fairness impact. Degrade to
  an unranked eligible list when no solver run is available.
- Every state change visible in the UI. No email in this release — notifications are out of scope
  for this rollout.

## Acceptance criteria

- [ ] Offering a duty takes one action from a roster cell or the shifts list.
- [ ] The approval queue shows the roster change and any warnings before approval.
- [ ] Refused swaps state the specific violation in the member's language.
- [ ] Suggestions degrade to an unranked list when no solver run is available.
- [ ] DE and EN strings; works at 360 px.

## Dependencies

Blocked by #22. Suggestion ranking additionally uses #20.

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

Task: build the swap marketplace and the planner approval queue.

1. Read `frontend/app/my-planning/page.tsx` and its "My shifts" tab, plus
   `frontend/components/RosterMatrixEditor.tsx` for the roster-cell interactions.
2. Team-member side: an offer action on a duty (giveaway or direct proposal, with a member
   picker for direct), a board of open giveaways for the member's shift groups with claim, and a
   status list of their own requests.
3. Planner side: an approval queue in `PlanningWorkspace.tsx` showing each pending swap with the
   resulting roster change rendered as before/after and any attached warnings, with approve and
   reject actions.
4. Refusals must be legible: render the violation message the API returns, not a generic error.
   Those strings need DE and EN entries.
5. Candidate suggestions: when a solver run is available, rank eligible partners by fairness
   impact; otherwise show the eligible list unranked. Never block the flow on the solver.
6. Add every string to both dictionaries. Verify at 360 px. Run `npm run lint` and
   `npm run typecheck`.
7. Update `README.md`, `CHANGELOG.md`.
```
