---
title: "Frontend test harness: Vitest, Testing Library, Playwright and golden screenshots"
labels: frontend, testing
---

## Context

Part of ADR 0001 (`docs/decisions/0001-desktop-first-workbench.md`, decision 3).

The frontend has **no tests at all**. `frontend/package.json` has `lint`, `typecheck` and `build`
scripts and nothing else. CI (`.github/workflows/ci.yml`, job `frontend`) runs those three. Every
later issue in this plan rewrites a large piece of UI: `PlanningWorkspace.tsx` (2,124 lines),
`MatrixEditor.tsx` (2,100), `RosterMatrixEditor.tsx` (1,567). `AGENTS.md` requires that
behaviour-preserving refactors start from a golden snapshot. For the frontend that snapshot does
not exist yet, and there is nothing to take it with.

This issue builds the harness and takes the baseline. It changes no production behaviour.

There is a second gap. The solver fixture (`backend/app/scripts/seed_solver_fixture.py`) builds a
realistic organization with members, groups, templates and history, but creates **no login
accounts** for it. An end-to-end test cannot sign in to it. The default organization has logins
(`seed_admin`, `seed_team_member_users`, `seed_planner_user`) but no realistic planning data.

## Scope

1. **Unit and component tests.** Vitest, `@testing-library/react`, `@testing-library/user-event`,
   `jsdom`. Config in `frontend/vitest.config.ts` with the `@/` alias from `tsconfig.json`.
   Scripts: `npm run test` (single run) and `npm run test:watch`. Seed it with real tests for pure
   modules that later issues will touch:
   - `frontend/lib/i18n.ts`: `t()` interpolation, and a runtime check that both dictionaries have
     the same keys (the type-level check already exists at the bottom of the file).
   - `frontend/lib/planningDates.ts`, `frontend/lib/shiftOverlap.ts`, `frontend/lib/rosterWorkload.ts`,
     `frontend/lib/membershipRouting.ts` (`pathnameCompatibleWithMembership` and
     `membershipDefaultPath` for each role).
2. **E2E seed.** A backend script `backend/app/scripts/seed_e2e.py` that:
   - runs the `comfortable` solver fixture for a fixed month and seed (reuse the service in
     `app/services/solver_fixture.py`, do not shell out),
   - creates three `Account` + `User` memberships in that fixture organization with fixed emails
     (`e2e-admin@example.com`, `e2e-planner@example.com`, `e2e-member@example.com`) and a password
     from `E2E_SEED_PASSWORD` (refuse to run without it),
   - links the planner to every shift group of the fixture (`user_shift_groups`) and the member to
     one existing fixture `TeamMember`,
   - is idempotent (re-running updates passwords and links, does not duplicate),
   - refuses to run against `DEFAULT_ORGANIZATION_ID`, like the fixture script.
   pytest coverage for idempotency and the refusal.
3. **Playwright.** `@playwright/test` in `frontend/`, config `frontend/playwright.config.ts`,
   tests in `frontend/e2e/`. Script `npm run test:e2e`. Base URL from `E2E_BASE_URL` (default
   `http://localhost:18130`, the Compose frontend port). A `globalSetup` signs in each of the three
   roles once through `POST /api/v1/auth/login` and stores `storageState` per role so tests do not
   log in through the UI every time. In the cloud dev container Chromium lives at
   `/opt/pw-browsers`. Do not add a `playwright install` step to scripts; document it for local
   machines in `README.md`.
4. **Flows covered (smoke, not exhaustive):**
   - Planner: open `/planning` for the fixture month and a shift group, switch Wishes, Roster and
     Analysis tabs, assign one roster cell through the picker, see the assignment persist after a
     reload, clear it again.
   - Admin: open `/organization/team`, open one staff-directory row detail, close it.
   - Member: open `/my-planning`, see the Wishes, Roster and My shifts tabs.
   - Everyone: sign out.
5. **Golden screenshots.** `toHaveScreenshot` baselines at 1440x900 for: `/planning` Wishes tab,
   Roster tab, Analysis tab, `/organization/team`, `/hours`; and at 390x844 for `/my-planning`
   and the member dashboard. Mask volatile regions (dates relative to today, generated ids).
   Commit the baselines. These are the baseline #114 onward must either match or justify.
