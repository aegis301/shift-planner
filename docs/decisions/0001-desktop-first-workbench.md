# 0001: Desktop-first planner workbench, mobile-first member companion

- **Status:** Accepted
- **Date:** 2026-09-25
- **Decided by:** @aegis301
- **Concept issue:** #107
- **Supersedes:** the "mobile-first layouts" style rule in `AGENTS.md` (in force until this record)

## Context

The frontend was built mobile-first on the assumption that most people would use the product on a
phone. That assumption holds for one group of users and not for the other.

The product has two audiences with different jobs:

| | Planner and admin | Team member |
|---|---|---|
| Who | Planners, admins. A few people per organization | Every doctor on the roster. Many people |
| Job | Build and defend a month: wishes matrix, roster matrix, validation, solver, fairness, compliance report, rule sets, contracts, staff directory | Check own duties, enter wishes, offer or claim a swap, record a call-out at 3 a.m., read hours |
| Session | Long, dense, many decisions in a row | Short, one decision, often interrupted |
| Right device | Desktop or laptop, keyboard, large screen | Phone, notifications, sometimes no signal |

Holding the planner surfaces to a phone-width design has cost the most where the product is
strongest. Concretely, on `main` at the time of this record:

- `/planning` and `/my-planning` render the same 2,124-line `PlanningWorkspace` component with a
  `variant` switch (`frontend/app/planning/page.tsx`, `frontend/app/my-planning/page.tsx`). Each
  audience pays for the other's constraints.
- The two matrices (`MatrixEditor.tsx`, 2,100 lines, and `RosterMatrixEditor.tsx`, 1,567 lines)
  are hand-built tables with sticky headers and click-to-open pickers. There is no keyboard
  navigation, no range selection, no copy and paste, no undo, and no virtualization.
- Detail views are modals. At least 14 components hand-roll a `fixed inset-0` overlay. There is
  no shared dialog, menu, popover or combobox primitive and no design tokens beyond four colors
  in `tailwind.config.ts`.
- Server state is managed by hand: `PlanningWorkspace` has about 50 `useState`/`useEffect` calls
  and several `*ReloadToken` counters to force refetches.
- Frontend types for API payloads are written by hand (67 exported types in `frontend/lib/*.ts`)
  although FastAPI already publishes an OpenAPI schema (135 paths, 206 schemas).
- There are no frontend tests of any kind. CI runs lint, typecheck and build only.

