# Changelog

## 2026-06-02
- **`GET /api/v1/auth/me`:** Admins receive **`organization_shift_groups`** (all shift groups in the active organization, including inactive) so admin UIs such as **Organization → Invites** can list groups without coupling to other parallel API calls.
- **Organization invites (refine):** **`team_member`** invites default to **email-only**; profile fields are supplied at **accept** or optionally when **`prepare_team_member_profile`** is true (creates an unlinked **`TeamMember`** stored on **`precreated_team_member_id`**, linked on accept). **`POST /api/v1/auth/me/organization-invites/{id}/accept`** accepts an optional JSON body. Pending list includes **`needs_profile_on_accept`**, **`has_precreated_team_member`**, and **`accept_shift_groups`**. Alembic **`202606020001`** adds **`precreated_team_member_id`**.

## 2026-06-01
- **Organization membership invites:** Admins invite an **existing account email** (`planner` or `team_member`) via **`POST /api/v1/organization/invites`**; **`GET /api/v1/organization/invites`** lists outbound invites; **`DELETE /api/v1/organization/invites/{id}`** revokes pending invites. Invitees use **`GET /api/v1/auth/me/organization-invites`**, **`POST .../accept`** (session switches to the new membership), and **`POST .../decline`**. Alembic **`202606010001`** adds **`organization_membership_invites`**. Frontend: **Organization** tab under **`/organization/team/organization`**; **Settings** shows pending invites when present.
- **Delete organization:** **`DELETE /api/v1/organization`** with JSON **`{ "confirm_organization_name" }`** must match the organization’s current **`name`** exactly; blocked for **`DEFAULT_ORGANIZATION_ID`**. Destructive teardown reuses existing delete helpers for planning periods, shift templates/groups, team members, join requests, invites, users, then the **`organizations`** row.

## 2026-05-04
- **Alembic `202605040001`:** Drops per-org email uniqueness the same way **`202605020001`** created it (unique index **`ix_users_org_email`**), with fallbacks for a legacy constraint name, so Postgres upgrades no longer fail on missing **`uq_users_organization_email`**. Downgrade recreates **`ix_users_org_email`** to match **`202605020001`**.
- **Team member domain (full stack):** SQLAlchemy **`TeamMember`** (table **`team_members`**) replaces the old doctor entity; REST **`/api/v1/team-members`**, profile **`GET|PATCH /api/v1/auth/me/team-member`**, join approvals **`approve-create-team-member`** / **`approve-link-team-member`**, roster query **`team_member_portal`**, and user role **`team_member`**. Alembic **`202605050001`** renames tables/columns and migrates `users.role`. Staff directory API uses **`team_member_label`** / **`team_member_is_active`** / **`team_member_only`**. Frontend matrix and roster payloads use **`team_members`**; i18n keys **`orgStaffDetailLoadingTeamMember`** / **`orgStaffDetailTeamMemberMissing`**. Seed env **`TEAM_MEMBER_SEED_PASSWORD`** and **`python -m app.scripts.seed_team_member_users`**.

