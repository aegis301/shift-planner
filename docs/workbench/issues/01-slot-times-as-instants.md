---
title: "Defect: roster slot times are local wall-clock values labelled as UTC"
labels: backend, frontend, schema, bug
---

## Context

Part of ADR 0001 (`docs/decisions/0001-desktop-first-workbench.md`, decision 6). It is listed
first because the member app's offline duty-activity capture (#123) cannot be correct until it
lands, and because it is a live defect today.

Roster slot start and end times are generated as **naive local wall-clock** datetimes and then
treated as **UTC** everywhere they are read. Anything that carries a real instant, like the
timestamps the browser sends for duty activity, is compared against them and is off by the UTC
offset of Germany (1 hour in winter, 2 hours in summer).

Where the naive value is created:

- `backend/app/services/shift_templates.py`, `_combine(day, value)` returns
  `datetime.combine(day, value)` with no `tzinfo`. `generate_slots_for_month` feeds it into
  `RosterSlot.starts_at` / `ends_at` (`DateTime(timezone=True)`). On Postgres, whose session time
  zone is UTC in our containers, the stored value becomes "08:00 UTC" for a shift that starts at
  08:00 in Germany.

Where it is read as UTC:

- `backend/app/services/rules/statutory.py`, `_as_utc` and `_slot_interval`
- `backend/app/services/duty_activity.py`, `_as_utc` (also used for the "episode must fall inside
  the slot span" checks around lines 160 to 175)
- `backend/app/services/ics_export.py`, `_resolve_event_times` labels naive slot times as UTC,
  while `_combine_date_time` in the same file uses `Europe/Berlin`. The two paths disagree.
- `backend/app/services/time_entries.py` copies `slot.starts_at` into derived `TimeEntry`
  rows (`source = "roster"`), so derived rows carry the same fake-UTC value.
- `PlanVersionRosterSlot.starts_at` / `ends_at` snapshot the same values.

Where the real instant comes from:

- `frontend/components/DutyActivityControl.tsx` sends `new Date().toISOString()`.
- `frontend/lib/dutyActivity.ts`, `fromDatetimeLocalValue` converts a `datetime-local` input to a
  UTC ISO string.

Effects today:

- A call-out recorded in the first one to two hours of a duty is rejected as outside the slot,
  and every episode is shifted against its slot.
- Rest-period and daily-maximum checks that mix episodes with slots are off by the same amount.
- A night duty across a daylight-saving change counts as 24 h instead of 23 h or 25 h.
- Calendar exports that go through `_resolve_event_times` show shifts 1 to 2 hours late in
  Germany.
- Frontend code parses slot times inconsistently: some paths use `new Date(iso)` (browser time
  zone conversion), others read the hour from the string. See `frontend/lib/dutyActivity.ts`
  (around line 53), `frontend/lib/shiftSwaps.ts` (around line 271), `frontend/lib/shiftOverlap.ts`,
  `frontend/lib/nrwCalendar.ts` (around line 82) and `frontend/lib/fairness.ts` (around line 90).

## Decision for this issue

- Every organization has an IANA time zone, `Organization.timezone`, default `Europe/Berlin`.
- `RosterSlot.starts_at` / `ends_at` store the **real instant**: the wall-clock time of the variant
  on that date, interpreted in the organization's time zone, converted to UTC.
- `slot_date` stays the local calendar date the slot belongs to. It is the planning key and does
  not change.
- Anything that needs a **local** hour or date (night classification, "which calendar day does
  this minute belong to", display, ICS) converts from the instant to the organization's time zone
  explicitly. Nothing reads `.hour` or `.date()` from a UTC instant and treats it as local.
- Naive datetimes read back from the database are UTC. That is only true after this issue, and
  it is what makes the existing `_as_utc` helpers correct. SQLite in the test suite drops `tzinfo`
  on `DateTime(timezone=True)`, so this rule matters for tests.

## Scope

1. **Schema.** Add `organizations.timezone` (`String(64)`, not null, server default
   `'Europe/Berlin'`). Validate against `zoneinfo.available_timezones()` in the service that writes
   it. Expose it on `OrganizationReadForAdmin` and the `PATCH /api/v1/organization` payload
   (`backend/app/api/v1/organization_admin.py`, admin write), on the admin organization settings
   page (`frontend/app/organization/team/organization/page.tsx`) as a select, and in MCP.
2. **Generation.** One helper, for example `local_to_instant(day, clock, tz) -> datetime` in a new
   `backend/app/services/org_time.py`, used by slot generation and by anything else that turns a
   variant clock time into a datetime. `end_day_offset` is applied to the local date before
   conversion, never by adding 24 h to an instant.
3. **Local views.** Helpers `instant_to_local(dt, tz)` and `local_date_of(dt, tz)`, and a sweep of
   every place that derives an hour or a date from a slot or entry time. Known sites:
   - `services/rules/builder.py` `_is_night_duty` (`started_at.hour >= 21`, `ended_at.date()`)
   - `services/shift_swaps.py` `_slot_is_night_duty`
   - `services/rules/shift_constraints.py` around line 686 (`slot.starts_at.date()`)
   - `services/rules/statutory.py` `_slot_duty_minutes_on_day` and friends that split minutes by
     calendar day
   - `services/member_planning_patterns.py` (avoid-time-window matching uses `slot_tz`)
   - `services/ics_export.py`, `services/exports.py`, `services/hours_ledger.py`,
     `services/compliance_report.py`, `services/shift_intervals.py`, `services/solver_runs.py`
   Use `grep -rn "combine(\|_as_utc\|replace(tzinfo\|\.hour\|\.date()" backend/app/services` to find
   the rest and list every site you changed in the PR.
4. **Data migration.** An Alembic migration that converts stored fake-UTC values to real instants:
   `(col AT TIME ZONE 'UTC') AT TIME ZONE org.timezone` for
   - `roster_slots.starts_at`, `roster_slots.ends_at`
   - `plan_version_roster_slots.starts_at`, `plan_version_roster_slots.ends_at`
   - `time_entries.started_at`, `time_entries.ended_at` **only where `source = 'roster'`**
   Do not convert `source = 'duty_activity'` or `source = 'manual'` rows. Those came from the
   browser and are already real instants. Rows with `source = 'day_status'` have no times.
   Join through `planning_periods.organization_id` / `time_entries.organization_id` to get the
   zone.
5. **Frontend.** One formatting module, `frontend/lib/orgTime.ts`, that formats instants with
   `Intl.DateTimeFormat(locale, { timeZone: orgTimeZone, ... })`. The org time zone comes from
   `GET /api/v1/auth/me` (add `organization_timezone` to the `user` payload). Replace the
   string-slicing and `new Date(...).getHours()` readings in the files listed in Context.
   `toDatetimeLocalValue` / `fromDatetimeLocalValue` convert through the org time zone, not the
   browser's.
6. **ICS.** `_resolve_event_times` emits real instants (or `TZID=` local times) consistently with
   `_combine_date_time`.
7. **MCP.** Organization resource exposes `timezone`. Any MCP output that prints slot times keeps
   ISO 8601 with offset.

## Out of scope

- Holiday calendars per region (NRW is still hard-coded in `services/holidays.py` and
  `frontend/lib/nrwCalendar.ts`). Separate issue, not part of ADR 0001.
- Changing `slot_date` semantics.
- Any UI redesign.

## Acceptance criteria

- [ ] `organizations.timezone` exists, defaults to `Europe/Berlin`, is validated, and is readable
      and writable through REST (admin) and MCP.
- [ ] A slot generated for 2026-07-01 08:00 to 2026-07-02 08:00 in `Europe/Berlin` stores
      `2026-07-01T06:00:00Z` to `2026-07-02T06:00:00Z`. Test in `backend/app/tests/`.
- [ ] A 24 h duty starting 2026-10-24 08:00 Berlin (DST ends on 2026-10-25) has 25 h statutory
      minutes. A duty across the March 2027 change has 23 h. Tests.
- [ ] A duty-activity episode posted with the instant a phone would send for 08:30 local on a
      duty that starts 08:00 local is accepted. Today it is rejected. Test.
- [ ] Night classification of a 21:00 to 07:00 local duty is unchanged in summer and winter. Test
      for builder and swap night detection.
- [ ] Migration verified against Postgres: seed a pre-migration database with a roster slot, a
      derived roster `TimeEntry`, a `duty_activity` `TimeEntry` and a plan version snapshot, run
      `alembic upgrade head`, show that roster-derived values moved by the offset and the
      duty-activity values did not. Paste the run in the PR.
- [ ] Frontend shows the same local times as before for existing shifts, in a browser set to
      `Europe/Berlin` and in one set to `America/New_York`. Screenshot both in the PR.
- [ ] `ics_export` produces events at the correct local time. Test.
- [ ] `ruff check app`, `pytest`, `npm run lint`, `npm run typecheck`, `npm run build` green.

## Dependencies

None. Blocks #123. Should land before #117 so the grid never renders fake-UTC times.

## Implementation prompt

```text
You are working in the `aegis301/shift-planner` repository.
Start from the latest `main`: `git fetch origin && git switch -c fix/slot-times-as-instants origin/main`.
Do not continue on a branch from another issue.

Read these before writing any code, and follow them strictly:
1. `AGENTS.md`, especially **Working an issue**, **Style → Frontend surfaces** and **Testing Expectations**.
2. `docs/rollout/STATE.md`, especially **Decisions already made** and **Traps this project has already hit**.
3. `docs/decisions/0001-desktop-first-workbench.md`.
4. This issue's spec in full: `docs/workbench/issues/01-slot-times-as-instants.md`.

Standing rules that matter most here:
- Business logic lives in typed service functions under `backend/app/services/`, never in route
  handlers or React components.
- Every capability is reachable from the web UI, REST and MCP (`mcp-server/mcp_app/server.py`).
  Mutating MCP tools require `MCP_ADMIN_TOKEN`.
- Every user-visible string exists in both dictionaries in `frontend/lib/i18n.ts`.
- Schema changes ship with a forward-only Alembic migration. `pytest` builds SQLite with
  `create_all` and never runs Alembic, so a migration is verified by hand against Postgres.
- Update `README.md`, `CHANGELOG.md`, `PLAN.md`, `AGENTS.md` and `docs/rollout/STATE.md` when
  behaviour, setup, API shape, MCP capability or roadmap changes.
- Before you finish: `cd backend && ruff check app && pytest`, and
  `cd frontend && npm run lint && npm run typecheck && npm run build`.

Task: store roster slot times as real instants in the organization's time zone.

1. Before changing production code, write failing tests that pin the defect: a slot generated
   for a Berlin summer date stores the wrong instant, a duty-activity episode at 08:30 local is
   rejected, and a 24 h duty across the October DST change reports 24 h instead of 25 h. Commit
   them first (marked xfail if you must) so the PR shows the before and after.
2. Add `Organization.timezone` with an Alembic migration (server default `Europe/Berlin`),
   validation against `zoneinfo.available_timezones()`, read and admin write through the existing
   organization service, REST and MCP.
3. Create `backend/app/services/org_time.py` with `local_to_instant`, `instant_to_local` and
   `local_date_of`. Use it in `shift_templates._combine` / `generate_slots_for_month`.
   `end_day_offset` shifts the local date before conversion.
4. Sweep every site that reads an hour or a date from a slot or entry datetime (the spec lists the
   known ones; grep for the rest) and convert through the org time zone. List every changed site in
   the PR description.
5. Write the data migration exactly as the spec describes. Only `time_entries` rows with
   `source = 'roster'` are converted. Verify it on Postgres: `docker compose up -d postgres`,
   check out `main`, `alembic upgrade head`, seed the four row kinds, switch to your branch,
   `alembic upgrade head`, query the rows, paste the output in the PR.
6. Frontend: add `organization_timezone` to the `/api/v1/auth/me` user payload, create
   `frontend/lib/orgTime.ts`, and replace every slot-time parse listed in the spec. No component may
   call `getHours()` on a slot time.
7. Fix `ics_export._resolve_event_times` so both paths agree.

Do not change: `slot_date` semantics, the holiday calendar, anything under `services/solver/`
except where it reads an hour or date from a slot time, and any UI layout.

Stop and report instead of guessing if: the migration would need to convert rows whose `source`
is anything other than the four named here, or a rule's behaviour changes for a slot that does not
cross midnight or a DST boundary. Either means an assumption in this spec is wrong.

Prove it: walk the acceptance criteria one by one in the PR and name the test or the pasted run
that proves each.
```
