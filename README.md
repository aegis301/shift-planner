# Shift Planner

AI-first shift planning for healthcare teams, built with FastAPI, Next.js, Postgres, Docker Compose, and FastMCP.

## Current Scope

The MVP supports **organizations** as the tenancy boundary: users, **`TeamMember`** profiles, shift groups, shift templates, and planning periods belong to an `organization_id` (default org `1` via `DEFAULT_ORGANIZATION_ID` in settings). Each organization has a globally unique **`slug`** (public code, e.g. `default`) used for join-by-code flows, **`POST /api/v1/auth/me/active-organization`**, and similar—**not** on the public **`/login`** form. **Self-service registration** begins with an **`Account`** and **`/onboarding`** (or legacy one-shot register endpoints): create a new org (founding **admin**) or join an existing org as an **applicant** until an admin approves a **join request** by creating a new `TeamMember` row or linking an existing unlinked `TeamMember`. An **admin** (`User.role` `admin`) manages team members, shift groups, templates, creates and deletes planning months, publish workflow, validation, and exports. A **planner** (`User.role` `planner`) uses the same planning UI for months that already exist: matrix, roster, publish, unpublish, regenerate roster, validation, and exports, scoped to shift groups linked in `user_shift_groups`. Planners see a **read-only team member list** (served by `/api/v1/team-members`) filtered to people who share at least one of those shift groups. The same person can be admin, planner, and linked team member in one org (capabilities on `GET /api/v1/auth/me` drive the shell). **`team_member`**-role accounts (`User.role` `team_member`, or planner/admin with a linked `TeamMember`) use `/my-planning` for wishes and no-gos, `/profile` for self-service fields, and read-only published roster for their shift groups. Two matrix surfaces: wishes (days × team members) and final roster (days × generated slots). Shift template categories are `Bereitschaftsdienst`/on-call, `Rufdienst`/stand-by, `Spätdienst`/late, and `Andere`/other.

## Quick Start

```bash
cp .env.example .env
docker compose up --build
```

Services (host ports default to uncommon values to reduce clashes with other local apps; override via `.env`):

- Frontend: <http://localhost:18130> (`FRONTEND_HOST_PORT`) — role-based **Dashboard** at `/` (admin / planner / team member tabs with charts)
- Backend: <http://localhost:18180> (`BACKEND_HOST_PORT`)
- Backend health: <http://localhost:18180/health>
- API docs: <http://localhost:18180/docs>
- MCP service: <http://localhost:18181/mcp> (`MCP_HOST_PORT`) when run through Docker Compose.
- Postgres: localhost:5433 on the host (`POSTGRES_HOST_PORT`), `postgres:5432` inside Docker Compose.

If you change `FRONTEND_HOST_PORT` or `BACKEND_HOST_PORT`, update `BACKEND_CORS_ORIGINS` and `NEXT_PUBLIC_API_BASE_URL` in `.env` to match.

Docker Compose development uses bind mounts for the backend, frontend, and MCP code. The frontend runs Next.js dev mode with hot reload, and the backend runs Uvicorn with reload. The MCP container may need a restart after MCP server code changes.

## Cloudflare Tunnel for local dev

To reach the dev stack from outside your machine (without publishing host ports on the LAN), run a named tunnel after `docker compose up`. Configure the `dev-tunnel` ingress in your Cloudflare / `cloudflared` config to forward to local services (typically the frontend at `http://localhost:18130`; add a second ingress for the backend at `http://localhost:18180` if the browser calls the API on a separate hostname).

```bash
cloudflared tunnel --protocol http2 run dev-tunnel
```

If the public hostname differs from `localhost`, set `BACKEND_CORS_ORIGINS` and `NEXT_PUBLIC_API_BASE_URL` in `.env` to your tunnel URL(s) so the browser can call the API and receive session cookies.

## Production deployment

Use `docker compose -f docker-compose.prod.yml --env-file .env up -d --build` with a production `.env` (see [.env.example](.env.example)). Details: Caddy routing, Cloudflare, GitHub Actions CI/CD, backups, and required secrets are documented in [deploy/README.md](deploy/README.md). Continuous integration runs in [.github/workflows/ci.yml](.github/workflows/ci.yml); optional server deploy runs from [.github/workflows/deploy.yml](.github/workflows/deploy.yml) on `workflow_dispatch` or `v*` tags.