6. **CI.** Extend `.github/workflows/ci.yml`:
   - `frontend` job: add `npm run test`.
   - new `e2e` job, needs `backend` and `frontend`: start Postgres, backend and frontend with
     `docker-compose.yml`, run `alembic upgrade head` (Compose already does), run
     `python -m app.scripts.seed_e2e` in the backend container, install Playwright's Chromium
     (`npx playwright install --with-deps chromium`), run `npm run test:e2e`, upload the
     Playwright report as an artifact on failure.
   Screenshot comparisons must be stable on the CI runner: fix fonts (the app uses the system
   font stack, so pin the runner image and use `maxDiffPixelRatio` of about 0.01), disable
   animations in the test setup.

## Out of scope

- Any change to production components, apart from adding `data-testid` attributes where a stable
  selector does not otherwise exist. Prefer role and label selectors first.
- Testing the solver, swaps or duty activity flows in depth. Later issues add their own tests.

## Acceptance criteria

- [ ] `npm run test` runs Vitest and passes, with tests for the modules listed in scope 1.
- [ ] `python -m app.scripts.seed_e2e` creates the fixture org and three logins, is idempotent, and
      refuses without `E2E_SEED_PASSWORD` and against the default org. pytest proves each.
- [ ] `npm run test:e2e` passes locally against Compose and in the new CI job.
- [ ] Golden screenshots for the listed pages are committed and pass twice in a row in CI
      (re-run the job once to prove stability, and link both runs in the PR).
- [ ] `README.md` documents: running unit tests, running e2e locally (Compose up, seed, install
      Chromium, run), updating screenshot baselines (`npx playwright test --update-snapshots`) and
      when that is allowed (only with a justification in the PR).
- [ ] `AGENTS.md` **Testing Expectations** names the commands.
- [ ] `ruff check app`, `pytest`, `npm run lint`, `npm run typecheck`, `npm run build` green.

## Dependencies

None. Blocks #112, #113, #114, and every later frontend issue.

## Implementation prompt

```text
You are working in the `aegis301/shift-planner` repository.
Start from the latest `main`: `git fetch origin && git switch -c test/frontend-harness origin/main`.
Do not continue on a branch from another issue.

Read these before writing any code, and follow them strictly:
1. `AGENTS.md`, especially **Working an issue**, **Style → Frontend surfaces** and **Testing Expectations**.
2. `docs/rollout/STATE.md`, especially **Decisions already made** and **Traps this project has already hit**.
3. `docs/decisions/0001-desktop-first-workbench.md`.
4. This issue's spec in full: `docs/workbench/issues/02-frontend-test-harness.md`.

Standing rules that matter most here:
- Business logic lives in typed service functions under `backend/app/services/`.
- Every user-visible string exists in both dictionaries in `frontend/lib/i18n.ts`.
- Update `README.md`, `CHANGELOG.md`, `AGENTS.md` and `docs/rollout/STATE.md` in the same change.
- Before you finish: `cd backend && ruff check app && pytest`, and
  `cd frontend && npm run lint && npm run typecheck && npm run build && npm run test && npm run test:e2e`.

Task: add the frontend test harness and take the golden baseline. This is a testing change. It
must not change what any page does or looks like.

1. Add Vitest + Testing Library + jsdom with the `@/` alias. Write the unit tests listed in scope 1
   of the spec. Read each module before testing it and test its real behaviour, including edge
   cases you find in the code (for example the applicant and account-session branches in
   `membershipRouting.ts`).
2. Write `backend/app/scripts/seed_e2e.py` on top of the existing fixture service in
   `backend/app/services/solver_fixture.py` and the account and membership services
   (`backend/app/services/registration.py`, `backend/app/services/users.py`). Read how
   `seed_planner_user.py` links planner shift groups and copy that approach. Add pytest coverage.
3. Add Playwright with per-role `storageState` from a `globalSetup` that calls the login API.
4. Write the smoke flows and the golden screenshots from scope 4 and 5. Use role and label
   selectors first. Add `data-testid` only where nothing else is stable, and list each one you
   added in the PR.
5. Add the CI changes from scope 6. Run the e2e job twice to prove the screenshots are stable.
6. Document everything in `README.md` and `AGENTS.md`.

Do not change: component behaviour, styling, API shapes, or any backend service other than
adding the seed script.

Stop and report instead of guessing if: a page renders differently on each run in a way masking
cannot fix (that is a real nondeterminism bug to file), or the fixture needs a change under
`app/services/` to be usable for login.

Prove it: walk the acceptance criteria one by one in the PR and name the test, command output or
CI run that proves each.
```
