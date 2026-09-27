# Shift Planner Agent Instructions

## Purpose

This project is an AI-first shift planning tool for **healthcare teams**; people on the roster are **team members**, backed by the **`TeamMember`** model and **`/api/v1/team-members`** in the API. **Sign-in** uses **`Account`** (global `email` + `hashed_password`); each **`User`** row is an **organization membership** (`account_id`, `organization_id`, `role`, …). The **`shift_planner_session`** cookie identifies either the **active membership** (**`User.id`**, **`typ`** **`user`**) or—when the signed-in **`Account`** has **no memberships**—the **`Account.id`** (**`typ`** **`account`**); payloads without **`typ`** are treated as **`user`** for backward compatibility. Data is scoped by the membership’s **`organization_id`** the same way as before for `TeamMember`, `ShiftGroup`, `ShiftTemplate`, and `PlanningPeriod` (see `Organization`). The default org id comes from **`Settings.default_organization_id`** (`DEFAULT_ORGANIZATION_ID`, typically `1`). **`POST /api/v1/auth/login`** responds with **`auth_kind`** **`account`** (**`AccountSessionRead`**) or **`user`** (**`UserRead`**); **multiple memberships** picks one **deterministic** active row (**`organization.slug`** ascending, then **`users.id`** ascending). **`get_current_user`** returns **`403`** **`account_session_incomplete`** on an account cookie; onboarding uses **`get_current_account_session`**. **`POST /api/v1/auth/me/active-organization`** (membership cookie) switches **`User`** in the cookie; **`POST /api/v1/auth/me/add-organization-membership`** (signed-in **`User`**, password re-verified) requests another org as **`applicant`**. **`GET /api/v1/auth/me`** is the same union as login (**`memberships`** and planner fields appear on **`user`** only). The app shell and **Settings** list orgs after login; **`/login`** does not collect **`organization_slug`**. After org switch or onboarding, redirects follow capability defaults (same as post-login routing).

**Admins** (`User.role` `admin`) manage team members (`TeamMember` rows), contract groups, dated employment periods, opening balances, shift groups, shift templates, create and delete planning months, publish state, wishes and roster matrices, notes, validation, and exports.

**Planners** (`User.role` `planner`) use the same planning surfaces for **existing** months: wishes matrix, roster matrix, **per-shift-group** planning status transitions (`draft`, `preliminary`, `published`), **sync roster** from current templates (`POST /api/v1/planning-periods/{id}/sync-roster`, preserves assignments on unchanged slots), regenerate roster (optionally scoped to one shift group; clears assignments in scope), validation, exports, workload stats, the **compliance report**, and **fairness accounts**, but only for shift groups listed in **`user_shift_groups`**. They receive a **read-only team member list** (from `/api/v1/team-members`) filtered to people who belong to at least one of those groups (intersection). They must pass **`shift_group_id`** on matrix, roster, validation, status transitions, sync/regenerate roster, CSV export, compliance-report, fairness-account, solver-run, and shift-swap APIs. They do not mutate `TeamMember` rows, templates, or shift-group membership.

**Applicants** (`User.role` `applicant`) are users who registered to **join** an existing organization and are waiting on an admin to approve an **`organization_join_request`** (create `TeamMember` + link, or link to an existing unlinked `TeamMember`). They sign in with **email + password** on **`POST /api/v1/auth/login`**; when an account spans several memberships, login picks **one deterministic** **`User`** row (**`organization.slug`**, then **`users.id`**). With no pending request (e.g. after reject or cancel), they may **`POST /api/v1/auth/me/join-request`** to submit a new request. They have no planning or team-member-portal capabilities until approved (role becomes `team_member`).

**Team members** are `TeamMember` rows; a user with a linked `TeamMember.user_id` uses `/my-planning` and `/profile` behavior (wishes, notes, self profile) and reads the roster matrix in `preliminary` and `published` status for the **selected shift group**, subject to shift-group scope. Team-member wishes matrix edits (day status, wish/no-go intents, day comments, month summary notes) are writable while **that shift group's** plan is `draft` or `preliminary` and read-only when that group is `published`. The same user may also be `admin` or `planner` with overlapping capabilities; on **`auth_kind`** **`user`**, **`GET /api/v1/auth/me`** exposes **`capabilities`** (`admin`, `planning`, `team_member_portal`) plus **`team_member_id`, `planner_shift_groups`, and `shift_groups` so the UI merges nav items correctly ( **`account`** payloads omit membership-scoped planner fields ). For `GET /api/v1/roster-matrix/{id}`, **`team_member_portal=true`** selects the team-member read path; omit it (default) when the client is the **planning** workspace so admins and planners—including planner accounts that also have a linked team member—edit draft rosters under `assert_planning_shift_group_scope`. The same flag on **`GET|PUT /api/v1/matrix/{id}`** (and related cell/note/intent routes) limits wishes-matrix payloads and writes to the linked **`TeamMember`** row on **`/my-planning`**; omit it on **`/planning`** for the full team matrix.

