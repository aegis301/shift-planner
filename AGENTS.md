# Shift Planner Agent Instructions

## Purpose

This project is an AI-first shift planning tool for **healthcare teams**; people on the roster are **team members**, backed by the **`TeamMember`** model and **`/api/v1/team-members`** in the API. **Sign-in** uses **`Account`** (global `email` + `hashed_password`); each **`User`** row is an **organization membership** (`account_id`, `organization_id`, `role`, …). The session cookie identifies the **active membership** (`User.id`). Data is scoped by the membership’s **`organization_id`** the same way as before for `TeamMember`, `ShiftGroup`, `ShiftTemplate`, and `PlanningPeriod` (see `Organization`). The default org id comes from **`Settings.default_organization_id`** (`DEFAULT_ORGANIZATION_ID`, typically `1`). **`POST /api/v1/auth/me/active-organization`** switches the session to another membership of the same account; **`POST /api/v1/auth/me/add-organization-membership`** (signed-in, password re-verified) requests membership in another org as **`applicant`** with a pending join request and moves the session to that new row. **`GET /api/v1/auth/me`** includes **`memberships`** (all memberships for the account) while **`capabilities`**, `organization`, `team_member_id`, and planner shift-group fields describe the **active membership** only. The app shell and **Settings** list orgs with roles; after an org switch the client redirects to a route that matches the new membership’s capabilities when the current path would be wrong (same defaults as post-login).

**Admins** (`User.role` `admin`) manage team members (`TeamMember` rows), shift groups, shift templates, create and delete planning months, publish state, wishes and roster matrices, notes, validation, and exports.

**Planners** (`User.role` `planner`) use the same planning surfaces for **existing** months: wishes matrix, roster matrix, publish, unpublish, regenerate roster, validation, exports, and workload stats, but only for shift groups listed in **`user_shift_groups`**. They receive a **read-only team member list** (from `/api/v1/team-members`) filtered to people who belong to at least one of those groups (intersection). They must pass **`shift_group_id`** on matrix, roster, validation, and CSV export APIs. They do not mutate `TeamMember` rows, templates, or shift-group membership.

**Applicants** (`User.role` `applicant`) are users who registered to **join** an existing organization and are waiting on an admin to approve an **`organization_join_request`** (create `TeamMember` + link, or link to an existing unlinked `TeamMember`). They sign in with **email + password** on `POST /api/v1/auth/login`. **`organization_slug`** is optional when their email maps to a **single** active user globally; otherwise it disambiguates. With no pending request (e.g. after reject or cancel), they may **`POST /api/v1/auth/me/join-request`** to submit a new request. They have no planning or team-member-portal capabilities until approved (role becomes `team_member`).

**Team members** are `TeamMember` rows; a user with a linked `TeamMember.user_id` uses `/my-planning` and `/profile` behavior (wishes, notes, self profile) and reads the roster matrix only after publish, subject to shift-group scope. The same user may also be `admin` or `planner` with overlapping capabilities; `GET /api/v1/auth/me` exposes **`capabilities`** (`admin`, `planning`, `team_member_portal`) plus `team_member_id`, `planner_shift_groups`, and `shift_groups` so the UI merges nav items correctly. For `GET /api/v1/roster-matrix/{id}`, **`team_member_portal=true`** selects the published-only team-member read path; omit it (default) when the client is the **planning** workspace so admins and planners—including planner accounts that also have a linked team member—edit draft rosters under `assert_planning_shift_group_scope`.

**Registration and org codes:** `organizations.slug` is globally unique and human-readable. Business logic lives in `app/services/registration.py`, `app/services/join_requests.py`, `app/services/organization_invites.py`, `app/services/organization_lifecycle.py`, and `app/services/organizations.py`; REST mirrors those services. **`Account.email`** is globally unique; **`User`** has **`UniqueConstraint(account_id, organization_id)`** (one membership per account per org). Reusing an existing email for **create organization** or **join** verifies the password against **`Account`** and adds a membership (or applicant flow) instead of creating a duplicate account. **`POST /api/v1/auth/register/create-organization`** and **`POST /api/v1/auth/register/join-organization`** require **`password_confirm`** matching **`password`**. An already signed-in account can request another org via **`POST /api/v1/auth/me/add-organization-membership`** (no `password_confirm`; session switches to the new applicant membership on success). **Admin membership invites** target an **existing `Account` email** only: **`POST /api/v1/organization/invites`** creates a pending **`organization_membership_invite`**; the invitee accepts or declines via **`/api/v1/auth/me/organization-invites`**. This is separate from **applicant join requests** (`organization_join_requests`). **Delete organization** is **`DELETE /api/v1/organization`** with a typed organization **name** confirmation; it is blocked for **`DEFAULT_ORGANIZATION_ID`**. Login may omit **`organization_slug`** only when the email resolves to exactly one **active membership**; otherwise the client must send it (**`409`** with JSON **`{ "code": "organization_slug_required", "organizations": [...] }`** if ambiguous).

**Account deletion:** Users may call **`POST /api/v1/auth/delete-account`** with their password (`delete_own_account` in `app/services/users.py`): it removes the **`Account`** and **all** memberships (after checking sole-admin rules in every org where the account is an admin).

