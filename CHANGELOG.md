# Changelog

## 2026-05-02
- **Admin org user directory:** `GET /api/v1/organization/users` and **`/organization/users`** UI list every account in the org with copyable user IDs and linked-doctor info so admins can re-link after clearing `user_id` on a doctor.
- **Self-service account deletion:** `POST /api/v1/auth/delete-account` (password confirmation) deletes the current user, clears the session, and blocks deleting the **sole admin** in an org. Settings UI danger zone (DE/EN).
- **Registration and onboarding:** `organizations.slug` (globally unique), `organization_join_requests`, and `User.role` **`applicant`**. `users.email` is unique per **`organization_id`**; **`POST /api/v1/auth/login`** requires **`organization_slug`**. Added **`POST /api/v1/auth/register/create-organization`**, **`POST /api/v1/auth/register/join-organization`**, **`GET /api/v1/organizations/lookup`**, admin **`/api/v1/organization`** (settings + join-request approve/reject/cancel), and **`GET /api/v1/auth/me/join-request`**. Frontend: `/register/create`, `/register/join`, `/pending-onboarding`, **`/organization`** join inbox, login org code field, **AppShell** rules for applicants and admins. Alembic **`202605020001`**.

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
