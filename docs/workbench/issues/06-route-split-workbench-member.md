---
title: "Split the frontend into a desktop workbench and a mobile member area"
labels: frontend, architecture, ux
---

## Context

This is the structural core of ADR 0001 (`docs/decisions/0001-desktop-first-workbench.md`,
decision 1). Until it lands, every planner change still has to fit a phone and every member
change carries planner code.

What exists on `main`:

- `frontend/app/planning/page.tsx` and `frontend/app/my-planning/page.tsx` both render
  `PlanningWorkspace` (`frontend/components/PlanningWorkspace.tsx`, 2,124 lines), the second with
  `variant="team_member"`. Inside, `planningUi`, `adminUi` and `teamMemberPortalUi` (around line
  200) switch behaviour, and redirects between the two routes are done in effects (around line
  210).
- One shell for everyone: `components/LocaleProvider.tsx` renders `components/AppShell.tsx`
  (502 lines) around every page. `AppShell` builds the sidebar from `me.capabilities`
  (`/`, `/planning`, `/hours`, `/my-planning`, `/my-hours`, `/profile`, `/organization/team`,
  `/organization/shifts/groups`) and enforces route access with
  `pathnameCompatibleWithMembership` from `lib/membershipRouting.ts`.
- `/` renders `components/Dashboard.tsx` with capability tabs `admin`, `planner`, `member`
  (`?tab=`).
- `frontend/lib/useMediaQuery.ts` is used once, in `MatrixEditor.tsx:266`
  (`(max-width: 1023px)`), to switch the wishes matrix to a narrow layout.
- `/shift-groups` and `/shift-types` only redirect to `/organization/shifts/*`.
- A user can be planner **and** linked team member at the same time (`capabilities.planning` and
  `capabilities.team_member_portal` both true).

## Decision for this issue

**Route groups** (URLs do not change):

```
frontend/app/
  (shared)/      login, register/*, onboarding, pending-onboarding, settings
  (workbench)/   page.tsx (/), planning, hours, organization/**, shift-groups, shift-types
  (member)/      my (new member home), my-planning, my-hours, profile
  layout.tsx     root: html, providers only (no shell)
```

- `(workbench)/layout.tsx` renders `WorkbenchShell`: left sidebar with planner and admin
  navigation, top bar with org switcher and user menu, a slot for the context bar (#115).
  Design target 1440 px, supported down to 1024 px.
- `(member)/layout.tsx` renders `MemberShell`: mobile-first, bottom tab bar under 768 px
  (Home, Wishes, Duties, Swaps, Profile), a simple top bar with a sidebar variant at 768 px and
  above. Touch targets at least 44 px.
- `(shared)/layout.tsx` renders a minimal centred layout.
- **`/` stays the workbench dashboard** (admin and planner tabs). The member tab moves to a new
  member home at **`/my`**. `membershipDefaultPath` sends team-member-only users to `/my` instead of
  `/my-planning`. A member-only user who opens `/` is redirected to `/my`.
- **Dual-role users** see a "Member area" / "Workbench" switch in both shells (user menu).
- **Below 1024 px** the workbench layout renders a `WorkbenchNarrowNotice` above the page: "This
  area is designed for larger screens" with links to the member area (if the user has
  `team_member_portal`) and a "Continue anyway" button that hides the notice for the session.
  Pages stay usable read-only-ish; nobody builds phone layouts for them any more.
- **`PlanningWorkspace` is split.** `components/planning/PlannerWorkspace.tsx` for `/planning`,
  `components/member/MemberPlanning.tsx` for `/my-planning`. Shared pieces become presentational
  components under `components/planning/shared/` (for example the read-only roster view, the
  wishes matrix for a single member, duty cards). No `variant` prop survives.
- Access control stays in `lib/membershipRouting.ts`, extended for `/my`, and is enforced by each
  shell's layout instead of a single `AppShell` effect.

## Scope

1. Create the three route groups and move pages without changing URLs. Next.js route groups do
   not affect paths; verify every existing URL still resolves (Playwright visits each).
2. Build `WorkbenchShell` and `MemberShell` with the `components/ui/` primitives from #112.
   Retire `AppShell`. Keep the sidebar collapsed state (`localStorage` key
   `shift-planner-sidebar-expanded`) for the workbench.
3. Split `PlanningWorkspace` as described. Move member-only features (own wishes, My shifts tab,
   duty activity control, `.ics` export, swap offers) to `MemberPlanning`. Move planner-only
   features (period create and delete, status transitions, sync and regenerate, solver, approval
   queue, analysis, exports) to `PlannerWorkspace`.
