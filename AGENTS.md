# Shift Planner Agent Instructions

## Purpose

This project is an AI-first shift planning tool for doctors. Data is scoped by **`organization_id`** on `User`, `Doctor`, `ShiftGroup`, `ShiftTemplate`, and `PlanningPeriod` (see `Organization`). The default org id comes from **`Settings.default_organization_id`** (`DEFAULT_ORGANIZATION_ID`, typically `1`).

**Admins** (`User.role` `admin`) manage doctors, shift groups, shift templates, create and delete planning months, publish state, wishes and roster matrices, notes, validation, and exports.

**Planners** (`User.role` `planner`) use the same planning surfaces for **existing** months: wishes matrix, roster matrix, publish, unpublish, regenerate roster, validation, exports, and workload stats, but only for shift groups listed in **`user_shift_groups`**. They receive a **read-only doctors list** filtered to doctors who belong to at least one of those groups (intersection). They must pass **`shift_group_id`** on matrix, roster, validation, and CSV export APIs. They do not mutate doctors, templates, or shift-group membership.

**Applicants** (`User.role` `applicant`) are users who registered to **join** an existing organization and are waiting on an admin to approve an **`organization_join_request`** (create doctor + link, or link to an existing unlinked `Doctor`). They authenticate with the same **`organization_slug` + email** scope as other users; they have no planning or doctor-portal capabilities until approved (role becomes `doctor`).

**Doctors** are `Doctor` rows; a user with a linked `Doctor.user_id` uses `/my-planning` and `/profile` behavior (wishes, notes, self profile) and reads the roster matrix only after publish, subject to shift-group scope. The same user may also be `admin` or `planner` with overlapping capabilities; `GET /api/v1/auth/me` exposes **`capabilities`** (`admin`, `planning`, `doctor_portal`) plus `planner_shift_groups` and doctor `shift_groups` so the UI merges nav items correctly. For `GET /api/v1/roster-matrix/{id}`, **`doctor_portal=true`** selects the published-only doctor read path; omit it (default) when the client is the **planning** workspace so admins and planners—including planner+doctor—edit draft rosters under `assert_planning_shift_group_scope`.

**Registration and org codes:** `organizations.slug` is globally unique and human-readable. Business logic lives in `app/services/registration.py`, `app/services/join_requests.py`, and `app/services/organizations.py`; REST mirrors those services. `users.email` is unique per **`organization_id`**, not globally; login and registration always carry **`organization_slug`**.

**Account deletion:** Users may call **`POST /api/v1/auth/delete-account`** with their password (`delete_own_account` in `app/services/users.py`). The last **`admin`** user in an organization cannot delete themselves until another admin exists.

**Org user directory (admin):** **`GET /api/v1/organization/users`** lists all `User` rows in the org with ids, roles, and linked doctor labels so admins can copy **user id** back into the doctor form after unlinking.

**Subscription hooks:** `Organization` carries optional `seat_limit`, `billing_customer_id`, and `subscription_status` for future billing; linking a doctor login enforces seat limits when `seat_limit` is set.

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

## Shift groups (Dienstgruppen)
Doctors can belong to multiple shift groups; each group links to multiple shift templates. **Admins** may omit `shift_group_id` on planning reads/exports for a full-org view; the **wishes matrix** still returns `shift_templates`, `template_slot_days` (each row includes `shift_group_id`), and `shift_intents` so wish/no-go editing matches the filtered experience. **Planners** must supply `shift_group_id` (and it must appear in `user_shift_groups`). Roster assignment is rejected when the doctor does not share a group with the slot’s template (templates with no group remain assignable by any active doctor). Admin UI: `/shift-groups`; planning toolbar: shift group selector and `?shiftGroup=` URL param. Destructive **create/delete planning month** actions are admin-only in API and UI; mutating MCP tools remain admin-token gated.

## Matrix Planning Rule
The active planning workflow uses two monthly matrices:

- Wishes matrix: rows are days, columns are doctors, and each cell has exactly one day-level status (`urlaub`, `forschung`, `lehre`, `frei`) plus an optional comment, backed by `PlanningCell` and `DoctorPeriodNote`. Per shift group, `PlanningShiftIntent` stores a wish or no-go per doctor, date, and shift template; the planning API returns intents when `shift_group_id` filters the matrix.
- Final roster matrix: rows are days, and each day shows concrete generated shift slots. Each cell assigns one doctor to one roster slot. This is backed by `RosterSlot` and `RosterSlotAssignment`.

## Shift Template Rule
Shift configuration must use `ShiftTemplate` and `ShiftVariant`. Do not add compatibility code for old simple shift-type, availability-request, or direct roster-assignment schemas. Variants define applicability (`any`, `weekday`, `weekend`, `holiday`), start/end time, inferred `end_day_offset`, and required count. Slot generation must use the North Rhine-Westphalia German holiday calendar; holidays behave like weekends unless an explicit holiday variant exists. Template categories are currently limited to `bereitschaftsdienst`, `rufdienst`, `spaetdienst`, and `other`, displayed as `Bereitschaftsdienst` / on-call duty, `Rufdienst` / stand-by duty, `Spätdienst` / late duty, and `Andere` / other.

Validation compares final roster assignments against day-level wishes (all four statuses block assignment that day) and against template no-gos unless the assignment uses `manual_override`. The roster UI surfaces day status and wish/no-go hints in the doctor picker, with conflicts highlighted.

The primary planner workflow is `/planning`; linked doctors use `/my-planning` and `/profile`. Planning owns the selected month and renders wishes, final roster assignment, inline validation, CSV export actions, and workload stats together for planners. It must support both the full stacked view and a tabbed Wishes/Roster/Analysis view. Do not reintroduce separate frontend pages for wishes, roster, validation, or export unless the product direction changes.

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
