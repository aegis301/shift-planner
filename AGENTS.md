# Shift Planner Agent Instructions

## Purpose

This project is an AI-first shift planning tool for doctors. The MVP supports a single admin planner who manages doctors, monthly planning periods, a day-by-doctor wishes matrix, a day-by-shift final roster matrix, doctor/month source notes, validation warnings, and exports.

## Architecture

- Backend: Python, FastAPI, SQLAlchemy, Alembic, Postgres.
- Frontend: Next.js App Router, TypeScript, Tailwind CSS, PWA-ready, mobile first.
- MCP: FastMCP from the start. MCP tools and resources must reuse the same backend service layer as REST endpoints.
- Runtime: Docker Compose for local development with Postgres, backend, frontend, and MCP services.

## AI-First / FastMCP Rule

Every feature must be designed so it can be controlled by a web UI, REST API, and LLM through MCP. When adding functionality:

- Put business logic in typed service functions, not directly in route handlers or React components.
- Use stable identifiers and structured request/response schemas.
- Return predictable validation errors and warnings.
- Consider whether a read resource and/or guarded mutating FastMCP tool should be added.
- Update MCP docs and tests when MCP-visible behavior changes.
- Mutating MCP tools must require explicit authorization, currently through `MCP_ADMIN_TOKEN`.

## Matrix Planning Rule
The active planning workflow uses two monthly matrices:

- Wishes matrix: rows are days, columns are doctors, and each cell has exactly one status plus an optional comment. This is backed by `PlanningCell` and `DoctorPeriodNote`.
- Final roster matrix: rows are days, and each day shows concrete generated shift slots. Each cell assigns one doctor to one roster slot. This is backed by `RosterSlot` and `RosterSlotAssignment`.

## Shift Template Rule
Shift configuration must use `ShiftTemplate` and `ShiftVariant`. Do not add compatibility code for old simple shift-type, availability-request, or direct roster-assignment schemas. Variants define applicability (`any`, `weekday`, `weekend`, `holiday`), start/end time, inferred `end_day_offset`, and required count. Slot generation must use the North Rhine-Westphalia German holiday calendar; holidays behave like weekends unless an explicit holiday variant exists. Template categories are currently limited to `bereitschaftsdienst`, `rufdienst`, `spaetdienst`, and `other`, displayed as `Bereitschaftsdienst` / on-call duty, `Rufdienst` / stand-by duty, `Spätdienst` / late duty, and `Andere` / other.

Validation should compare final roster assignments against wishes/unavailable cells. The roster UI should surface assigned doctors' wishes as the same colored status pills used in the wishes matrix, with unavailable statuses highlighted as conflicts.

The primary frontend planning workflow is `/planning`. It owns the selected planning month and renders wishes, final roster assignment, inline validation, CSV export actions, and workload stats together. It must support both the full stacked view and a tabbed Wishes/Roster/Analysis view. Do not reintroduce separate frontend pages for wishes, roster, validation, or export unless the product direction changes.

Deleting a planning month and regenerating roster slots are destructive month-level actions. They must clear existing roster assignments, require explicit confirmation in the UI, and remain exposed through guarded REST/MCP service-backed functionality.

Deleting a shift template is also destructive because it removes variants, generated roster slots, and assignments tied to those slots. Keep it behind explicit UI confirmation and guarded REST/MCP service-backed functionality.

When a schema changes in a way that makes old local data incompatible, prefer a clear forward migration and tell the developer exactly what data must be recreated instead of carrying long-term compatibility branches.

Doctor/month notes belong in the wishes matrix header as per-doctor modal actions, not as a separate full-width form below the matrix.

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
- MCP changes should test resources/tools, authorization for mutations, and parity with backend services.
- Frontend changes should keep TypeScript, linting, and i18n key coverage passing.
- Docker startup should remain the baseline development path.

## Style

- Prefer small, explicit modules over broad abstractions.
- Keep domain services deterministic and easy for MCP tools to call.
- Use bright, fresh, accessible UI styling with mobile-first layouts and practical desktop density.