## 2026-05-03
- **Multi-organization accounts:** New **`accounts`** table (global email + password); **`users`** rows are **memberships** (`account_id`, `organization_id`, role, …). Alembic **`202605040001`**. Session still stores **`User.id`** (active membership). **`GET /api/v1/auth/me`** adds **`memberships`**; **`POST /api/v1/auth/me/active-organization`** switches org by slug. Login **`409`** returns structured **`organizations`** when the account has multiple memberships. Admin **remove user** deletes one membership (and the **`Account`** if it was the last). **Self delete account** removes the whole **`Account`**. Registration reuses **`Account`** when the email exists and the password matches. **`Doctor.user_id`** still points at **`users.id`**; **`get_linked_doctor`** scopes by the active membership’s org. Optional **`MCP_ORGANIZATION_ID`** (backend settings) overrides the default org for MCP tools. Frontend: org picker on ambiguous login; **AppShell** user menu lists orgs when **`memberships.length > 1`**.
- **Login organization code:** Removed the pre-filled **`default`** value on the sign-in form so accounts in a non-default organization are not sent to the wrong slug by mistake; the field stays empty unless needed (same email in more than one organization → **409** and hint to enter the code). Placeholder shows an example only.
- **Admin team (single screen):** **`/organization/team`** merges the staff directory and team-member editor: click a row to open a detail modal (team profile via embedded editor, login, roles, unlink, remove, copy IDs). **Add team member** opens the create dialog on the same page. **`/organization/team/members`** redirects to **`/organization/team`**; the team layout shows **Team members** and **Join requests** tabs only.
- **Team member terminology:** Product copy uses **team member** / **Teammitglied**; admin roster-people management is on **`/organization/team`** (row detail modal). **`/doctors`** and **`/organization/team/doctors`** were removed (no redirects). The backend still uses the **`Doctor`** model and **`GET|POST|PATCH|DELETE /api/v1/doctors`**; OpenAPI tags use **`team-members`**. User-visible API error strings and MCP tool docstrings were aligned with the same wording.
- **Sign-in and recovery:** `POST /api/v1/auth/login` uses **`email`** + **`password`** only (single password field); **`organization_slug`** may be omitted or blank when the email matches **exactly one** active user across all orgs; **`409`** with detail **`organization_slug_required`** when the same email exists in more than one organization. **`POST /api/v1/auth/register/create-organization`** and **`POST /api/v1/auth/register/join-organization`** require **`password_confirm`** matching **`password`**. Applicants with **no pending** join request may **`POST /api/v1/auth/me/join-request`** to submit a new request (e.g. after rejection or cancel). **`DELETE /api/v1/organization/users/{id}`** still removes the **`User`** row (sign-in requires re-registration via join); **unlink login** on a doctor only clears **`Doctor.user_id`** and keeps the user account.

## 2026-05-02
- **Admin navigation:** Sidebar toggles between **full labels** and a narrow **icon-only** rail (persisted in `localStorage` as `shift-planner-sidebar-expanded`, with migration from `shift-planner-sidebar-open`), **user avatar menu** (settings, language, logout), and grouped **Team** (`/organization/team` with team members + access combined; join requests) and **Shifts** (`/organization/shifts` tabs: groups, types). Legacy routes redirect to the new paths where still applicable.
- **Admin org staff directory (email-keyed):** **`GET /api/v1/organization/staff-directory`** merges **`User`** and **`Doctor`** by normalized org email with **`link_status`**; **`/organization/users`** uses it as a single table (copy user / doctor / linked-login ids). **`GET /api/v1/organization/users`** unchanged for raw user rows.
- **Admin remove users:** **`DELETE /api/v1/organization/users/{id}`** (admin, same org) removes a user account; blocks self-delete and removing the **sole admin**. Team & access UI adds **unlink login from doctor** (`PATCH` doctor `user_id: null`) and **remove user** actions with confirmations.
- **Admin role changes:** **`PATCH /api/v1/organization/users/{id}`** with `{ "role": "admin"|"planner"|"doctor" }` (admin, same org); cannot demote the **sole admin**. Clears **`user_shift_groups`** when the new role is not **planner**. Staff directory includes role dropdowns for the email-matched account and for a **separate linked-login** user when present; role changes, unlink, and remove are confirmed in a **modal** (join **`applicant`** is not assignable here).
- **Self-service account deletion:** `POST /api/v1/auth/delete-account` (password confirmation) deletes the current user, clears the session, and blocks deleting the **sole admin** in an org. Settings UI danger zone (DE/EN).
- **Registration and onboarding:** `organizations.slug` (globally unique), `organization_join_requests`, and `User.role` **`applicant`**. `users.email` is unique per **`organization_id`**. Added **`POST /api/v1/auth/register/create-organization`**, **`POST /api/v1/auth/register/join-organization`**, **`GET /api/v1/organizations/lookup`**, admin **`/api/v1/organization`** (settings + join-request approve/reject/cancel), and **`GET /api/v1/auth/me/join-request`**. Frontend: `/register/create`, `/register/join`, `/pending-onboarding`, **`/organization`** join inbox, login org code field, **AppShell** rules for applicants and admins. Alembic **`202605020001`**. (Login slug optionality is documented under **2026-05-03**.)