4. New `/my` member home: next duties (from `/api/v1/dashboard/team-member`), open swap actions,
   wishes deadline for the next draft period. Reuse `DashboardMemberPanel` content; it is the
   starting point, not a redesign. #120 later switches it to the member API.
5. Remove the narrow layout switch in `MatrixEditor.tsx` (`useMediaQuery("(max-width: 1023px)")`)
   from the planner path. The member path shows a single-member wishes view designed for phones.
6. Update `lib/membershipRouting.ts` and its unit tests from #110.
7. Update the Playwright suite: planner flows at 1440x900, member flows at 390x844, dual-role
   switch, narrow notice at 1000 px wide, redirect of member-only users from `/` to `/my`.
8. Update `AGENTS.md` sections that name `/my-planning` tabs, the dashboard, and the `variant`
   note in **Style → Frontend surfaces** (remove the "until then" caveat).

## Out of scope

- Context bar, inspector, command palette, density toggle (#115).
- Grid rewrite (#117, #118).
- Member API (#120).
- Visual redesign of member screens beyond what the new shell requires.

## Acceptance criteria

- [ ] Route groups `(shared)`, `(workbench)`, `(member)` exist. Every URL that existed before
      still works (Playwright visits the full list, including the redirects `/shift-groups`,
      `/shift-types`, `/organization/users`, `/organization/team/members`).
- [ ] `grep -rn "variant=\"team_member\"\|variant: \"planner\" | \"team_member\"" frontend` is empty
      and `PlanningWorkspace.tsx` is gone.
- [ ] Member-only user lands on `/my` after login and is redirected there from `/`.
- [ ] Dual-role user can switch between workbench and member area from the user menu in both
      shells.
- [ ] Workbench below 1024 px shows the narrow notice. Member area at 390 px has the bottom tab bar
      and no horizontal scroll (Playwright asserts `document.documentElement.scrollWidth <= 390`).
- [ ] Golden screenshots: workbench baselines change only in the shell chrome; member baselines
      are regenerated at 390x844 and reviewed in the PR with before/after images.
- [ ] Both dictionaries updated. `npm run lint`, `npm run typecheck`, `npm run build`,
      `npm run test`, `npm run test:e2e` green.

## Dependencies

Needs #112 and #113. Blocks #115, #121.

## Implementation prompt

```text
You are working in the `aegis301/shift-planner` repository.
Start from the latest `main`: `git fetch origin && git switch -c feat/route-split origin/main`.
Do not continue on a branch from another issue.

Read these before writing any code, and follow them strictly:
1. `AGENTS.md`, especially **Working an issue**, **Style → Frontend surfaces** and **Testing Expectations**.
2. `docs/rollout/STATE.md`, especially **Traps this project has already hit**.
3. `docs/decisions/0001-desktop-first-workbench.md`.
4. This issue's spec in full: `docs/workbench/issues/06-route-split-workbench-member.md`.

Standing rules that matter most here:
- Business logic lives in backend services. Splitting a page must not move any rule into React.
- `/api/v1/roster-matrix/{id}` and `/api/v1/matrix/{id}` take `team_member_portal=true` on the
  member path and omit it on the planner path (see **Purpose** in `AGENTS.md`). Keep that exact.
- Every user-visible string exists in both dictionaries in `frontend/lib/i18n.ts`.
- Update `README.md`, `CHANGELOG.md`, `AGENTS.md` and `docs/rollout/STATE.md` in the same change.
- Before you finish: `cd frontend && npm run lint && npm run typecheck && npm run build && npm run test && npm run test:e2e`.

Task: split the frontend into a desktop-first workbench and a mobile-first member area, and split
`PlanningWorkspace` accordingly.

1. Confirm the Playwright suite is green on `main`. If not, stop and report.
2. Before moving code, write in the PR description a table of every feature inside
   `PlanningWorkspace.tsx` and which side it goes to (planner, member, shared presentational).
   Use the `planningUi`, `adminUi` and `teamMemberPortalUi` flags to find them. This table is the
   checklist; nothing may be dropped silently.
3. Create the route groups and shells. Move pages. Run the URL check.
4. Split `PlanningWorkspace` following your table, one commit per feature group.
5. Add `/my`, update routing and redirects, add the dual-role switch and the narrow notice.
6. Update Playwright tests and baselines as the spec describes.

Do not change: any API call or payload, the planning status workflow, the solver or swap flows'
behaviour, i18n wording of existing keys.

Stop and report instead of guessing if: a feature in the table is used by both audiences with
different rules you cannot map to "planner", "member" or "shared presentational", or a member
flow depends on planner-only data.

Prove it: walk the acceptance criteria one by one in the PR and name the test, command output or
CI run that proves each.
```
