# Shift Planner

AI-first shift planning for doctors, built with FastAPI, Next.js, Postgres, Docker Compose, and FastMCP.

## Current Scope
The MVP is a single-admin planner for monthly doctor rosters. It has two matrix planning surfaces: a wishes matrix where rows are days and columns are doctors, and a final roster matrix where rows are days and concrete generated shift slots. It also supports doctors, shift templates with weekday/weekend/holiday variants, planning periods, doctor/month notes for source emails, validation warnings, CSV export, printable views, and an MCP interface designed for LLM control. Shift template categories are currently `Bereitschaftsdienst`/on-call duty, `Rufdienst`/stand-by duty, `Spätdienst`/late duty, and `Andere`/other.

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
Use `/planning` in the frontend for the active workflow. One selected planning month controls wishes, final roster assignment, inline validation, CSV exports, and workload stats. The page supports both a full stacked view and a tabbed view for Wishes, Roster, and Analysis.

Cell statuses:
- `dienstwunsch`
- `urlaub`
- `kein_dienst`
- `forschung`
- `lehre`
- `frei`
- `tagdienst`
- `nachtdienst`
- `spaetdienst`
- `rufdienst`

Doctor/month notes store source emails and summaries so future LLM parsing can propose matrix updates. In the wishes matrix, each doctor header has a notes button that opens that doctor's month-specific source text and summary.

Shift templates are configured under Shift Types. A template has one or more variants that define applicability (`weekday`, `weekend`, `holiday`, or `any`), start/end times, overnight offsets, and required count. Holidays use the North Rhine-Westphalia German holiday calendar and behave like weekend rules unless explicit holiday variants exist.

The final roster matrix has one row per day and shows only the concrete shift slots generated for that date. Each roster cell assigns a doctor to that date/slot, and changes autosave. If the assigned doctor has a wishes matrix status on the same day, the roster cell shows the matching colored status pill; unavailable statuses are highlighted as conflicts.

The frontend no longer has standalone `/requests`, `/roster`, `/validation`, or `/exports/print` pages. Validation remains available through the backend API and MCP, and `/planning` uses it for inline conflict summaries.

The `/planning` toolbar includes destructive month actions behind confirmation dialogs: deleting a planning month removes its wishes, notes, generated roster slots, and assignments; regenerating a month clears roster assignments and rebuilds roster slots from the current shift templates.

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

## Documentation Rule
When behavior, setup, architecture, API shape, MCP capabilities, or roadmap changes, update `README.md`, `AGENTS.md`, `CHANGELOG.md`, `PLAN.md`, or `BRAINSTORM.md` as appropriate.