## 2026-05-01
- Introduced **organizations** as the tenancy boundary (`Organization`, `organization_id` on users, doctors, shift groups, templates, planning periods) with per-org composite uniques and Alembic migration `202605010001`.
- Added **`planner`** role and **`user_shift_groups`** so planners use the planning UI only for assigned shift groups; planners get a **scoped read-only doctors list** (doctors who share those groups). Admins retain full mutations; creating and deleting planning months is **admin-only**; publish, unpublish, regenerate roster, matrix, and roster writes stay available to planning users.
- Enforced **`shift_group_id`** for non-admin planners on matrix, roster, validation, and both planning CSV exports to avoid cross-group data exposure.
- Extended **`GET /api/v1/auth/me`** with `organization_id`, `planner_shift_groups`, and **`capabilities`**; frontend **AppShell** and redirects use capabilities so one account can be admin, planner, and linked doctor.
- Session responses (`GET /auth/me`, `POST /auth/login`) include nested **`organization`** (`id`, `name`, `plan_tier`); **AppShell** and **Settings** show the organization name (and ID on settings) for signed-in users.
- Added **`DEFAULT_ORGANIZATION_ID`** setting and MCP behavior scoped to that org; optional **`seed_planner_user`** script (`PLANNER_SEED_EMAIL`, `PLANNER_SEED_PASSWORD`). Org **seat limits** hook when linking `Doctor.user_id`.
- Documented the above in `README.md`, `AGENTS.md`, and `.env.example`.
- Fixed `seed_doctor_users` to set `User.organization_id` from each doctor’s org (or `DEFAULT_ORGANIZATION_ID`) so Docker startup no longer fails on `NOT NULL` for `users.organization_id`.
- Docker Compose now forwards `DOCTOR_SEED_PASSWORD`, `DEFAULT_ORGANIZATION_ID`, `PLANNER_SEED_EMAIL`, and `PLANNER_SEED_PASSWORD` to the backend container. `seed_planner_user` reads `planner_seed_*` from `Settings`, supports re-run **updates** for an existing planner, and treats empty `PLANNER_SEED_EMAIL` as the default `planner@example.com` so login matches the seeded password.
- `GET /api/v1/roster-matrix/{id}` accepts optional `doctor_portal=true` so planner accounts with a linked doctor use **planning** roster rules on `/planning` (draft allowed) and **published** rules on `/my-planning`. Planning workspace waits for session before mounting matrix/roster editors to avoid unscoped API calls.
- Frontend uses a **single root `LocaleShell`** (`app/ClientRoot.tsx`) so `/auth/me` is not refetched in a blank session on each page; planner matrix gating uses `me.role === "planner"` and the planning body shows a short loading state until the session is ready.
- **Planning matrix (no `shift_group_id`)**: backend now returns group-scoped `template_slot_days` (with `shift_group_id`), templates in any shift group, and org-wide `shift_intents`; the wishes UI shows wish/no-go for admins the same way as for a filtered group, using the row’s group when saving.

## 2026-04-29
- Added `doctor` users linked via `doctors.user_id`, role-based REST authorization, `PlanningPeriod.published_at` and `POST /planning-periods/{id}/publish`, doctor self profile `GET|PATCH /auth/me/doctor`, enriched `GET /auth/me`, seed script `seed_doctor_users` with `DOCTOR_SEED_PASSWORD`, frontend session-aware nav, `/my-planning`, `/profile`, planner publish UI, and read-only roster for doctors until publish.
- Added `POST /planning-periods/{id}/unpublish` and planner UI support to revert a published month back to draft, which immediately hides roster access for doctor accounts again.
- Narrowed wishes matrix day statuses to Urlaub, Forschung, Lehre, and Frei (all block roster assignments that day); legacy statuses migrate to Frei.
- Added `planning_shift_intents` for per-shift-group wish or no-go per doctor, date, and shift template, with bulk REST and MCP tools and roster validation (`ROSTER_TEMPLATE_NO_GO_CONFLICT`).
- Enriched filtered planning matrix responses with group templates, generated template-by-day keys, and intents; roster matrix includes intents for the doctor picker.
- Replaced native roster doctor `<select>` with an accessible dropdown showing day-status dots and wish/no-go hints; assignments default to honoring no-go unless Manual override is checked.

