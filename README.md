# Shift Planner

AI-first shift planning for healthcare teams, built with FastAPI, Next.js, Postgres, Docker Compose, and FastMCP.

## Current Scope
The MVP supports **organizations** as the tenancy boundary: users, **`TeamMember`** profiles, shift groups, shift templates, and planning periods belong to an `organization_id` (default org `1` via `DEFAULT_ORGANIZATION_ID` in settings). Each organization has a globally unique **`slug`** (public code, e.g. `default`) used at sign-in and for join-by-code flows. **Self-service registration** creates a new org (founding **admin**) or joins an existing org as an **applicant** until an admin approves a **join request** by creating a new `TeamMember` row or linking an existing unlinked `TeamMember`. An **admin** (`User.role` `admin`) manages team members, shift groups, templates, creates and deletes planning months, publish workflow, validation, and exports. A **planner** (`User.role` `planner`) uses the same planning UI for months that already exist: matrix, roster, publish, unpublish, regenerate roster, validation, and exports, scoped to shift groups linked in `user_shift_groups`. Planners see a **read-only team member list** (served by `/api/v1/team-members`) filtered to people who share at least one of those shift groups. The same person can be admin, planner, and linked team member in one org (capabilities on `GET /api/v1/auth/me` drive the shell). **`team_member`**-role accounts (`User.role` `team_member`, or planner/admin with a linked `TeamMember`) use `/my-planning` for wishes and no-gos, `/profile` for self-service fields, and read-only published roster for their shift groups. Two matrix surfaces: wishes (days × team members) and final roster (days × generated slots). Shift template categories are `Bereitschaftsdienst`/on-call, `Rufdienst`/stand-by, `Spätdienst`/late, and `Andere`/other.

## Quick Start
```bash
cp .env.example .env
docker compose up --build
```

Services:
- Frontend: http://localhost:3000
- Backend: http://localhost:8000
- Backend health: http://localhost:8000/health
- API docs: http://localhost:8000/docs
- MCP service: http://localhost:8001/mcp when run through Docker Compose.
- Postgres: localhost:5433 on the host, `postgres:5432` inside Docker Compose.