At the same time, the member side has needs a web page serves poorly: push notifications for swaps
(#101), offline capture of duty activity, and a home-screen presence.

## Decision

1. **Split the frontend by audience, not by breakpoint.**
   - The **planner workbench** (`/planning`, `/hours`, `/organization/*`, `/shift-groups`,
     `/shift-types`, admin dashboard) is **desktop-first**. Design target 1440 px wide, supported
     down to 1024 px. Below 1024 px the workbench shows a read-only view or a notice pointing to
     the member area. It is never squeezed into a phone layout.
   - The **member companion** (`/my-planning`, `/my-hours`, `/profile`, member dashboard) stays
     **mobile-first** as a web app until the native app covers it, and then remains as a fallback.
   - Shared entry pages (`/login`, `/register`, `/onboarding`, `/settings`) work at every width.
   - The split is implemented with Next.js route groups `app/(workbench)` and `app/(member)`, each
     with its own layout and shell. URLs do not change.

2. **The workbench is built for density and the keyboard.**
   - The two matrices move onto one shared grid primitive with keyboard navigation, range
     selection, copy and paste, undo and redo, and row and column virtualization.
   - Detail moves out of modals into a persistent **inspector panel** on the right. Modals are
     kept for confirmation of destructive actions and for short forms.
   - A persistent **context bar** holds period, shift group and plan status. All of it lives in
     the URL (`?period=`, `?shiftGroup=` already exist).
   - A **command palette** (Ctrl+K / Cmd+K) reaches navigation and the main actions.
   - A density setting (comfortable / compact) applies to grids and tables.

3. **Frontend foundations come before the redesign.**
   - Radix UI primitives, wrapped in `frontend/components/ui/`, and CSS-variable design tokens.
     shadcn/ui is the recommended way to generate the wrappers, not a runtime dependency.
   - TanStack Query for all server state.
   - API types generated from FastAPI's OpenAPI schema, with a CI check that fails on drift.
   - Vitest with Testing Library for units, Playwright for end-to-end and golden screenshots.

4. **The member companion becomes a native app, built with Expo (React Native).**
   - It is scoped to member jobs only: my duties, wishes, swaps, duty activity capture, hours,
     notifications, calendar. No planning and no administration, ever.
   - It shares TypeScript code with the web app through an npm workspace: `packages/api-client`
     (generated types and fetch wrapper), `packages/i18n` (DE/EN dictionaries), `packages/domain`
     (pure helpers such as shift display and overlap).
   - The workspace move happens when the app starts, not before. Until then generated types live in
     `frontend/lib/api/`.

5. **The backend grows what a second client needs.**
   - Bearer token authentication with refresh tokens and revocable device sessions, next to the
     existing `shift_planner_session` cookie. The cookie stays the web mechanism.
   - A member API under `/api/v1/me/...` that returns what one phone screen needs in one request,
     built on the existing services.
   - Roster change sets: bulk assignment writes that are evaluated once, reported per row, and
     revertible. They back paste and undo in the grid.
   - Push delivery for notifications, on top of the notification design from #101.
   - Idempotent duty activity creation so an offline queue can retry safely.

6. **Time is stored as real instants.** Roster slot start and end times are stored as absolute
   instants computed in the organization's time zone. This is a prerequisite for offline capture
   on a phone and fixes a defect that exists today (see #109 below).

## Consequences

- `AGENTS.md` style rules change in the same change as this record: workbench desktop-first,
  member mobile-first, and the foundations above are the default for new frontend code.
- New planner features are designed at 1440 px first. A planner feature does not need a phone
  layout. A member feature does.
- The `variant` prop on `PlanningWorkspace` goes away. Member and planner screens may share
  components (a read-only roster view, a duty card) but not a page component.
- The web member area is not deleted when the app ships. It stays the fallback for people who do
  not install an app and for desktop users.
- Every capability stays reachable from web UI, REST and MCP. The native app is one more client of
  the same REST API, not a new source of business logic.
- CI grows: a Playwright job, an OpenAPI drift check, and later an Expo typecheck.
- The Docker build context for the web frontend changes when the npm workspace lands (#121).
  `docker-compose.yml`, `docker-compose.prod.yml`, `frontend/Dockerfile*` and
  `deploy/README.md` change with it.

## Alternatives considered

- **Stay mobile-first and responsive for everything.** Rejected. It keeps the matrices and the
  inspector-free layout that limit planners most, for a user group that does not plan on phones.
- **One native app for every role.** Rejected. Building a roster on a phone is not a job anyone
  has. It doubles the planner UI for no user.
- **PWA only for members, no native app.** Kept as the interim state, not the end state. Web push on
  iOS works only for home-screen-installed PWAs, background work and offline storage are weaker,
  and a store presence matters for adoption in a department.
- **Flutter or native Swift/Kotlin for the member app.** Rejected. Neither shares code with the
  TypeScript frontend. Expo shares types, API client, i18n and domain helpers and needs no second
  language on a one-person team.
- **Move `frontend/` into `apps/web` right away.** Deferred to #121. It touches Docker, Compose,
  CI and deploy documentation, and has no benefit until a second TypeScript app exists.
- **AG Grid for the matrices.** Allowed as an outcome of #117, not mandated. The recommendation
  is TanStack Table plus TanStack Virtual with our own cell rendering, because the roster matrix
  cells are not spreadsheet cells (a slot has a template, variant, day class, warnings, wishes and a
  swap state). #117 decides with a short written comparison in the PR.

## Work plan

Issue specs live in `docs/workbench/issues/`. GitHub numbers are recorded in
`docs/workbench/created-issues.json`. All issues are sub-issues of #107.

| Issue | Spec | What | Depends on |
|---|---|---|---|
| #109 | `01-slot-times-as-instants.md` | Store roster slot times as real instants in the org time zone | none |
| #110 | `02-frontend-test-harness.md` | Vitest, Testing Library, Playwright, golden screenshots of `/planning` | none |
| #111 | `03-generated-api-types.md` | OpenAPI export, generated types, typed client, drift check | none |
| #112 | `04-ui-foundation.md` | Radix primitives, design tokens, dialog migration | #110 |
| #113 | `05-server-state-tanstack-query.md` | TanStack Query in `PlanningWorkspace` and the member views | #110, #111 |
| #114 | `06-route-split-workbench-member.md` | Route groups, two shells, split `PlanningWorkspace` | #112, #113 |
| #115 | `07-workbench-layout.md` | Context bar, inspector panel, command palette, density | #114 |
| #116 | `08-roster-change-sets.md` | Bulk roster writes, per-row results, revert (backend, REST, MCP) | none |
| #117 | `09-roster-grid.md` | Shared grid primitive, roster matrix on it, paste and undo | #115, #116 |
| #118 | `10-wishes-grid.md` | Wishes matrix on the grid primitive | #117 |
| #119 | `11-token-auth-device-sessions.md` | Bearer tokens, refresh, device sessions | none |
| #120 | `12-member-api.md` | `/api/v1/me/...` read endpoints for the member app and web | #111 |
| #121 | `13-js-workspace-packages.md` | npm workspace, `packages/api-client`, `packages/i18n`, `packages/domain` | #111, #114 |
| #122 | `14-expo-member-app-scaffold.md` | Expo app: sign-in, my duties, i18n, CI | #119, #120, #121 |
| #123 | `15-offline-duty-activity-capture.md` | Idempotent duty activity API, offline queue in the app | #109, #122 |
| #124 | `16-member-app-wishes-swaps.md` | Wishes, swaps, hours and calendar in the app | #122 |
| #125 | `17-push-delivery.md` | Push tokens and delivery for notifications | #101, #119, #122 |

#116, #119 and #120 are backend-first and #109 is mostly backend. All four can run in parallel with the frontend track (#110 to #115).