**Registration and org codes:** `organizations.slug` is globally unique and human-readable. Business logic lives in `app/services/registration.py`, `app/services/join_requests.py`, `app/services/organization_invites.py`, `app/services/organization_lifecycle.py`, and `app/services/organizations.py`; REST mirrors those services. **`Account.email`** is globally unique; **`User`** has **`UniqueConstraint(account_id, organization_id)`**. **`POST /api/v1/auth/register`** creates **`Account`** only ( **`password_confirm`**) with an account session. **`POST /api/v1/auth/me/onboarding/create-organization`** / **`POST /api/v1/auth/me/onboarding/join-organization`** use **`get_current_account_session`** and rotate the cookie to **`User.id`** after the org step. Reused emails on create/join verify **`Account`** and add memberships; **`register_*`** and onboarding call the shared services. **`POST /api/v1/auth/register/create-organization`** / **`POST /api/v1/auth/register/join-organization`** keep one-shot registration ( **`password_confirm`**). Signed-in users can request another org as applicant via **`POST /api/v1/auth/me/add-organization-membership`** and can create their own new org at any time via **`POST /api/v1/auth/me/create-organization-membership`** (becomes admin in the new org; cookie switches there). Admin **membership invites** use **`POST /api/v1/organization/invites`**; **`/api/v1/auth/me/organization-invites`** is separate from **`organization_join_requests`**. **`DELETE /api/v1/organization`** requires typed **`name`**; **`DEFAULT_ORGANIZATION_ID`** is protected. **`/login`** / **`/register`** do not ask for **`organization_slug`**; **Settings** plus **`POST /api/v1/auth/me/active-organization`** cover switching.

**Account deletion:** **`POST /api/v1/auth/delete-account`** with **`password`** works under account or **`User`** session (`delete_own_account`); removes **`Account`** and **all** memberships after sole-admin checks.

**Password recovery (no email):** Forgot-password flow is admin-assisted: users contact an org admin, who sets a new password in **Team** → staff directory (**`POST /api/v1/organization/users/{id}/reset-password`**, admin only, not self). Updates global **`Account.hashed_password`** (all org memberships for that email). Signed-in users use **`POST /api/v1/auth/me/change-password`** (current + new + confirm). Existing sessions stay valid until cookie expiry.

**Org staff directory (admin):** **`GET /api/v1/organization/staff-directory`** lists one merged row per normalized email (`User` + `TeamMember` in the org) with **`link_status`** (API values such as `team_member_only` mean team-profile-only, login-only, unlinked, linked, mismatches). **`GET /api/v1/organization/users`** still returns raw `User` rows with linked team-member labels. Admin **Team** UI lives under **`/organization/team`**: one **staff directory** table with a row detail modal for team profile editing (same **`PATCH /api/v1/team-members/{id}`** surface as before), roles, unlink, remove, and copy IDs; **`/organization/team/members`** redirects here; the other tab is **join requests**. **`/organization/users`** redirects to **`/organization/team`**. Admins may **`DELETE /api/v1/organization/users/{id}`** to remove another **membership** in the org (not self, not sole admin)—this **deletes** that **`User`** row; if it was the account’s last membership, the **`Account`** is removed too (otherwise the person keeps other org logins). They may **`PATCH /api/v1/organization/users/{id}`** with **`{ "role" }`** to assign **`admin`**, **`planner`**, or **`team_member`** (cannot demote the sole admin; planner shift-group links cleared when role is not planner), and **unlink** a team-member login via existing **`PATCH /api/v1/team-members/{id}`** (clears **`TeamMember.user_id`** only; the user account remains). **Shift admin** UI is grouped under **`/organization/shifts`** (groups and types tabs; index redirects to groups).

**Subscription hooks:** `Organization` carries optional `seat_limit`, `billing_customer_id`, and `subscription_status` for future billing; linking a team-member login enforces seat limits when `seat_limit` is set.

**Organization time zone:** `organizations.timezone` is an IANA name (default `Europe/Berlin`), validated with `zoneinfo.available_timezones()`. Admins read and write it on `GET|PATCH /api/v1/organization`; MCP exposes `shift-planner://organization` and token-gated `update_organization_settings_tool`. User sessions from `GET /api/v1/auth/me` include `organization_timezone`. `RosterSlot.starts_at` / `ends_at`, roster-derived `TimeEntry` bounds (`source=roster`), and plan-version slot snapshots store the UTC instant of the variant wall clock on the local `slot_date`. `end_day_offset` shifts that local date before conversion. `slot_date` stays the planning date. Night flags, overlap days, avoid-windows, ICS events, and export labels convert through the org zone (`app/services/org_time.py`). Statutory minutes are the real elapsed interval: a 24 h wall-clock duty that contains the autumn clock change is 25 h, and one that contains the spring change is 23 h. Duty-activity and manual time entries are instants already and are not reinterpreted.

## Where things live

Start here before reading the rest of this file.

| Concern | Module |
|---|---|
| Rule evaluation, `PlanState` | `app/services/rules/` — `builder`, `protocol`, `registry`, `shift_constraints`, `member_patterns`, `builtin`, `statutory` |
| Contract terms, employment | `contract_groups.py`, `employment_periods.py` |
| Time ledger, duty activity | `time_entries.py`, `duty_activity.py`, `duty_utilization.py`, `duty_activity_privacy.py` |
| Statutory configuration | `work_time_rule_sets.py`, `work_time_presets.py`, `work_time_preset_catalog.py`, `work_time_consents.py` |
| Duty valuation | `work_time_valuation.py` — statutory minutes and tariff credit are two independent numbers and stay that way |
| Reporting | `compliance_report.py`, `fairness.py`, `workload.py` |
| Roster solver runs | `solver_runs.py`, `solver/` (`model.py`, `objective.py`, `solve.py`), `scripts/solver_worker.py` |
| Shift swaps | `shift_swaps.py` — `ShiftSwapRequest` state machine, legality via `evaluate_plan_state`, claim eligibility via `eligible_members_for_slots` |
| Realistic test data | `app/scripts/seed_solver_fixture.py` — profiles `comfortable`, `tight`, `infeasible`, `arbzg` |
| Decisions, frontend direction | `docs/decisions/` (ADR 0001: desktop-first workbench, mobile-first member companion) and `docs/workbench/issues/` |