## Backend Development

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
python -m app.scripts.seed_admin
python -m app.scripts.seed_team_member_users
python -m app.scripts.seed_planner_user
uvicorn app.main:app --reload --port 18180
ruff check app
pytest
```

Backend lint rules live in [backend/pyproject.toml](backend/pyproject.toml) (`[tool.ruff.lint]`): pycodestyle errors, pyflakes, isort, pyupgrade, bugbear, flake8-simplify, perflint, and Ruff-specific checks. FastAPI dependency markers (`Depends`, `Query`, `Body`, …) are registered as immutable calls so `B008` does not fire on route signatures. Run `ruff check app --fix` before pushing; CI runs `ruff check app`.

If your machine already runs Postgres on port `5432`, keep `POSTGRES_HOST_PORT=5433` in `.env`. The backend and MCP containers still use `postgres:5432` internally. Containers still listen on `8000` / `3000` / `8001` internally; only the published host ports use `18180` / `18130` / `18181` by default.

## Frontend Development

```bash
cd frontend
npm install
npm run dev
npm run lint
npm run typecheck
```

The App Router root layout wraps the app in one **`LocaleShell`** (see `app/ClientRoot.tsx`) so locale and `/api/v1/auth/me` session state are not reset on every navigation. Individual pages do not nest another `LocaleShell`.

## MCP Development

```bash
cd mcp-server
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
PYTHONPATH=../backend python -m mcp_app.server
pytest
```

Mutating MCP tools require `MCP_ADMIN_TOKEN`. Read resources are local-first and share backend service behavior. Local CLI runs use FastMCP stdio by default; Docker Compose sets `MCP_TRANSPORT=http`. MCP reads and mutations use **`MCP_ORGANIZATION_ID`** when set, otherwise **`DEFAULT_ORGANIZATION_ID`** (default `1`), so tools target a single configured org (not the signed-in web user’s org).

## Planning Workflow

Use `/planning` for the planner workflow and `/my-planning` for linked team members. One selected planning month controls wishes, final roster assignment, inline validation, CSV exports, and workload stats. The planner page supports both a full stacked view and a tabbed view for Wishes, Roster, and Analysis.

Wishes matrix **day statuses** are configured per organization (`GET|POST|PATCH|DELETE /api/v1/planning-day-status-definitions`; admin UI **Team** → **Tagesstatus**). Each status has a stable `code`, DE/EN labels, a color preset, and `blocks_roster_assignment` (when true, roster assignment on that day is blocked). New orgs start with `urlaub`, `forschung`, `lehre`, and `frei`.

`GET /api/v1/matrix/{id}` always returns `shift_templates`, `template_slot_days`, and `shift_intents` for wish/no-go editing: **with** `shift_group_id`, they are limited to that group; **without** it (admin full-org view), templates are every template linked to any shift group, each `template_slot_days` row includes `shift_group_id`, and intents list all rows for team members in the matrix. Use `PUT /api/v1/matrix/{id}/shift-intents/bulk` with `{ "intents": [ { "team_member_id", "cell_date", "shift_group_id", "shift_template_id", "kind": "wish" | "no_go" | null } ] }` — `kind` null removes that intent row.

Team member month notes now store only month-specific summaries. Permanent preference text is stored on `team_members.planning_preferences` and reused in `/profile` and the matrix note modal.

Shift templates are configured under Shift Types. A template has one or more variants that define applicability (`weekday`, `weekend`, `holiday`, or `any`), start/end times, overnight offsets, and required count. Holidays use the North Rhine-Westphalia German holiday calendar and behave like weekend rules unless explicit holiday variants exist.

Templates and variants can each define constraints with per-rule **`severity`**: `info`, `warning`, or `error` (`error` blocks roster assignment; the others do not). Requests may still send legacy **`enforcement`** (`warning` / `block`); it is normalized to severity. Current rule types:

- `no_additional_same_day`
- `min_rest_hours` (requires `min_rest_hours`)
- `unavailable_overlap_policy` (`unavailable_overlap_mode`: `allow`, `warn`, `block`; overrides global wishes-matrix overlap blocking for this template/variant; legacy `no_cross_day_into_unavailable_day` maps to the same policy)
- `max_assignments_per_month` (requires `max_assignments_per_month`, counts same-template assignments in the selected month)
- `requires_coupled_shift` (requires `paired_shift_variant_id`, optional `partner_day_offset` default `1`, range `-7`..`7`; same person must also be assigned to the partner variant on the offset calendar day **inside the same planning month**; outside the month the rule is skipped)
- `team_member_property_requirement` (requires JSON **`property_requirement`**: nested **`all`** / **`any`** / **`atom`** nodes; atoms reference **`team_member_property_definitions`** with typed operators such as `gte` on numbers or `one_of` on select; missing values fail the expression; validation code **`ROSTER_CONSTRAINT_TEAM_MEMBER_PROPERTIES`**; you may add **multiple** such rules per template or variant)

These constraints are evaluated for assignment preflight and validation warnings through a shared backend rule engine. **Global rule:** roster assignments are blocked when the shift overlaps any wishes-matrix day whose status has `blocks_roster_assignment` (`ROSTER_MATRIX_UNAVAILABLE_OVERLAP`), unless a template/variant sets `unavailable_overlap_policy` to `allow` or `warn`.

Team members may also define recurring **planning patterns** on their profile or via `GET/PUT /api/v1/team-members/{id}/planning-patterns`: `avoid_time_window` (always non-blocking info hints on roster; **stack several weekday+time bands** in `windows[]`), **`iso_week_cycle`** (anchored multi-week on/off cycle with `cycle_weeks`, `on_weeks`, `anchor_iso_year`, `anchor_iso_week`, optional `wishes_weekdays`, `allow_weekend_roster`, and `off_status` for wishes on off weeks/days), legacy `allowed_calendar_week_parity` (even/odd ISO weeks), and `recurring_weekday_status` (weekdays plus a wishes day status). Recurring weekday and cycle wishes materialization is merged by pattern **`display_order`** (later patterns override earlier ones on the same day). New planning months pick up these rules when the month is created. Organization admins choose whether `iso_week_cycle` and calendar-week parity may use blocking `error` via `GET/PATCH /api/v1/organization/member-pattern-policy` (time windows cannot be hard errors).

**Team member properties (competencies):** Admins define custom fields per organization at `GET|POST|PATCH|DELETE /api/v1/team-member-property-definitions` (types: `number`, `date`, `select`, `multi_select`, `text`; options required for select types). Values are stored per team member at `GET|PUT /api/v1/team-members/{id}/property-values`. The org-wide editable matrix is `GET /api/v1/team-member-property-values/matrix` (admin). Each definition may set `editable_by_team_member` so linked members can maintain their own values on `/profile` while admins edit all fields in Organization → Team → Properties (table) and in the staff directory member editor.

**Team member nickname:** Optional `team_members.nickname` is editable on `/profile` (`PATCH /api/v1/auth/me/team-member`) and by admins on `TeamMember` CRUD. Wishes matrix, final roster, planning validation/workload, and roster exports show **nickname** when set, otherwise **last name** (compact column headers). Staff directory and admin lists still use full first + last name.

Validation also emits **`ROSTER_CONSECUTIVE_WEEKENDS`** (warning) when a team member is assigned on two consecutive calendar weekends (Saturday–Sunday pairs anchored by each weekend’s Saturday).

The final roster matrix has one row per day and shows only the concrete shift slots generated for that date. Each roster cell assigns a team member to that date/slot, and changes autosave. The team member picker shows a color dot for that person’s day-level wishes status and labels for wish/no-go on the slot’s template. Day-level unavailable statuses, template no-gos (unless Manual override is checked on the cell), and template/variant constraints are highlighted as conflicts.

The frontend no longer has standalone `/requests`, `/roster`, `/validation`, or `/exports/print` pages. Validation remains available through the backend API and MCP, and `/planning` uses it for inline conflict summaries.

The `/planning` toolbar includes destructive month actions behind confirmation dialogs: deleting a planning month removes its wishes, notes, generated roster slots, and assignments; regenerating a month clears roster assignments and rebuilds roster slots from the current shift templates. Planning months use a **per-shift-group** 3-state lifecycle: `draft`, `preliminary`, `published` (stored in `planning_period_shift_group_statuses`). Publishing one Dienstgruppe does not change another group's status. Wishes day cells and month notes are also scoped by `shift_group_id`. Team members can read roster data for a group in `preliminary` and `published`; wishes and feedback are writable for that group while it is `draft` or `preliminary`. **Published** plans are read-only for planners and admins; reopen to `preliminary` to edit (working version bumps, e.g. `1.0` → `1.1`). **Plan versions** snapshot roster + wishes per shift group (`0.1` on first preliminary share, `1.0` on first publish); use **Save version** while preliminary or browse **Versions** history.

Relevant CSV exports (planning users):

- Wishes matrix: `/api/v1/exports/matrix/{planning_period_id}.csv`
- Final roster matrix: `/api/v1/exports/roster-matrix/{planning_period_id}.csv`

Published roster file exports (planning users and linked team-member portal users):

- Final roster Excel: `/api/v1/exports/roster-matrix/{planning_period_id}.xlsx`
- Final roster PDF: `/api/v1/exports/roster-matrix/{planning_period_id}.pdf`

Personal iCalendar exports (linked team-member portal users only; same preliminary/published visibility as roster reads):

- Single assigned shift: `/api/v1/exports/roster-slots/{roster_slot_id}.ics`
- All visible assigned shifts (shift group scope): `/api/v1/exports/my-shifts.ics?shift_group_id=…`
- Visible assigned shifts in a date range: same endpoint with optional `start_date` and `end_date` query params (ISO dates, both required together)
- Assigned shifts in one planning month: `/api/v1/exports/my-shifts/{planning_period_id}.ics?shift_group_id=…`

Query parameter `shift_group_id`: **admins** may omit it for a full-org matrix, matrix notes, roster, validation, and CSV exports. **Planners** (non-admin) must pass `shift_group_id` on `GET /api/v1/matrix/{id}`, matrix note routes under `/api/v1/matrix/{id}/notes`, `GET /api/v1/roster-matrix/{id}`, `GET /api/v1/validation/{id}`, and on both CSV export routes; the value must be one of their `user_shift_groups`. For roster XLSX/PDF exports, planners follow the same shift-group scope rules, while team-member portal users must pass `shift_group_id` and are checked against team-member shift-group membership. Creating or deleting a planning month (`POST` / `DELETE /api/v1/planning-periods`) is **admin-only**; status transitions, `POST /api/v1/planning-periods/{id}/sync-roster` (add/remove/update template slots while preserving assignments on unchanged slots), and destructive `POST /api/v1/planning-periods/{id}/regenerate-roster` remain available to any user with planning access (admin or planner).

Shift groups are managed at `GET|POST|PATCH|DELETE /api/v1/shift-groups` (`GET` for any planning user, scoped for planners; create/update/delete and membership `PUT`s are admin-only). `TeamMember` rows carry `shift_group_ids`; roster assignments require the assignee to share a group with the slot’s template when that template belongs to at least one group.

The old request/roster form APIs and simple shift-type API have been removed. Current workflow code should target `/api/v1/matrix`, `/api/v1/roster-matrix`, `/api/v1/shift-templates`, and `/api/v1/shift-groups`.

## Migrations

Create a migration after changing backend models:

```bash
cd backend
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

