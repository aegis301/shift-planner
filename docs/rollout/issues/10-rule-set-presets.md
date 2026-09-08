---
title: "R1: Ship ArbZG and TV-Ärzte rule-set presets as seed data"
labels: rollout-r1, backend, compliance
---

## Context

Organizations should not derive statutory parameters themselves. Ship presets an admin can adopt
and then adjust.

## Scope

`backend/app/scripts/seed_work_time_presets.py`, idempotent, run from Docker Compose after
migrations:

**`ArbZG-Grundmodell`**
- `max_daily_working_time`: base 8 h, extended 10 h
- `min_rest_period`: 11 h, reducible to 10 h in hospitals with compensation within one month
- `rest_after_long_duty`: trigger 12 h → 11 h uninterrupted
- `weekly_average_cap`: 48 h over 6 months / 24 weeks
- `documentation_requirement`: above 8 h/day

**`TV-Ärzte (TdL)`**
- daily up to 24 h where at least 8 h is Bereitschaftsdienst
- `opt_out_weekly_cap`: 58 h (Stufe I) / 54 h (Stufe II) averaged over 12 months, with a
  documented extension to 66 h by regional agreement
- `max_duties_per_period`: 4 per month, +1 per quarter
- Bereitschaftsdienst valuation: Stufe I 60 %, Stufe II 95 %, +25 pp on public holidays,
  `statutory_factor` 1.0 throughout

**`TV-Ärzte (VKA)`** — municipal hospitals; values to be confirmed before use.

Each rule carries a `source_note` naming the provision, surfaced in the admin UI, plus a visible
disclaimer that presets are engineering defaults requiring confirmation by the works council and
legal counsel.

## Acceptance criteria

- [ ] Seeding twice produces one copy of each preset.
- [ ] Adopting a preset creates an editable, org-owned rule set; the preset is not mutated.
- [ ] Every preset rule carries a `source_note`.
- [ ] A test asserts the TdL opt-out caps, duty limits and Bereitschaftsdienst factors against
      the values above.

## Dependencies

Blocked by #05, #07, #08.

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

Task: add seed presets for statutory rule sets.

1. Follow the existing seed scripts in `backend/app/scripts/` — idempotent, safe to re-run,
   invoked from Docker Compose after `alembic upgrade head`.
2. Create the three presets described above. The Bereitschaftsdienst valuation factors belong to
   the preset because the Stufe determines both the credit factor and which opt-out cap applies;
   adopting a preset therefore seeds contract-group category rules as well as statutory rules.
3. Every rule gets a `source_note` naming the provision, e.g. "§ 5 Abs. 1 ArbZG" or
   "§ 7 Abs. 5 TV-Ärzte (TdL)". Surface it in the API payload and the admin UI.
4. Adoption copies the preset into an org-owned `WorkTimeRuleSet`; the preset row is never
   edited by an organization.
5. Add a disclaimer string to the DE and EN dictionaries stating that presets are engineering
   defaults requiring confirmation by the works council and legal counsel, and render it
   wherever a preset is adopted.
6. Tests: idempotency, adoption copies rather than references, explicit assertion of the TdL
   numbers.
7. Update `README.md` (seed commands), `docker-compose.yml`, `AGENTS.md`, `CHANGELOG.md`.
```