Two invariants that are easy to break and expensive to unbreak:

- **`PlanState` is built from a date window, never a `planning_period_id`.** Month-scoped
  evaluation silently misses rest-period and coupling violations across month boundaries.
- **Statutory working time and tariff credit are never summed or collapsed into one figure.**
  A Bereitschaftsdienst counts 100 % toward ArbZG limits and 60 % (Stufe I) toward the time
  account. One number cannot be both.

---

## Architecture

- Backend: Python, FastAPI, SQLAlchemy, Alembic, Postgres.
- Frontend: Next.js App Router, TypeScript, Tailwind CSS. The planner workbench is desktop-first and the member companion is mobile-first (PWA-ready); see **Style** and [ADR 0001](docs/decisions/0001-desktop-first-workbench.md). A native member app (Expo) is planned as a second client of the same REST API.
- MCP: FastMCP from the start. MCP tools and resources must reuse the same backend service layer as REST endpoints. MCP targeting uses **`MCP_ORGANIZATION_ID`** when set, otherwise the default organization id (see `README.md`); it is not tied to a browser user’s active membership.
- Runtime: Docker Compose for local development with Postgres, backend, **solver-worker**, frontend, and MCP services. Production-oriented stack and Cloudflare/GitHub Actions notes live in [deploy/README.md](deploy/README.md) and [docker-compose.prod.yml](docker-compose.prod.yml).

## AI-First / FastMCP Rule

Every feature must be designed so it can be controlled by a web UI, REST API, and LLM through MCP. When adding functionality:

- Put business logic in typed service functions, not directly in route handlers or React components.
- Use stable identifiers and structured request/response schemas.
- Return predictable validation errors and warnings.
- Consider whether a read resource and/or guarded mutating FastMCP tool should be added.
- Update MCP docs and tests when MCP-visible behavior changes.
- Mutating MCP tools must require explicit authorization, currently through `MCP_ADMIN_TOKEN`.

## Contract groups and employment

### Contract groups, employment periods, opening balances

Organizations define **`ContractGroup`** rows (`GET|POST|PATCH|DELETE /api/v1/contract-groups`; planning-user read, admin write). Each group stores `weekly_hours_at_100` and `vacation_days_at_100` as `Numeric`, a regular week pattern, per-template-category credit rules (`credit_mode` duration/factor/none, `credit_factor` only when factor, `holiday_credit_bonus`, **`statutory_factor`**, `call_outs_count_as_work`), and day-status `status_mappings`. **`EmploymentPeriod`** is the source of truth for employment percentage (non-overlapping per member, `400` on overlap). **`TimeAccountOpening`** holds one opening balance per member. Reads of employment percentage go through `employment_percentage_on(member, date)`. Admin UI: **Team** → **Verträge** (`/organization/team/contract-groups`) and staff-directory row detail. MCP: `shift-planner://contract-groups` plus token-gated create/update/delete and employment-period/opening tools. 

### Time entry ledger

**`TimeEntry`** is the dated ledger (`GET|POST /api/v1/time-entries`, reconciliation, `POST .../derive`, `GET .../ledger`; MCP `shift-planner://time-entries/{team_member_id}`, `get_hours_ledger_tool`, and token-gated upsert/derive). Derivation reconciles roster and mapped day-status sources and never overwrites `manual` rows or `corrected_fields`. Linked members use **`/my-hours`**; planners/admins use **`/hours`** (planners must pass `shift_group_id`). Statutory and credited minutes stay separate; the running account adds opening overtime to credited minutes that count toward the contract, then subtracts the contract-target minutes from the week pattern. 

### Statutory rule sets and presets

**`WorkTimeRuleSet`** is org-scoped, named, and versioned (`GET|POST|PATCH|DELETE /api/v1/work-time-rule-sets`; planning-user read, admin write). Only one set is active; editing a set referenced by **`PlanningPlanVersion.work_time_rule_set_version_id`** creates version N+1. Seed presets (`ArbZG-Grundmodell`, `TV-Ärzte (TdL)`, `TV-Ärzte (VKA)`) are adopted via **`POST /api/v1/work-time-rule-sets/presets/{code}/adopt`** (copies rules; TdL/VKA also seed Stufe contract groups). Admin UI: **Team** → **Arbeitszeitregeln**. MCP: `shift-planner://work-time-rule-sets` plus token-gated tools. The active set’s rules evaluate in `app/services/rules/statutory.py` during validation and assignment preflight. **`WORKTIME_MAX_DUTIES`** counts only configured template **`categories`** (default **`bereitschaftsdienst`**). 

### Opt-out consents

**`WorkTimeConsent`** stores dated opt-out records (`GET|POST /api/v1/team-members/{id}/work-time-consents`, revoke); `applicable_weekly_cap` resolves the weekly cap per date. Records are immutable; corrections insert a new row. Revocation lists affected future published plan versions and does not rewrite them. MCP: `shift-planner://team-members/{id}/work-time-consents` plus token-gated record/revoke tools. Admin UI: staff-directory row detail; linked members see a read-only card on `/profile`. 

### Duty activity log