Current cleanup note: migration `202604290001` removes the old simple shift type, availability request, direct roster assignment tables, and incompatible roster slots from existing databases. If you still need data from those tables in a local database, manually recreate it as shift templates, matrix cells, or generated roster assignments before running `alembic upgrade head`.

Migration `202604300001` adds `shift_groups`, `doctor_shift_groups`, and `shift_group_shift_templates`.

Migration `202604300002` adds `planning_shift_intents` and maps legacy `planning_cells.status` values outside Urlaub/Forschung/Lehre/Frei to `frei`.

Migration `202604300003` adds optional `doctors.user_id` (unique, links a doctor login) and `planning_periods.published_at`.

Migration `202604300004` splits doctor display names into `first_name` and `last_name`.

Migration `202605010001` adds `organizations` (with `plan_tier`, optional `seat_limit`, and subscription-related columns for future billing), `user_shift_groups`, `organization_id` on core tenant tables, composite uniqueness per org (for example shift group code, template code, doctor email, planning year/month), and `User.role` value `planner`.

Migration `202605020001` adds **`organizations.slug`**, **`organization_join_requests`**, switches `users.email` uniqueness to **per organization** (`organization_id`, `email`), and backfills `slug` for existing organizations.

Migration `202605050001` renames **`doctors`** → **`team_members`**, related join tables and FK columns (**`team_member_id`**), period notes, join-request resolution column, and sets `users.role` from **`doctor`** to **`team_member`** where applicable.

