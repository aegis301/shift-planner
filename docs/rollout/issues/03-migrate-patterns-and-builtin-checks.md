---
title: "R1: Migrate member planning patterns and built-in checks onto the Rule protocol"
labels: rollout-r1, backend, architecture
---

## Context

Evaluation also covers member planning patterns (`services/member_planning_patterns.py`) and
checks implemented directly in `services/validation.py`. They must join the same rule layer.

## Scope

Port to `backend/app/services/rules/member_patterns.py` and `.../builtin.py`:

- `avoid_time_window` — always `info` on roster, multiple bands via `windows[]`
- `iso_week_cycle` — anchored multi-week on/off cycle; may be `error` when the org's
  `member_pattern_policy` allows it
- `allowed_calendar_week_parity` — legacy even/odd ISO week rule, same policy gate
- `recurring_weekday_status` — writes wishes cells, is **not** a roster rule; keep the
  distinction explicit
- `ROSTER_CONSECUTIVE_WEEKENDS`, `ROSTER_MATRIX_DUPLICATE_DAY`,
  `ROSTER_TEMPLATE_NO_GO_CONFLICT` (including the `manual_override` exemption)

`ROSTER_CONSECUTIVE_WEEKENDS` gains a 7-day lookback so a weekend at the start of a month is
compared against the last weekend of the previous month — currently it is not.

## Acceptance criteria

- [ ] Golden-file parity with current behaviour for in-month cases.
- [ ] A member assigned on the last Saturday of month M and the first Saturday of M+1 produces
      `ROSTER_CONSECUTIVE_WEEKENDS`, with a regression test.
- [ ] The org `member_pattern_policy` gate still decides whether cycle and parity rules may be
      `error`; `avoid_time_window` never can.
- [ ] Wishes-cell materialization is untouched by this change.

## Dependencies

Blocked by #01. Parallel with #02.

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

Task: port member planning patterns and built-in roster checks onto the `Rule` protocol, and
extend the consecutive-weekend check across month boundaries.

1. Read `backend/app/services/member_planning_patterns.py` and `validation.py`. Note which
   pattern types are roster rules and which only materialize wishes cells —
   `recurring_weekday_status` is the latter and must not become a roster rule.
2. Implement the rules listed above in `backend/app/services/rules/member_patterns.py` and
   `.../builtin.py`.
3. Keep the `member_pattern_policy` gate: `iso_week_cycle` and `allowed_calendar_week_parity`
   may be `error` only when the org allows it; `avoid_time_window` is always `info`.
4. Give `ROSTER_CONSECUTIVE_WEEKENDS` a 7-day lookback and evaluate it over `PlanState` so the
   previous month's last weekend counts. Add a regression test.
5. Extend the golden-file test from #02 to cover these codes and assert in-month parity.
6. Do not change wishes-cell materialization in this issue.
7. Update `AGENTS.md` and `CHANGELOG.md`. Run `ruff check app` and `pytest`.
```