**Duty activity** episodes are `TimeEntry` rows with kind `call_out` or `in_duty_activity` (`GET|POST /api/v1/duty-activity`, `PATCH /api/v1/duty-activity/{id}` to stop or annotate, revoke via delete). Both require an assigned `roster_slot_id` plus `started_at` inside the slot; `ended_at` may be omitted to start a running episode. Overlaps on the same slot are rejected. `call_out` feeds `statutory_work_minutes` and rest interruption; `in_duty_activity` adds no statutory time. `app/services/duty_utilization.py` reports per-slot and aggregate utilization, tariff band, `exceeds_on_call_threshold`, and coverage from the active set’s `duty_utilization_bands`. Linked members see one-tap start/stop on `/my-planning` and the team-member dashboard, plus retrospective entry on the My shifts tab; `GET /api/v1/duty-activity/slots/{id}/utilization` returns the band for an assigned slot. Planners/admins read aggregates only unless `DutyActivityAccessPolicy.individual_read_roles` grants them; default individual reads are 403. The same rule covers every other path that returns `TimeEntry` rows: `GET /api/v1/time-entries`, `/time-entries/ledger` (entries and reconciliation) and `/time-entries/reconciliation` drop duty activity kinds unless `can_read_individual_duty_activity` (in `duty_activity_privacy.py`) allows the caller; ledger totals still include their minutes. `get_hours_ledger` takes a required `reveal_duty_activity`, so a new caller has to decide. MCP has no user and reveals episodes only when `MCP_DUTY_ACTIVITY_INDIVIDUAL_READ=true`. REST purpose acknowledgement is required before a member records via `/api/v1/duty-activity`. Retention purge lives in `duty_activity_privacy.py` and `python -m app.scripts.purge_duty_activity`. Works-council export is aggregate-only with small-group suppression. Admin UI: **Team** → **Diensttätigkeit**; purpose card on `/profile`. MCP: `shift-planner://duty-utilization/{planning_period_id}`, `shift-planner://duty-activity-access-policy`, `shift-planner://duty-activity/works-council/{planning_period_id}`, plus token-gated `record_duty_activity_tool`, `update_duty_activity_tool`, `update_duty_activity_access_policy_tool`, and `purge_duty_activity_episodes_tool`. 

### Compliance report

**Compliance report** (`GET /api/v1/compliance-report/{planning_period_id}`, XLSX/PDF under `/api/v1/exports/compliance-report/{id}.xlsx|.pdf`) is built from `evaluate_plan_state` findings plus rule-layer metrics (statutory vs tariff credit, rolling weekly average and cap source, rest/compensation, consecutive days, duty counts, documentation coverage). The active rule-set version and generation timestamp are printed on every export. Admins may omit `shift_group_id`; planners must pass one of their groups. Planning workspace Analysis tab. MCP: `shift-planner://compliance-report/{planning_period_id}`. 

### Fairness accounts

**Fairness accounts** (`GET /api/v1/fairness/{planning_period_id}`) compute rolling actual / expected / deviation per member and dimension (duties, weekend/holiday, night, statutory hours) from `PlanState` history aggregates — duty counts come from `TimeEntry` rows with `source=roster`, not a year of `RosterSlot` rows. Expectation is the sum of per-month shares from `EmploymentPeriod.employment_percentage`, contract-group `weekly_hours_at_100`, and that month’s period roster; joiners are measured only for months they were on `planning_period_shift_group_members`. Opening values live in `TimeAccountOpening.fairness_balances` (and `overtime_minutes` for statutory hours). Dimensions and window length are org JSON (`fairness_policy`; `GET|PATCH /api/v1/organization/fairness-policy`); adding a dimension does not need a migration. Computing 30 members over 12 months stays under 2s with a member-count-independent query set and no history-window slot scan. MCP: `shift-planner://fairness/{planning_period_id}` plus token-gated `update_fairness_policy_tool`. Planning workspace Analysis tab shows actual / expected / deviation per dimension over the rolling window; the roster picker shows the slot-relevant deviation from the same payload (one fetch per period, not per candidate).

### Solver runs

**Solver runs** persist asynchronous roster generation (`SolverRun`: `queued` / `running` / `succeeded` / `failed` / `cancelled`). `POST /api/v1/planning-periods/{id}/solver-runs` returns immediately with a run id; a Compose **solver-worker** claims queued rows with `SELECT ... FOR UPDATE SKIP LOCKED` (Postgres) and an atomic `UPDATE ... WHERE status='queued'`. Parameters always store `num_search_workers` (default `1`) and a `random_seed` (generated per run if omitted). Per-run `time_budget_seconds` is capped by `Organization.solver_time_budget_ceiling_seconds` (default 120). Optional `objective_weights` on create override `Organization.solver_objective_weights` for that run (`GET /api/v1/organization/solver-config` seeds the planning form). `solve_roster` builds a CP-SAT model from explicit eligibility masks and rule `to_cpsat` (never `evaluate()` per candidate). Tier A constraints are encoded now; ArbZG rest / weekly-average stay post-solve. Unfilled slots are a penalized slack variable. Pre-assigned cells are fixed when `overwrite_existing` is false. Objective weights live on `Organization.solver_objective_weights` (unfilled dominant, then duty-count, fairness, wishes, `avoid_time_window`; no no-go term). Applying (`POST .../solver-runs/{run_id}/apply`) writes ordinary `RosterSlotAssignment` rows through `upsert_roster_slot_assignment` and is never automatic. Published shift groups are refused with 409, like regenerate/sync. Planning workspace: generate from the toolbar, poll, inspect, confirm-apply. MCP: `shift-planner://solver-runs/{planning_period_id}/shift-group/{shift_group_id}` plus token-gated `run_roster_solver_tool`, `apply_solver_run_tool`, `cancel_solver_run_tool`. Alembic `202609210002` (runs) and `202609210003` (objective weights).

### Shift swaps