Migration `202606080002` adds JSON `constraints` columns on `shift_templates` and `shift_variants`.

## Users and roles

- `User.role` is `admin` (full admin API and UI), `planner` (planning UI and scoped reads; no team-member/template/shift-group mutations), `team_member` (wishes and self-profile; roster reads in `preliminary` and `published` for their shift groups, feedback comments writable only in `preliminary`), or **`applicant`** (signed up to join an org; no planning or team portal until an admin approves the join request). `TeamMember.user_id` links a team member profile to a user; only admins assign or clear that link when creating or editing a `TeamMember` (or via join-request approval). Linking a user to a `TeamMember` checks org **seat limits** when `organizations.seat_limit` is set.
- **Sign-in:** `POST /api/v1/auth/login` sends **`email`** and **`password`** only (no **`organization_slug`** on the login request). **`shift_planner_session`** carries either **`User.id`** (version **`typ`** **`user`**) or, when there are **no memberships**, **`Account.id`** (**`typ`** **`account`**). Responses are **`AccountSessionRead`** (**`auth_kind`** **`account`**) or **`UserRead`** (**`auth_kind`** **`user`**). **`0`** memberships → account cookie + **`AccountSessionRead`**; **`1`** → user cookie + **`UserRead`**; **`N`** → user cookie bound to **one deterministic** membership (**`organization.slug`** ascending, then **`users.id`** ascending) + **`UserRead`**. Endpoints depending on **`get_current_user`** return **`403`** with **`{"code":"account_session_incomplete"}`** for an account cookie; **`GET /api/v1/auth/me`** accepts both. **`POST /api/v1/auth/me/active-organization`** (membership cookie + **`organization_slug`**) rotates **`User.id`**. **`POST /api/v1/auth/me/add-organization-membership`** (membership cookie) with **`organization_slug`, `password`, names, optional `message`** adds applicant membership + pending request and rotates session. **`GET /api/v1/auth/me`** matches login body shapes (**`memberships`** and org fields appear on **`user`**). **`POST /api/v1/auth/me/join-request`** applies to **`applicant`** with user session when no pending request.
- **Create own organization anytime:** Any signed-in membership can create a brand-new organization and become admin there via **`POST /api/v1/auth/me/create-organization-membership`** with **`organization_name`** and **`organization_slug`**. The session switches to the new admin membership on success.
- **Delete account:** **`POST /api/v1/auth/delete-account`** with **`password`** works when the cookie is membership or account-only; clears cookie. Sole-admin blocking applies as before.
- **Password recovery:** No email reset. Admins set a new password for another user in the org via **`POST /api/v1/organization/users/{id}/reset-password`** (staff directory UI). Users change their own password when signed in via **`POST /api/v1/auth/me/change-password`**. Passwords are per **`Account`** (global email login).
- **Registration:** **`POST /api/v1/auth/register`** with **`email`, `password`, `password_confirm`, `locale`** creates **`Account`** only (**`password_confirm`** must equal **`password`**) and sets an account cookie. **`POST /api/v1/auth/me/onboarding/create-organization`** (account cookie): new org plus admin **`User`**, cookie becomes membership. **`POST /api/v1/auth/me/onboarding/join-organization`** (account cookie): applicant **`User`** plus pending request, cookie becomes membership. **`POST /api/v1/auth/register/create-organization`** / **`POST /api/v1/auth/register/join-organization`** keep one-shot behavior. Frontend: **`/register`**, **`/onboarding`** ( **`/register/create`** and **`/register/join`** redirect); **`GET /api/v1/organizations/lookup?slug=`** for join lookups.
- **Join requests (admin):** `GET /api/v1/organization/join-requests`, `POST .../approve-create-team-member`, `POST .../approve-link-team-member`, `POST .../reject`, and **`POST /api/v1/organization/join-requests/{id}/cancel`** for the requester. **`GET /api/v1/auth/me/join-request`** returns the caller’s pending request, if any. **Membership invites (admin-initiated, existing accounts only):** **`GET|POST /api/v1/organization/invites`**, **`DELETE /api/v1/organization/invites/{id}`** (revoke pending; revoking also removes an **unlinked** pre-created **`TeamMember`** from **`prepare_team_member_profile`**). Default **`role`** is **`team_member`** with **email only**; **`prepare_team_member_profile`** optionally creates that unlinked profile first (names + **`shift_group_ids`**), linked on accept. **`planner`** invites still require **`planner_shift_group_ids`**. Invitees: **`GET /api/v1/auth/me/organization-invites`** (includes **`needs_profile_on_accept`**, **`accept_shift_groups`** when the invitee must supply a profile at accept time), **`POST .../organization-invites/{id}/accept`** with optional JSON **`{ first_name, last_name, shift_group_ids, employment_percentage?, notes? }`** for minimal **`team_member`** invites, **`POST .../decline`**. **Delete organization (admin):** **`DELETE /api/v1/organization`** with body **`{ "confirm_organization_name" }`** matching the org **`name`** exactly; refused when the org id equals **`DEFAULT_ORGANIZATION_ID`**. Admin **remove user** deletes the **`User`** account (that login no longer exists; the person must use **Join organization** again). **Unlink login** on the staff directory only removes **`TeamMember.user_id`**; the user can still sign in. Org settings: **`GET|PATCH /api/v1/organization`** (admin). **`GET /api/v1/organization/users`** lists all users in the org with **user id**, email, role, **`is_active`**, and linked team member profile (for re-linking after clearing `TeamMember.user_id` in the team member editor). **`GET /api/v1/organization/staff-directory`** returns one row per normalized email, merging `TeamMember` and login data with **`link_status`**. Admin UI groups **team** work under **`/organization/team`** (staff directory with row detail for profiles and access; **`/organization/team/members`** redirects to the same page; **join requests** and **Organization** tabs for invites + destructive delete) and **shifts** under **`/organization/shifts`** (tabs for shift groups and types). Staff directory actions include **unlink** team-member login, **`DELETE /api/v1/organization/users/{id}`** to remove an account (guards for self and sole admin), and **`PATCH /api/v1/organization/users/{id}`** with `{ "role" }` to promote or demote among **`admin`**, **`planner`**, and **`team_member`** (cannot demote the sole admin). Legacy **`/organization`**, **`/organization/users`**, **`/shift-groups`**, and **`/shift-types`** redirect into those sections.
- `GET|PATCH /api/v1/auth/me/team-member` applies when the session has a linked `TeamMember` (any allowed role for that link).
- Planning status endpoints (require `shift_group_id` query param): `POST /api/v1/planning-periods/{id}/draft`, `POST /api/v1/planning-periods/{id}/preliminary`, `POST /api/v1/planning-periods/{id}/publish` (optional JSON body: `major_version`, `minor_version`, `note`, `is_major_update` on preliminary reopen). Legacy `POST /api/v1/planning-periods/{id}/unpublish` maps to `preliminary`. Plan versions: `GET /api/v1/planning-periods/{id}/versions?shift_group_id=`, `POST /api/v1/planning-periods/{id}/versions?shift_group_id=`, `GET .../versions/{version_id}`, `GET .../versions/{version_id}/matrix`, `GET .../versions/{version_id}/roster-matrix`, `GET .../versions/{version_id}/export/{matrix.csv|roster-matrix.csv|roster-matrix.xlsx|roster-matrix.pdf}`. `GET /api/v1/planning-periods` includes `shift_group_statuses[]` per month (with `working_major_version` / `working_minor_version`).
- `GET /api/v1/roster-matrix/{id}`: users with planning access (`admin` / `planner`) use planning scope as before unless the query includes `team_member_portal=true` (the my-planning UI sends this for read-only roster). With `team_member_portal=true`, a **linked** team member session requires `shift_group_id`, group membership, and a month in `preliminary` or `published` (`403` while `draft`). Pure `team_member` users always follow that team-member read path.
- `GET /api/v1/exports/roster-matrix/{id}.xlsx` and `GET /api/v1/exports/roster-matrix/{id}.pdf` are roster exports for team-member portal visibility states (`preliminary` and `published`). They use the same planning/team-member portal access split and shift-group scope rules as roster reads; team-member portal callers should pass `team_member_portal=true`.
- Seed team-member logins: set `TEAM_MEMBER_SEED_PASSWORD` in `.env`, then run `python -m app.scripts.seed_team_member_users` (Docker Compose runs it after migrations). It creates a `team_member`-role user per active unlinked `TeamMember` email with the same `organization_id` as that row (or `DEFAULT_ORGANIZATION_ID` if missing) and links `TeamMember.user_id`. Skip when the email is already a user.
- Optional planner demo: set `PLANNER_SEED_EMAIL` and `PLANNER_SEED_PASSWORD` in `.env`. Docker Compose passes these into the **backend** container so `seed_planner_user` hashes the same password you use in the browser. Run `docker compose exec backend python -m app.scripts.seed_planner_user` (or add it to the backend command); re-running updates an existing planner’s password and shift-group links. Default email is `planner@example.com` when `PLANNER_SEED_EMAIL` is unset or empty.

## Documentation Rule

When behavior, setup, architecture, API shape, MCP capabilities, or roadmap changes, update `README.md`, `AGENTS.md`, `CHANGELOG.md`, `PLAN.md`, or `BRAINSTORM.md` as appropriate.
