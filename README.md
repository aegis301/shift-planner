# Shift Planner

AI-first shift planning for doctors, built with FastAPI, Next.js, Postgres, Docker Compose, and FastMCP.

## Current Scope
The MVP supports an admin shift planner plus doctor accounts linked to `Doctor` rows. Planners manage doctors, shift groups, templates, planning months, publish workflow, validation, and exports. Linked doctors use `/my-planning` for wishes and no-gos in their shift groups, `/profile` for self-service profile fields, and read-only published roster views. It has two matrix planning surfaces: a wishes matrix where rows are days and columns are doctors, and a final roster matrix where rows are days and concrete generated shift slots. Shift template categories are currently `Bereitschaftsdienst`/on-call duty, `Rufdienst`/stand-by duty, `Spätdienst`/late duty, and `Andere`/other.

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
python -m app.scripts.seed_doctor_users
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

## MCP Development
```bash
cd mcp-server
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
PYTHONPATH=../backend python -m mcp_app.server
pytest
```

Mutating MCP tools require `MCP_ADMIN_TOKEN`. Read resources are local-first and share backend service behavior. Local CLI runs use FastMCP stdio by default; Docker Compose sets `MCP_TRANSPORT=http`.

## Planning Workflow
Use `/planning` for the planner workflow and `/my-planning` for linked doctors. One selected planning month controls wishes, final roster assignment, inline validation, CSV exports, and workload stats. The planner page supports both a full stacked view and a tabbed view for Wishes, Roster, and Analysis.

Wishes matrix day statuses (each blocks any roster assignment on that day for the doctor): `urlaub`, `forschung`, `lehre`, `frei`.

When a `shift_group_id` query is present on `GET /api/v1/matrix/{id}`, the response also includes `shift_templates`, `template_slot_days` (which concrete templates occur on which dates that month), and `shift_intents` for that group. Use `PUT /api/v1/matrix/{id}/shift-intents/bulk` with `{ "intents": [ { "doctor_id", "cell_date", "shift_group_id", "shift_template_id", "kind": "wish" | "no_go" | null } ] }` — `kind` null removes that intent row.

Doctor/month notes store source emails and summaries so future LLM parsing can propose matrix updates. In the wishes matrix, each doctor header has a notes button that opens that doctor's month-specific source text and summary.

Shift templates are configured under Shift Types. A template has one or more variants that define applicability (`weekday`, `weekend`, `holiday`, or `any`), start/end times, overnight offsets, and required count. Holidays use the North Rhine-Westphalia German holiday calendar and behave like weekend rules unless explicit holiday variants exist.

The final roster matrix has one row per day and shows only the concrete shift slots generated for that date. Each roster cell assigns a doctor to that date/slot, and changes autosave. The doctor picker shows a color dot for that doctor’s day-level wishes status and labels for wish/no-go on the slot’s template. Day-level unavailable statuses and template no-gos (unless Manual override is checked on the cell) are highlighted as conflicts.

The frontend no longer has standalone `/requests`, `/roster`, `/validation`, or `/exports/print` pages. Validation remains available through the backend API and MCP, and `/planning` uses it for inline conflict summaries.

The `/planning` toolbar includes destructive month actions behind confirmation dialogs: deleting a planning month removes its wishes, notes, generated roster slots, and assignments; regenerating a month clears roster assignments and rebuilds roster slots from the current shift templates. Publish is a separate confirmed action that marks the month published and unlocks roster reads for doctors (per selected shift group). Unpublish reverts that month to draft and immediately blocks doctor roster reads again.

Relevant CSV exports:
- Wishes matrix: `/api/v1/exports/matrix/{planning_period_id}.csv`
- Final roster matrix: `/api/v1/exports/roster-matrix/{planning_period_id}.csv`

Optional query parameter `shift_group_id` on `GET /api/v1/matrix/{id}`, `GET /api/v1/matrix/{id}/notes`, `GET /api/v1/roster-matrix/{id}`, `GET /api/v1/validation/{id}`, and the two CSV export routes above filters doctors, slots, warnings, and export rows to one shift group. Shift groups are managed at `GET|POST|PATCH|DELETE /api/v1/shift-groups` with `PUT /api/v1/shift-groups/{id}/doctors` and `PUT /api/v1/shift-groups/{id}/shift-templates` for memberships. Doctors carry `shift_group_ids`; roster assignments require the doctor to share a group with the slot’s template when that template belongs to at least one group.

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

## Users and roles
- `User.role` is `admin` (shift planner UI and full API) or `doctor` (wishes and self-profile; published roster only for their shift groups). `Doctor.user_id` links a doctor record to a doctor-role user; planners set it when creating or editing a doctor (numeric user id) or leave it empty.
- `GET /api/v1/auth/me` returns `doctor_id` and `shift_groups` (id and names) for the session. `GET|PATCH /api/v1/auth/me/doctor` load or update the linked doctor profile for doctor sessions.
- `POST /api/v1/planning-periods/{id}/publish` sets `status` to `published` and `published_at`; `POST /api/v1/planning-periods/{id}/unpublish` reverts back to `draft` and clears `published_at`.
- Doctors receive `403` on `GET /api/v1/roster-matrix/{id}` while the planning period is draft.
- Seed doctor logins: set `DOCTOR_SEED_PASSWORD` in `.env` (see `.env.example`), then run `python -m app.scripts.seed_doctor_users` (also runs after migrations in Docker Compose). It creates a `doctor`-role user per active unlinked doctor email and links `Doctor.user_id`. Skip when the email is already a user.

## Documentation Rule
When behavior, setup, architecture, API shape, MCP capabilities, or roadmap changes, update `README.md`, `AGENTS.md`, `CHANGELOG.md`, `PLAN.md`, or `BRAINSTORM.md` as appropriate.