**Shift swaps** persist giveaway and direct 1:1 exchange requests (`ShiftSwapRequest`: `draft` → `open` → `claimed` / `targeted` → `accepted` → `approved` → `applied`, or `withdrawn` / `rejected` / `expired`). `POST /api/v1/shift-swaps` creates a request for a duty the linked member currently holds; `POST .../{id}/open` publishes a giveaway or targets a named member. Claiming a giveaway is an atomic `UPDATE ... WHERE status='open'` so exactly one of two concurrent claims succeeds. Eligibility reuses `eligible_members_for_slots` (the solver's service masks plus mask-phase `to_cpsat`). Legality builds a date-window `PlanState` with the swap overlaid and runs `evaluate_plan_state`: `error` findings refuse the transition and name the violation; `warning` findings are stored on the request for the approver. Swap legality evaluates two states for the same window: roster rules run on the group-scoped state, whose cells and intents match its assignments, and statutory working-time rules run on `build_plan_state(..., shift_group_id=..., member_duties_org_wide=True)` via `evaluate_plan_state(..., statutory_state=...)`. That state keeps the group's members and slots but loads every assignment an in-scope member holds in any group, so rest, daily-limit and consecutive-day rules see duties in other shift groups, matching the org-wide assignment preflight, while a group's wishes and statuses never judge a duty in another group. The claimant list (`list_eligible_claimants`) also drops candidates whose claim would produce an `error` finding, because the mask does not yet encode tier-B rules such as `min_rest_period`. Other scoped callers (fairness accounts, compliance report, dashboard, validation, solver) keep the default where `shift_group_id` also scopes assignments; fairness pools and duty counts are per group by design. Applying (`POST .../{id}/apply`) writes through `upsert_roster_slot_assignment` (source `shift_swap`) and snapshots a new plan version (`trigger` `swap_apply`) even when the group is published. Members offer from **My shifts** or an own roster cell, claim open giveaways, and track their own requests on `/my-planning`. A missing shift group, an unlinked account, and a draft plan each name the fix; draft offer buttons stay visible and disabled, and past slots stay hidden. Planners see unresolved `open` and `targeted` requests plus the approval queue on the Analysis tab of `/planning` (`GET /api/v1/shift-swaps/unresolved`; listing also accepts `statuses`), with duty-date order, days-until-duty, and withdraw of stale offers through the existing transition. An empty queue is distinct from a missing shift group, and planners who are also team members get a link to `/my-planning`. Eligibility lists are ranked by slot-relevant fairness deviation (under-served first) and fall back to sorted IDs if fairness cannot be built. MCP: `shift-planner://shift-swaps/{planning_period_id}/shift-group/{shift_group_id}`, `.../unresolved`, `shift-planner://shift-swaps/request/{request_id}`, plus token-gated create/open/claim/accept/withdraw/approve/reject/apply tools. Alembic `202609220001`.

## Team member properties

Admins manage org-scoped property definitions (`GET|POST|PATCH|DELETE /api/v1/team-member-property-definitions`) and per-member values (`GET|PUT /api/v1/team-members/{id}/property-values`). Types: `number`, `date`, `select`, `multi_select`, `text`. `editable_by_team_member` gates self-service writes on `/profile`. Business logic in `team_member_property_definitions.py` and `team_member_property_values.py`; MCP mirrors REST with admin token.

**Nickname:** Optional `team_members.nickname` (max 64) is editable on `/profile` (`PATCH /api/v1/auth/me/team-member`) and admin `TeamMember` CRUD. Wishes matrix, final roster, planning validation/workload, and roster/matrix exports show **nickname** when set, otherwise **last name** (`team_member_planning_display_name` in `team_members.py`; `MatrixTeamMember.nickname` in API payloads). Staff directory and admin pickers keep full first + last name.

## Shift groups (Dienstgruppen)
Team members (`TeamMember` rows) can belong to multiple shift groups through **dated membership stints** (`start_date`, optional `end_date`) on `team_member_shift_groups`; removing someone end-dates the active stint instead of deleting history. Admins edit exact periods with **`PUT /api/v1/shift-groups/{id}/memberships`** (`memberships[]` of `team_member_id`, `start_date`, `end_date`; several non-overlapping periods per person enable rotation tracking) or keep using **`PUT /api/v1/shift-groups/{id}/team-members`** (`team_member_ids`, interpreted as active today). Reads expose **`team_member_ids`** (active today) and **`team_member_memberships`**; `TeamMemberRead` adds **`shift_group_memberships`**. MCP mirrors this with **`set_shift_group_memberships_tool`**. Admin UI: the shift-group editor lists each membership period with start/end date inputs and an active/planned/ended badge. Each **planning month** stores its own roster per shift group in `planning_period_shift_group_members`, seeded when the month is created from stints overlapping that calendar month plus anyone who already has data in that month. Matrix, roster, validation, and plan-version columns use the **period roster**, not live membership—so past months stay stable when group membership changes later. **Admins** may omit `shift_group_id` on planning reads/exports for a full-org view; the **wishes matrix** still returns `shift_templates`, `template_slot_days` (each row includes `shift_group_id`), and `shift_intents` so wish/no-go editing matches the filtered experience. **Planners** must supply `shift_group_id` (and it must appear in `user_shift_groups`). Roster assignment is rejected when the assignee is not on the period roster for a group covering the slot’s template (templates with no group remain assignable by any roster member). Admin UI: `/shift-groups`; planning toolbar: shift group selector and `?shiftGroup=` URL param. Destructive **create/delete planning month** actions are admin-only in API and UI; mutating MCP tools remain admin-token gated.

## Dashboard

`/` is a data-driven home with capability-gated tabs (admin / planner / team member), mirroring the planning workspace tab pattern. Aggregates live in `app/services/dashboard.py` and `app/services/workload.py`; REST under `/api/v1/dashboard/*`. Planners and team members require `shift_group_id` when scoped to multiple groups. Deep links use `?period=` and `?shiftGroup=` on `/planning` and `/my-planning`.

## Planning day status (Tagesstatus)

Organizations define wishes-matrix day statuses via `planning_day_status_definitions` (`GET|POST|PATCH|DELETE /api/v1/planning-day-status-definitions`; reads for any signed-in member, writes admin-only). Each row has stable `code` (stored on `planning_cells.status`), single org-defined `label`, `color_preset`, `blocks_roster_assignment`, and `is_active`. Lists sort alphabetically by `label` (then `code`). New orgs and the migration seed the former defaults (`urlaub`, `forschung`, `lehre`, `frei`). Admin UI: **Team** → **Tagesstatus** (`/organization/team/day-statuses`). Matrix and roster payloads include `day_status_definitions` for the picker and legend.

**Org-defined display names:** `ShiftGroup`, `ShiftTemplate`, and planning day status definitions each store one user-entered display field (`name` or `label`). The UI locale switch (DE/EN) applies to system strings in `frontend/lib/i18n.ts` only, not to org content.

## Matrix Planning Rule
The active planning workflow uses two monthly matrices:

- Wishes matrix: rows are days, columns are team members, and each cell has exactly one org-defined day-level status plus an optional comment per **shift group**, backed by `PlanningCell` (scoped by `shift_group_id`) and `TeamMemberPeriodNote` (scoped by `shift_group_id`). Per shift group, `PlanningShiftIntent` stores a wish or no-go per `team_member_id`, date, and shift template; the planning API returns intents when `shift_group_id` filters the matrix. Planning lifecycle status is stored per month **and shift group** in `planning_period_shift_group_statuses`; `POST /api/v1/planning-periods/{id}/publish|preliminary|draft` require `shift_group_id`. **Plan versions** (`planning_plan_versions` + snapshot child tables) store immutable roster + wishes snapshots per shift group with semver labels (`0.1` first preliminary, `1.0` first publish, minor bumps on reopen/manual save). **Published** shift groups are read-only for planner roster/wishes writes; reopen to `preliminary` to edit.
- Final roster matrix: rows are days, and each day shows concrete generated shift slots. Each cell assigns one team member to one roster slot. This is backed by `RosterSlot` and `RosterSlotAssignment`.

## Shift Template Rule
Shift configuration must use `ShiftTemplate` and `ShiftVariant`. Do not add compatibility code for old simple shift-type, availability-request, or direct roster-assignment schemas. Variants define applicability via coarse **`start_day_class`** / optional **`end_day_class`** (`any`, `weekday`, `weekend`, `holiday`) or optional **`start_weekdays`** / **`end_weekdays`** allowlists (`mon`…`sun`); when allowlists are set, day-class matching on that side is ignored. **`include_holidays`** (per variant, default false) controls whether a public holiday on an allowed weekday still generates a slot. Variants also define start/end time, inferred **`end_day_offset`**, and required count. Slot generation must use the North Rhine-Westphalia German holiday calendar; holidays behave like weekends unless an explicit holiday variant exists (unchanged when weekday allowlists are empty). Template categories are currently limited to `bereitschaftsdienst`, `rufdienst`, `spaetdienst`, and `other`, displayed as `Bereitschaftsdienst` / on-call duty, `Rufdienst` / stand-by duty, `Spätdienst` / late duty, and `Andere` / other. Optional **`valuation_override`** (same payload as a contract-group category rule) wins over the group rule so a Bereitschaftsdienst-Stufe can attach to a template. Dual valuation lives in `app/services/work_time_valuation.py` (`statutory_work_minutes`, `tariff_credit_minutes`); holiday credit bonus is percentage points added to the credit factor via `classify_day`. Derived `TimeEntry` rows store `statutory_minutes` and `credited_minutes` at first derivation and do not rewrite them when contract-group factors change later. Templates and variants can each store constraints with per-rule **`severity`** (`info`, `warning`, `error`); **`error`** blocks roster assignment in the assignment preflight path. Legacy **`enforcement`** (`warning` / `block`) is accepted on input and mapped. Rule types: `no_additional_same_day`, `min_rest_hours`, `unavailable_overlap_policy` (template override for global overlap blocking: `allow`, `warn`, `block`; legacy `no_cross_day_into_unavailable_day` maps to the same policy), `max_assignments_per_month`, **`requires_coupled_shift`** (unidirectional: variant A requires the same person to be assigned to a chosen partner variant on **`slot_date + partner_day_offset`** within the same planning month, with **`paired_shift_variant_id`**; **`error`** blocks saves when the partner assignment is missing), and **`team_member_property_requirement`** (boolean expression over org **`team_member_property_definitions`** / stored values: nested **`all`**, **`any`**, and **`atom`** nodes in JSON field **`property_requirement`**; **`ROSTER_CONSTRAINT_TEAM_MEMBER_PROPERTIES`** on mismatch; default **`warning`** allows save). Reverse coupling needs a second rule on the partner variant if desired.

Validation compares final roster assignments against day-level wishes on **every calendar day the shift overlaps** (**`ROSTER_MATRIX_UNAVAILABLE_OVERLAP`**, default **`error`**; templates may opt out or downgrade via `unavailable_overlap_policy`), template no-gos unless the assignment uses `manual_override`, active template/variant constraints from the shared constraints engine, recurring **team-member planning patterns** (`avoid_time_window` is always info-only on roster and may list **several time windows** in `windows[]`; **`iso_week_cycle`** (per-member anchored multi-week on/off cycle with optional weekday-only wishes and `allow_weekend_roster`) and legacy **`allowed_calendar_week_parity`** may be `error` when allowed by org `member_pattern_policy` and write wishes cells on off weeks/days, merged with `recurring_weekday_status` by pattern order; `recurring_weekday_status` fills wishes cells on selected weekdays and is not a separate roster rule), and a built-in **consecutive calendar weekends** check (**`ROSTER_CONSECUTIVE_WEEKENDS`**, warning): a team member with roster work on Saturday or Sunday in two weekends whose Saturdays are exactly seven days apart is flagged (Sunday assignments roll up to that weekend’s Saturday). The roster UI surfaces day status and wish/no-go hints in the team member picker, with conflicts highlighted.

The primary planner workflow is `/planning`; linked team members use `/my-planning` (tabbed **Wishes**, **Roster**, **My shifts**) and `/profile`. Planning owns the selected month and renders wishes, final roster assignment, inline validation, CSV export actions, workload stats, the **compliance report** and **fairness accounts** on the Analysis tab, and (for team members) personal `.ics` calendar exports together for planners. It must support both the full stacked view and a tabbed Wishes/Roster/Analysis view. Do not reintroduce separate frontend pages for wishes, roster, validation, or export unless the product direction changes.

Syncing roster slots from current shift templates (`sync_roster_slots_for_period`) adds missing template slots, removes obsolete template slots, updates slot metadata, and preserves assignments on unchanged slots; it is blocked for **published** shift groups. Regenerating roster slots is also blocked for **published** shift groups. Deleting a planning month and **regenerating** roster slots are destructive month-level actions. Regenerate must clear existing roster assignments in scope, require explicit confirmation in the UI, and remain exposed through guarded REST/MCP service-backed functionality.

Deleting a shift template is also destructive because it removes variants, generated roster slots, and assignments tied to those slots. Keep it behind explicit UI confirmation and guarded REST/MCP service-backed functionality.

When a schema changes in a way that makes old local data incompatible, prefer a clear forward migration and tell the developer exactly what data must be recreated instead of carrying long-term compatibility branches.

Team member month notes belong in the wishes matrix header as per-column modal actions, not as a separate full-width form below the matrix.

## Rule evaluation layer

Shared rule evaluation lives in `backend/app/services/rules/`. `build_plan_state` loads an immutable `PlanState` from a **date window** (`start_date`, `end_date`), never a `planning_period_id`, and widens **roster** loading by `max(rule.roster_lookback)` (falling back to `lookback`) in both directions. Statutory averaging rules declare a long `lookback` (the reference period) but a zero `roster_lookback`; prior months are loaded as per-member, per-day **`statutory_minutes_by_member_date`** totals, not a year of roster slots. Fairness passes an explicit **`history_start`** so the same path also fills **`duty_counts_by_member_date`** from roster `TimeEntry` rows (total / weekend-holiday / night / category) and **`period_roster_member_ids`** from the existing `PlanningPeriodShiftGroupMember` join. Rules implement `evaluate(state) -> list[ValidationWarning]` and optional `to_cpsat` (tier A encodings live next to `evaluate`; eligibility never overlays `evaluate()` per candidate). Template and variant constraints live in `app/services/rules/shift_constraints.py`. Member planning patterns that apply to the roster (`avoid_time_window`, `iso_week_cycle`, `allowed_calendar_week_parity`) live in `app/services/rules/member_patterns.py`; `recurring_weekday_status` remains wishes-cell materialization only. Built-in roster checks (`ROSTER_CONSECUTIVE_WEEKENDS` with a 7-day lookback, `ROSTER_MATRIX_DUPLICATE_DAY`, `ROSTER_TEMPLATE_NO_GO_CONFLICT`) live in `app/services/rules/builtin.py`. Statutory ArbZG/TV-Ärzte checks live in `app/services/rules/statutory.py` and resolve from the org’s **active** `WorkTimeRuleSet`. New statutory, template, pattern, and builtin checks go in this package against `PlanState`; do not add them to `constraints.py` (that module re-exports `resolve_slot_constraints` and a thin `evaluate_assignment_constraints` wrapper). `time_entries_by_member_id` and `employment_periods_by_member_id` are loaded for the roster window (employment periods widen to `history_start` when history is longer). Month validation (`validate_roster`), assignment preflight, and dashboard workload assignment counts all build `PlanState` for a date window; MCP `get_validation_warnings` calls `validate_roster`.

## Working an issue

Issue specifications live in two places:

- `docs/rollout/issues/`: the compliance, fairness, solver and swaps rollout. The plan they
  belong to is `docs/rollout/ROLLOUT.md`, and the CP-SAT spike findings are in
  `docs/rollout/solver-spike-findings.md`.
- `docs/workbench/issues/`: the desktop-first workbench and the member app. The decision they
  carry out is `docs/decisions/0001-desktop-first-workbench.md`.

Cross-cutting decisions are recorded in `docs/decisions/`. An agent implementing any of those
issues follows these rules without being reminded:

- **One issue, one branch off `main`, one pull request.** Do not start a second issue in the
  same session, and do not touch files the issue does not need.
- **The acceptance criteria are the definition of done.** Walk them one by one at the end and
  name the test that proves each. Never report a criterion as met without showing the evidence.
- **A green `pytest` does not validate a migration.** The suite runs on in-memory SQLite via
  `Base.metadata.create_all` and never executes Alembic, so a broken migration passes. Any
  change that adds one is verified separately: start Postgres, seed the pre-migration shape,
  run `alembic upgrade head`, assert the data survived, and show that run in the PR.
- **CI runs only on pull requests and on pushes to `main`** (`.github/workflows/ci.yml`).
  `container-smoke` is the only job that applies the migration chain to an empty Postgres.
  Work that is not in a PR has been checked by nothing.
- **Spike and documentation branches do not touch production code.** If a spike needs a change
  under `app/` to run at all, that is a finding to report, not a commit to make.
- **Behaviour-preserving refactors start with a golden-file snapshot** of current output, taken
  and committed before the first production line changes. Any later diff is either justified in
  the PR or is a regression.
- Before finishing: `cd backend && ruff check app && pytest`; for frontend changes also
  `cd frontend && npm run lint && npm run typecheck`, plus the frontend test commands once
  they exist (`npm run test`, `npm run test:e2e`; see **Testing Expectations**).

---

## Internationalization

Every user-visible frontend string must exist in both German and English dictionaries. Do not hardcode UI copy inside components unless it is a non-visible test fixture.

## Documentation Discipline

Keep these files current:

- `README.md`: setup, commands, tests, migrations, seed admin, MCP usage.
- `CHANGELOG.md`: brief dated record of meaningful changes.
- `PLAN.md`: current next steps and roadmap.
- `BRAINSTORM.md`: unstructured ideas.
- `AGENTS.md`: project instructions and architectural decisions.

Any implementation that changes setup, behavior, architecture, API shape, MCP capability, or roadmap must update the relevant docs in the same change.

## Testing Expectations

- Backend changes should include or update pytest coverage for services and API behavior.
- Solver and related regression tests use `python -m app.scripts.seed_solver_fixture` (`comfortable` / `tight` / `infeasible` / `arbzg`) rather than hand-built months.
- MCP changes should test resources/tools, authorization for mutations, and parity with backend services.
- Frontend logic (formatting, grid selection, keyboard handling, query hooks) gets Vitest unit tests: `cd frontend && npm run test` (watch with `npm run test:watch`). User-visible workbench flows get Playwright tests: `npm run test:e2e` against Compose after `python -m app.scripts.seed_e2e` (see README). A frontend refactor that claims to preserve behaviour starts from the Playwright golden screenshots.
- Frontend changes should keep TypeScript, linting, and i18n key coverage passing. German and English dictionaries in `frontend/lib/i18n.ts` must have the same keys (`true satisfies` parity check).
- Pull request CI merges the latest base branch before tests so combined `main` + PR is what is checked. Enable **Require branches to be up to date before merging** (or a merge queue) on `main` so GitHub cannot merge a PR whose last green run predates newer `main` commits.
- Docker startup should remain the baseline development path.

## Style

- Prefer small, explicit modules over broad abstractions.
- Keep domain services deterministic and easy for MCP tools to call.
- Use bright, fresh, accessible UI styling.

### Frontend surfaces (ADR 0001)

The frontend serves two audiences and is designed per audience, not per breakpoint. The full
reasoning is in [ADR 0001](docs/decisions/0001-desktop-first-workbench.md). Rules marked
*(target, #NNN)* describe the state the `docs/workbench/issues/` work is moving towards. Once the
named issue has landed the rule is binding. Before that, do not add new code that the issue would
have to undo (another hand-rolled matrix, dialog or `variant` switch, another hand-written API
type), and design new planner features desktop-first already.

**Planner workbench: desktop-first.** `/planning`, `/hours`, `/organization/*`, `/shift-groups`,
`/shift-types` and the admin and planner dashboard tabs.

- Design at 1440 px wide first and support down to 1024 px. Below 1024 px show a read-only view
  or a notice that links to the member area. Do not build phone layouts for planner features.
- Prefer density: compact tables, tabular numbers, several panes on screen at once.
- Detail belongs in a persistent inspector panel on the right, not in a modal. Keep modals for
  destructive confirmations and short forms. *(target, #115)*
- Period, shift group and plan status live in a context bar and in the URL (`?period=`,
  `?shiftGroup=`). Every workbench view is linkable. *(target, #115)*
- Every primary action is reachable from the keyboard and from the command palette.
  *(target, #115)*
- Matrices use the shared grid primitive: arrow-key navigation, range selection, copy and paste,
  undo and redo, virtualization. Do not add another hand-built matrix table. *(target, #117)*

**Member companion: mobile-first.** `/my-planning`, `/my-hours`, `/profile` and the member
dashboard tab.

- Design at 375 px first. Touch targets at least 44 px. One primary action per screen.
- Anything a member needs must also work in the planned native app, so member business logic
  stays in the backend and member screens consume the member API (`/api/v1/me/...`, #120)
  once it exists.
- Member and planner pages may share presentational components but never a page component or a
  `variant` switch. *(target, #114; `PlanningWorkspace` still has `variant` until then)*

**Shared pages** (`/login`, `/register`, `/onboarding`, `/pending-onboarding`, `/settings`) work
at every width.

**Frontend foundations** for all new code:

- UI primitives come from `frontend/components/ui/` (Radix-based). Do not hand-roll dialogs,
  menus, popovers, comboboxes or tooltips. Colors, spacing, radii and density come from the design
  tokens in `frontend/app/globals.css` (`bg-surface`, `text-muted`, `border-default`, `text-danger`,
  `rounded-token-*`, cell spacing via `data-density` on `<html>`). See `frontend/components/ui/README.md`.
- Server state goes through TanStack Query with the query keys in `frontend/lib/queryKeys.ts`. Do
  not add `useEffect` fetches or `*ReloadToken` counters. Planning workspace reads and the session
  query live in `frontend/lib/queries/`. Switching organization clears the cache.
- API payload types come from `frontend/lib/api/schema.d.ts`. Regenerate with
  `cd frontend && npm run api:generate` (exports `python -m app.scripts.export_openapi`, then
  `openapi-typescript`). Aliases live in `frontend/lib/api/types.ts`. `npm run api:check` fails
  when the committed schema drifts. New fetches use `apiClient` from `frontend/lib/api/client.ts`.
  Do not hand-write a type that mirrors a backend schema.
