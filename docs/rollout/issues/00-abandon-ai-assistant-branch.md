---
title: "R0: Abandon feat/ai-assistant and record the decision"
labels: rollout-r0, chore
---

## Context

`feat/ai-assistant` carries ~4,300 lines of unmerged work (worker groups, employment periods,
time entries, an hours ledger, AI/Langfuse env placeholders). It is considered unripe and will
not be merged. R1 rebuilds the parts it needs on `main`, designed for statutory evaluation from
the start rather than as a contract-hours ledger with statutory rules added later.

This issue exists so the decision is recorded and the branch does not get revived by accident.

## Scope

- Close any PR from `feat/ai-assistant` with a comment pointing at `docs/rollout/ROLLOUT.md`.
- Delete or clearly rename the branch (e.g. `archive/ai-assistant`) so it is not picked up as
  active work.
- Do the same for the stale duplicates: `feature/ai-assistant`, `feat/work-hours-timesheets`.
- Record the decision and its rationale in `CHANGELOG.md`.
- Confirm `main` is the baseline: `alembic upgrade head` from an empty database, CI green.

## Acceptance criteria

- [ ] No open branch or PR presents the abandoned time model as pending work.
- [ ] `CHANGELOG.md` records the decision and why.
- [ ] `alembic upgrade head` succeeds from an empty database on `main`.

## Dependencies

None. Should happen before #05 so nobody builds on the old model by reflex.

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

Task: formally abandon the `feat/ai-assistant` line of work.

1. List the branches involved: `git branch -a | grep -E 'ai-assistant|work-hours'`.
2. Close any associated PRs with a short comment: the work is superseded by the rollout plan
   in `docs/rollout/ROLLOUT.md`, which rebuilds the employment and time model on `main` with
   dual statutory/tariff valuation designed in.
3. Rename the branches to `archive/<name>` (or delete them if you are confident nothing is
   worth revisiting) so they no longer read as in-flight work.
4. Verify `main` is a clean baseline: fresh database, `cd backend && alembic upgrade head`,
   then `ruff check app && pytest`, and `cd frontend && npm run lint && npm run typecheck`.
5. Add a dated `CHANGELOG.md` entry recording the decision and the reason.
```