**Org staff directory (admin):** **`GET /api/v1/organization/staff-directory`** lists one merged row per normalized email (`User` + `TeamMember` in the org) with **`link_status`** (API values such as `team_member_only` mean team-profile-only, login-only, unlinked, linked, mismatches). **`GET /api/v1/organization/users`** still returns raw `User` rows with linked team-member labels. Admin **Team** UI lives under **`/organization/team`**: one **staff directory** table with a row detail modal for team profile editing (same **`PATCH /api/v1/team-members/{id}`** surface as before), roles, unlink, remove, and copy IDs; **`/organization/team/members`** redirects here; the other tab is **join requests**. **`/organization/users`** redirects to **`/organization/team`**. Admins may **`DELETE /api/v1/organization/users/{id}`** to remove another **membership** in the org (not self, not sole admin)—this **deletes** that **`User`** row; if it was the account’s last membership, the **`Account`** is removed too (otherwise the person keeps other org logins). They may **`PATCH /api/v1/organization/users/{id}`** with **`{ "role" }`** to assign **`admin`**, **`planner`**, or **`team_member`** (cannot demote the sole admin; planner shift-group links cleared when role is not planner), and **unlink** a team-member login via existing **`PATCH /api/v1/team-members/{id}`** (clears **`TeamMember.user_id`** only; the user account remains). **Shift admin** UI is grouped under **`/organization/shifts`** (groups and types tabs; index redirects to groups).

**Subscription hooks:** `Organization` carries optional `seat_limit`, `billing_customer_id`, and `subscription_status` for future billing; linking a team-member login enforces seat limits when `seat_limit` is set.

## Architecture

- Backend: Python, FastAPI, SQLAlchemy, Alembic, Postgres.
- Frontend: Next.js App Router, TypeScript, Tailwind CSS, PWA-ready, mobile first.
- MCP: FastMCP from the start. MCP tools and resources must reuse the same backend service layer as REST endpoints. MCP targeting uses **`MCP_ORGANIZATION_ID`** when set, otherwise the default organization id (see `README.md`); it is not tied to a browser user’s active membership.
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
Team members (`TeamMember` rows) can belong to multiple shift groups; each group links to multiple shift templates. **Admins** may omit `shift_group_id` on planning reads/exports for a full-org view; the **wishes matrix** still returns `shift_templates`, `template_slot_days` (each row includes `shift_group_id`), and `shift_intents` so wish/no-go editing matches the filtered experience. **Planners** must supply `shift_group_id` (and it must appear in `user_shift_groups`). Roster assignment is rejected when the assignee does not share a group with the slot’s template (templates with no group remain assignable by any active `TeamMember`). Admin UI: `/shift-groups`; planning toolbar: shift group selector and `?shiftGroup=` URL param. Destructive **create/delete planning month** actions are admin-only in API and UI; mutating MCP tools remain admin-token gated.

## Matrix Planning Rule
The active planning workflow uses two monthly matrices:

- Wishes matrix: rows are days, columns are team members, and each cell has exactly one day-level status (`urlaub`, `forschung`, `lehre`, `frei`) plus an optional comment, backed by `PlanningCell` and `TeamMemberPeriodNote`. Per shift group, `PlanningShiftIntent` stores a wish or no-go per `team_member_id`, date, and shift template; the planning API returns intents when `shift_group_id` filters the matrix.
- Final roster matrix: rows are days, and each day shows concrete generated shift slots. Each cell assigns one team member to one roster slot. This is backed by `RosterSlot` and `RosterSlotAssignment`.

## Shift Template Rule
Shift configuration must use `ShiftTemplate` and `ShiftVariant`. Do not add compatibility code for old simple shift-type, availability-request, or direct roster-assignment schemas. Variants define applicability (`any`, `weekday`, `weekend`, `holiday`), start/end time, inferred `end_day_offset`, and required count. Slot generation must use the North Rhine-Westphalia German holiday calendar; holidays behave like weekends unless an explicit holiday variant exists. Template categories are currently limited to `bereitschaftsdienst`, `rufdienst`, `spaetdienst`, and `other`, displayed as `Bereitschaftsdienst` / on-call duty, `Rufdienst` / stand-by duty, `Spätdienst` / late duty, and `Andere` / other.

Validation compares final roster assignments against day-level wishes (all four statuses block assignment that day) and against template no-gos unless the assignment uses `manual_override`. The roster UI surfaces day status and wish/no-go hints in the team member picker, with conflicts highlighted.

The primary planner workflow is `/planning`; linked team members use `/my-planning` and `/profile`. Planning owns the selected month and renders wishes, final roster assignment, inline validation, CSV export actions, and workload stats together for planners. It must support both the full stacked view and a tabbed Wishes/Roster/Analysis view. Do not reintroduce separate frontend pages for wishes, roster, validation, or export unless the product direction changes.

Deleting a planning month and regenerating roster slots are destructive month-level actions. They must clear existing roster assignments, require explicit confirmation in the UI, and remain exposed through guarded REST/MCP service-backed functionality.

Deleting a shift template is also destructive because it removes variants, generated roster slots, and assignments tied to those slots. Keep it behind explicit UI confirmation and guarded REST/MCP service-backed functionality.

When a schema changes in a way that makes old local data incompatible, prefer a clear forward migration and tell the developer exactly what data must be recreated instead of carrying long-term compatibility branches.

Team member month notes belong in the wishes matrix header as per-column modal actions, not as a separate full-width form below the matrix.

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