Docker Compose development uses bind mounts for the backend, frontend, and MCP code. The frontend runs Next.js dev mode with hot reload, and the backend runs Uvicorn with reload. The MCP container may need a restart after MCP server code changes.

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
uvicorn app.main:app --reload
pytest
```

If your machine already runs Postgres on port `5432`, keep `POSTGRES_HOST_PORT=5433` in `.env`. The backend and MCP containers still use `postgres:5432` internally.

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

Wishes matrix day statuses (each blocks any roster assignment on that day for the team member): `urlaub`, `forschung`, `lehre`, `frei`.

`GET /api/v1/matrix/{id}` always returns `shift_templates`, `template_slot_days`, and `shift_intents` for wish/no-go editing: **with** `shift_group_id`, they are limited to that group; **without** it (admin full-org view), templates are every template linked to any shift group, each `template_slot_days` row includes `shift_group_id`, and intents list all rows for team members in the matrix. Use `PUT /api/v1/matrix/{id}/shift-intents/bulk` with `{ "intents": [ { "team_member_id", "cell_date", "shift_group_id", "shift_template_id", "kind": "wish" | "no_go" | null } ] }` — `kind` null removes that intent row.

Team member month notes store source emails and summaries so future LLM parsing can propose matrix updates. In the wishes matrix, each team member column header has a notes button that opens that person's month-specific source text and summary.

Shift templates are configured under Shift Types. A template has one or more variants that define applicability (`weekday`, `weekend`, `holiday`, or `any`), start/end times, overnight offsets, and required count. Holidays use the North Rhine-Westphalia German holiday calendar and behave like weekend rules unless explicit holiday variants exist.

The final roster matrix has one row per day and shows only the concrete shift slots generated for that date. Each roster cell assigns a team member to that date/slot, and changes autosave. The team member picker shows a color dot for that person’s day-level wishes status and labels for wish/no-go on the slot’s template. Day-level unavailable statuses and template no-gos (unless Manual override is checked on the cell) are highlighted as conflicts.

The frontend no longer has standalone `/requests`, `/roster`, `/validation`, or `/exports/print` pages. Validation remains available through the backend API and MCP, and `/planning` uses it for inline conflict summaries.

The `/planning` toolbar includes destructive month actions behind confirmation dialogs: deleting a planning month removes its wishes, notes, generated roster slots, and assignments; regenerating a month clears roster assignments and rebuilds roster slots from the current shift templates. Publish is a separate confirmed action that marks the month published and unlocks roster reads for team members (per selected shift group). Unpublish reverts that month to draft and immediately blocks team member roster reads again.

Relevant CSV exports:
- Wishes matrix: `/api/v1/exports/matrix/{planning_period_id}.csv`
- Final roster matrix: `/api/v1/exports/roster-matrix/{planning_period_id}.csv`

Query parameter `shift_group_id`: **admins** may omit it for a full-org matrix, matrix notes, roster, validation, and CSV exports. **Planners** (non-admin) must pass `shift_group_id` on `GET /api/v1/matrix/{id}`, matrix note routes under `/api/v1/matrix/{id}/notes`, `GET /api/v1/roster-matrix/{id}`, `GET /api/v1/validation/{id}`, and on both CSV export routes; the value must be one of their `user_shift_groups`. Creating or deleting a planning month (`POST` / `DELETE /api/v1/planning-periods`) is **admin-only**; publish, unpublish, and regenerate roster remain available to any user with planning access (admin or planner).

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

## Users and roles
- `User.role` is `admin` (full admin API and UI), `planner` (planning UI and scoped reads; no team-member/template/shift-group mutations), `team_member` (wishes and self-profile; published roster only for their shift groups), or **`applicant`** (signed up to join an org; no planning or team portal until an admin approves the join request). `TeamMember.user_id` links a team member profile to a user; only admins assign or clear that link when creating or editing a `TeamMember` (or via join-request approval). Linking a user to a `TeamMember` checks org **seat limits** when `organizations.seat_limit` is set.
- **Sign-in:** `POST /api/v1/auth/login` requires `email` and **`password`**. **`organization_slug`** is optional when the email maps to a **single** active **membership** (`User` row); otherwise include it. **`409`** with JSON body **`{ "code": "organization_slug_required", "organizations": [{ "slug", "name", "organization_id" }, ...] }`** when the same account has more than one org. **`POST /api/v1/auth/me/active-organization`** (session) with **`{ "organization_slug" }`** switches the cookie to another membership of the same account. **`POST /api/v1/auth/me/add-organization-membership`** (session) with **`{ "organization_slug", "password", "first_name", "last_name", "message?" }`** re-verifies the password, creates an **`applicant`** membership in the target org plus a pending join request (when allowed), and sets the session to that new membership. **`GET /api/v1/auth/me`** includes **`memberships`** for the org switcher and **Settings** (`/settings`). **`POST /api/v1/auth/me/join-request`** (session, **`applicant`** only) creates a new pending join request when none is pending.
- **Delete account:** `POST /api/v1/auth/delete-account` with JSON `{ "password" }` removes the signed-in user after password check; clears the session cookie. The **last admin** in an organization cannot delete themselves (add another admin first). `TeamMember.user_id` is set to null when a linked user is deleted; planner `user_shift_groups` rows cascade.
- **Registration:** `POST /api/v1/auth/register/create-organization` (founding admin + new org) and **`POST /api/v1/auth/register/join-organization`** (applicant + pending join request) require **`password`** and **`password_confirm`** (must match). Public **`GET /api/v1/organizations/lookup?slug=`** resolves a slug to the org display name before join.
- **Join requests (admin):** `GET /api/v1/organization/join-requests`, `POST .../approve-create-team-member`, `POST .../approve-link-team-member`, `POST .../reject`, and **`POST /api/v1/organization/join-requests/{id}/cancel`** for the requester. **`GET /api/v1/auth/me/join-request`** returns the caller’s pending request, if any. Admin **remove user** deletes the **`User`** account (that login no longer exists; the person must use **Join organization** again). **Unlink login** on the staff directory only removes **`TeamMember.user_id`**; the user can still sign in. Org settings: **`GET|PATCH /api/v1/organization`** (admin). **`GET /api/v1/organization/users`** lists all users in the org with **user id**, email, role, **`is_active`**, and linked team member profile (for re-linking after clearing `TeamMember.user_id` in the team member editor). **`GET /api/v1/organization/staff-directory`** returns one row per normalized email, merging `TeamMember` and login data with **`link_status`**. Admin UI groups **team** work under **`/organization/team`** (staff directory with row detail for profiles and access; **`/organization/team/members`** redirects to the same page; join requests tab) and **shifts** under **`/organization/shifts`** (tabs for shift groups and types). Staff directory actions include **unlink** team-member login, **`DELETE /api/v1/organization/users/{id}`** to remove an account (guards for self and sole admin), and **`PATCH /api/v1/organization/users/{id}`** with `{ "role" }` to promote or demote among **`admin`**, **`planner`**, and **`team_member`** (cannot demote the sole admin). Legacy **`/organization`**, **`/organization/users`**, **`/shift-groups`**, and **`/shift-types`** redirect into those sections.
- `GET /api/v1/auth/me` (and login/register responses) returns `organization_id`, nested `organization` (`id`, `name`, **`slug`**, `plan_tier`), `team_member_id`, `shift_groups`, `planner_shift_groups`, and `capabilities` (`admin`, `planning`, `team_member_portal`) for the **active membership** only so the frontend can show Dashboard, Planning, My planning, Profile, admin team/shift sections, and the current organization in the shell and settings. After switching org, navigation is aligned with those capabilities (same default routes as after login).
- `GET|PATCH /api/v1/auth/me/team-member` applies when the session has a linked `TeamMember` (any allowed role for that link).
- `POST /api/v1/planning-periods/{id}/publish` sets `status` to `published` and `published_at`; `POST /api/v1/planning-periods/{id}/unpublish` reverts to `draft` and clears `published_at`.
- `GET /api/v1/roster-matrix/{id}`: users with planning access (`admin` / `planner`) use **draft** roster data unless the query includes `team_member_portal=true` (the my-planning UI sends this for read-only roster). With `team_member_portal=true`, a **linked** team member session requires `shift_group_id`, group membership, and a **published** month (`403` while draft). Pure `team_member` users always follow that published read path.
- Seed team-member logins: set `TEAM_MEMBER_SEED_PASSWORD` in `.env`, then run `python -m app.scripts.seed_team_member_users` (Docker Compose runs it after migrations). It creates a `team_member`-role user per active unlinked `TeamMember` email with the same `organization_id` as that row (or `DEFAULT_ORGANIZATION_ID` if missing) and links `TeamMember.user_id`. Skip when the email is already a user.
- Optional planner demo: set `PLANNER_SEED_EMAIL` and `PLANNER_SEED_PASSWORD` in `.env`. Docker Compose passes these into the **backend** container so `seed_planner_user` hashes the same password you use in the browser. Run `docker compose exec backend python -m app.scripts.seed_planner_user` (or add it to the backend command); re-running updates an existing planner’s password and shift-group links. Default email is `planner@example.com` when `PLANNER_SEED_EMAIL` is unset or empty.

## Documentation Rule
When behavior, setup, architecture, API shape, MCP capabilities, or roadmap changes, update `README.md`, `AGENTS.md`, `CHANGELOG.md`, `PLAN.md`, or `BRAINSTORM.md` as appropriate.