## 2026-04-26
- Initialized the AI-first shift planner monorepo plan in code.
- Added Docker Compose services for Postgres, FastAPI backend, FastMCP server, and Next.js frontend.
- Added project governance docs and standing FastMCP/i18n documentation rules.
- Added a FastMCP server with read resources and guarded mutating tools backed by the shared backend service layer.
- Added a bilingual Next.js PWA shell and core admin screens.
- Replaced Docker `psycopg[binary]` dependency usage with portable `psycopg` plus system `libpq5` to support Linux ARM builds.
- Changed the host Postgres port default to `5433` to avoid conflicts with local Postgres installations.
- Added matrix-first planning with `PlanningCell`, `DoctorPeriodNote`, REST endpoints, FastMCP resources/tools, validation, CSV export, and frontend matrix editing.
- Added planning-month creation directly to the matrix editor so new matrices can be created and loaded without using API docs.
- Made doctor and shift-template lists load automatically when their routes are opened.
- Made the matrix/wishlist screen load the latest planning period automatically and documented Docker hot-reload behavior.
- Removed per-cell matrix save buttons; matrix status changes now save immediately and comments autosave after editing, with a top-level manual save/reload action.
- Added a separate final roster matrix backed by `RosterSlot` and `RosterSlotAssignment`, with rows as days and generated shift slots.
- Added REST endpoints, CSV export, validation, and FastMCP resource/tools for the final roster matrix.
- Changed the planning UI toward a shift-by-day final roster editor and a doctor-by-day wishes matrix.
- Removed final roster comment editing from the UI and CSV export.
- Added wishes/status pills to final roster cells so assigned doctors' conflicts are visible inline.
- Added a unified `/planning` workspace with shared month selection, wishes, final roster, inline conflict summary, CSV exports, and workload stats.
- Simplified the navbar to Dashboard, Planning, Doctors, Shift Types, and Settings.
- Removed standalone frontend pages for wishes, roster, validation, and export while keeping backend validation available for inline planning checks.
- Moved doctor/month notes into per-doctor buttons in the wishes matrix header with modal editing.
- Added a Planning view toggle for the full stacked workflow or tabbed Wishes, Roster, and Analysis sections.
- Added shift templates and variants for weekday/weekend/holiday-aware slot generation with North Rhine-Westphalia holiday support.
- Replaced fixed shift-type roster columns with concrete generated roster slots per day.
- Added shift-template REST and FastMCP surfaces plus a guided frontend template builder and monthly slot preview.
- Limited shift-template categories to Bereitschaftsdienst/on-call duty, Rufdienst/stand-by duty, and Andere/other.
- Improved shift-template cards so variants display as compact structured rows instead of raw nested data.
- Added Spätdienst/late duty as a shift-template category and inline three-dot editing for template and variant cards.
- Made the planning workspace default to the tabbed view and replaced tab/view toggle text buttons with icon buttons.
- Condensed the planning workspace header into a compact toolbar with modal create-month and export actions.
- Added destructive planning-month actions to delete a month or regenerate its roster slots from current shift templates, clearing assigned shifts after confirmation.
- Colored weekday, weekend, and holiday day-class pills distinctly in shift-template and roster-slot displays.
- Moved shift-template editing into a dedicated modal with field widths matched to names, codes, times, counts, and status controls.
- Simplified the shift-template editor by inferring overnight offsets from times, removing manual sorting, and using one modal-level save action.
- Added guarded shift-template deletion from the editor modal, clearing variants, generated slots, and related assignments.
- Removed old simple shift type, availability request, and direct roster assignment compatibility code and added a cleanup migration for existing local databases.
