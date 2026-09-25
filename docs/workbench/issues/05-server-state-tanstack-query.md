---
title: "Move server state to TanStack Query, starting with the planning workspace"
labels: frontend, architecture
---

## Context

Part of ADR 0001 (`docs/decisions/0001-desktop-first-workbench.md`, decision 3). A dense grid
with optimistic edits (#117) and an inspector that reacts to the selected cell (#115) both
need cached, shared, invalidatable server state. Today every component fetches for itself.

What exists on `main`:

- 33 files in `frontend/components` and `frontend/app` combine `useEffect` with `apiFetch`.
- `frontend/components/PlanningWorkspace.tsx` (`PlanningWorkspaceContent`, from line 138) holds
  about 30 `useState` calls, most of them server data: `periods`, `rosterMatrix`,
  `fairnessAccounts`, `warnings`, `shiftGroups`, `dayStatusDefinitions`, `groupPlanningStatus`,
  `memberShifts`. It forces refetches with counters: `rosterReloadToken`, `matrixReloadToken`,
  `solverReloadToken`, `swapReloadToken` (21 uses in the file). `DutyActivityShiftList.tsx` does
  the same.
- The session (`GET /api/v1/auth/me`) is fetched in `components/LocaleProvider.tsx` and shared
  through `SessionContext` / `useSession()`.
- `MatrixEditor` and `RosterMatrixEditor` fetch their own matrices and report back to the
  workspace through callbacks, so the workspace and the editor can hold different versions of the
  same roster.
- Planning endpoints loaded by the workspace: `/api/v1/planning-periods`,
  `/api/v1/shift-groups?active_only=true`,
  `/api/v1/planning-day-status-definitions?active_only=true`, `/api/v1/matrix/{id}`,
  `/api/v1/roster-matrix/{id}`, `/api/v1/validation/{id}`, `/api/v1/fairness/{id}`,
  `/api/v1/dashboard/team-member`, solver runs, shift swaps, plan versions. Planners must always
  pass `shift_group_id`.

## Decision for this issue

- **TanStack Query v5** (`@tanstack/react-query`, plus `@tanstack/react-query-devtools` in
  development only).
- One `QueryClient` created in `frontend/app/ClientRoot.tsx`. Defaults: `staleTime` 30 s for
  planning data, `refetchOnWindowFocus` true, `retry` 1 for queries and 0 for mutations, and
  `ApiError` with status 401 or 403 never retried.
- **Query keys in one module**, `frontend/lib/queryKeys.ts`, as factory functions. Every key
  that depends on scope includes `organizationId` and, where the API takes it, `shiftGroupId`.
  Example: `queryKeys.rosterMatrix(orgId, periodId, shiftGroupId)`. Switching organization (Settings,
  `POST /api/v1/auth/me/active-organization`) calls `queryClient.clear()`.
- **Hooks per resource** in `frontend/lib/queries/` (for example `useRosterMatrix`,
  `useWishesMatrix`, `useValidation`, `useFairness`, `usePlanningPeriods`, `useShiftGroups`,
  `useSolverRuns`, `useShiftSwaps`, `useSession`). New hooks use the typed client from #111.
- **Mutations invalidate by key**, never by counters. A roster assignment invalidates the roster
  matrix, validation and fairness for that period and group. A status transition invalidates the
  group planning status and plan versions.
- **Optimistic update** for single roster cell assignment and wishes cell edits, with rollback on
  error. This replaces the "restore previous on failure" code in `RosterMatrixEditor`.
- The session keeps its context API (`useSession()` returns the same shape) but is backed by a
  query, so other hooks can depend on it.

## Scope

1. Provider, defaults, devtools, `queryKeys.ts`, `lib/queries/`.
2. Rewrite data loading in `PlanningWorkspace.tsx`, `MatrixEditor.tsx`, `RosterMatrixEditor.tsx`,
   `SolverRunPanel.tsx`, `ShiftSwapMarketplace.tsx`, `ShiftSwapApprovalQueue.tsx`,
   `PlanVersionPanel.tsx`, `FairnessAccountsPanel.tsx`, `ComplianceReportPanel.tsx`,
   `DutyActivityShiftList.tsx` onto hooks. Remove every `*ReloadToken`.
3. The editors read the roster and wishes matrices from the same query as the workspace. No
   duplicate fetch of the same matrix on one page (check with the network tab and a Playwright
   request counter).
4. Solver run polling uses `refetchInterval` while a run is `queued` or `running`, and stops when
   it is terminal.
5. Vitest tests for the query key factory (scope is always included) and for the invalidation map
   (a roster mutation invalidates exactly the expected keys). Use `QueryClient` with a mocked fetch.
6. The remaining `useEffect` + `apiFetch` sites outside planning (admin panels, dashboards) are
   **listed** in the PR with a follow-up checkbox list, not migrated. They move when their page is
   redesigned.

## Out of scope

- Splitting `PlanningWorkspace` into member and planner pages (#114).
- Layout, inspector, grid (#115, #117).
- Admin and dashboard pages beyond listing them.

## Acceptance criteria

- [ ] `grep -rn "ReloadToken" frontend/components` is empty.
- [ ] `PlanningWorkspace.tsx` holds no server data in `useState`; all of it comes from hooks in
      `lib/queries/`.
- [ ] Opening `/planning` for one period and group fetches each of roster matrix, wishes matrix,
      validation and fairness at most once. A Playwright test counts requests.
- [ ] Assigning a roster cell updates the cell immediately and rolls back with an error message
      when the API refuses (Playwright: force a refusal by assigning a member who has a no-go).
- [ ] Switching organization clears the cache (test).
- [ ] Solver run polling stops at a terminal status (test with a mocked run).
- [ ] Playwright flows and golden screenshots from #110 pass unchanged.
- [ ] `npm run lint`, `npm run typecheck`, `npm run build`, `npm run test`, `npm run test:e2e`
      green.

## Dependencies

Needs #110 and #111. Blocks #114, #115, #117.

## Implementation prompt

```text
You are working in the `aegis301/shift-planner` repository.
Start from the latest `main`: `git fetch origin && git switch -c feat/tanstack-query origin/main`.
Do not continue on a branch from another issue.

Read these before writing any code, and follow them strictly:
1. `AGENTS.md`, especially **Working an issue**, **Style → Frontend surfaces** and **Testing Expectations**.
2. `docs/rollout/STATE.md`, especially **Traps this project has already hit**.
3. `docs/decisions/0001-desktop-first-workbench.md`.
4. This issue's spec in full: `docs/workbench/issues/05-server-state-tanstack-query.md`.

Standing rules that matter most here:
- Business logic lives in backend services, not in React components. Moving fetches into hooks
  must not move any rule or validation into the frontend.
- Planners must always send `shift_group_id`. Every query key for a planning resource includes it.
- Update `README.md`, `CHANGELOG.md`, `AGENTS.md` and `docs/rollout/STATE.md` in the same change.
- Before you finish: `cd frontend && npm run lint && npm run typecheck && npm run build && npm run test && npm run test:e2e`.

Task: replace hand-managed server state in the planning workspace with TanStack Query. This is a
behaviour-preserving refactor.

1. Confirm the Playwright suite is green on `main` before you start. If not, stop and report.
2. Read `PlanningWorkspace.tsx` top to bottom and write down, in the PR description, every piece
   of server state it holds, where it is fetched, and what triggers a refetch (including every
   `*ReloadToken`). That table is your migration checklist.
3. Add the provider, `queryKeys.ts` and `lib/queries/`. Use the typed client from #111 in new
   hooks.
4. Migrate one resource at a time (periods, shift groups, day statuses, wishes matrix, roster
   matrix, validation, fairness, solver runs, swaps, plan versions, member shifts), one commit
   each, running the e2e suite after each.
5. Replace counters with invalidation. Write the invalidation map as a tested function.
6. Add optimistic updates for single-cell roster and wishes edits.
7. List the non-planning `useEffect` fetches you did not migrate.

Do not change: page layout, component structure beyond data loading, API calls' URLs or payloads,
the `variant` prop on `PlanningWorkspace` (#114 removes it).

Stop and report instead of guessing if: two components on the page need different versions of
the same resource (for example a plan version snapshot next to the live roster). Propose the key
design before implementing it.

Prove it: walk the acceptance criteria one by one in the PR and name the test, command output or
CI run that proves each.
```
