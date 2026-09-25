---
title: "Member app scaffold (Expo): sign-in, home, my duties, i18n and CI"
labels: frontend, architecture
---

## Context

Part of ADR 0001 (`docs/decisions/0001-desktop-first-workbench.md`, decision 4). This issue
creates the native member app with the smallest useful slice: a member can sign in and see their
duties. Everything else builds on it (#123, #124, #125).

What the app can rely on when this starts:

- Bearer tokens with refresh and device sessions (#119): `POST /api/v1/auth/token`,
  `POST /api/v1/auth/token/refresh`, `POST /api/v1/auth/token/revoke`,
  `POST /api/v1/auth/me/active-organization` returning a new access token.
- The member API (#120): `GET /api/v1/me/home`, `GET /api/v1/me/duties?from=&to=` and the rest
  of `/api/v1/me`. Every route returns 403 `no_linked_team_member` when the user has no linked
  member.
- The npm workspace (#121): `@shift-planner/api-client` (with the `bearer` auth strategy),
  `@shift-planner/i18n` (DE/EN JSON dictionaries, `t()`), `@shift-planner/domain` (pure helpers
  including `orgTime`). Workspaces listed in the root `package.json` already include `mobile`.
- Login semantics (`AGENTS.md`, **Purpose**): one account can have several memberships; login
  picks one deterministically; an account without membership gets an account session and must
  onboard on the web. Applicants have no member capabilities until approved.

## Decision for this issue

- **Location** `mobile/` in the repository, package name `@shift-planner/mobile`.
- **Stack**: current stable Expo SDK with **Expo Router** (file-based routes), TypeScript strict,
  TanStack Query (same query-key conventions as the web: `mobile/lib/queryKeys.ts`),
  `expo-secure-store` for the refresh token, access token in memory only, `expo-localization` for
  the default locale (DE if the device language is German, otherwise EN; user can override in
  settings), `jest-expo` with React Native Testing Library for tests.
- **Auth flow**: sign-in screen (email, password) calls `POST /auth/token` with
  `device_name` from `expo-device` and `platform` from `Platform.OS`. The api-client's bearer
  strategy refreshes on 401 once, single-flight (concurrent requests wait for one refresh), and
  signs out on refresh failure. Sign-out calls `/auth/token/revoke` and wipes secure storage and the
  query cache.
- **Session outcomes after sign-in**, each with its own screen:
  - `user` session with `team_member_portal` capability: the app.
  - `user` session without a linked member (planner or admin only): a screen saying the app is for
    team members, with a button that opens the web workbench URL in the browser, and sign-out.
  - `account` session (no membership) or `applicant`: a screen that explains onboarding happens on
    the web, with a link, and sign-out.
- **Organization switch**: if the user has several memberships, the settings screen lists them and
  switches through `POST /auth/me/active-organization`, then clears the query cache.
- **Screens in this issue**: Sign in; Home (`/me/home`: next duties, pending swap actions as
  read-only rows, next wishes deadline); Duties (`/me/duties` for today minus 7 days to plus
  60 days, grouped by week, pull to refresh); Duty detail (times in the org time zone, template,
  group, plan status); Settings (language, organization, signed-in account, sign out, app version).
  Tabs: Home, Duties, Settings. Wishes and Swaps tabs arrive in #124.
- **Configuration**: `EXPO_PUBLIC_API_BASE_URL` (no default pointing at production). Document
  running against the local Compose backend from a phone on the same network and from the iOS
  simulator or Android emulator (`10.0.2.2`).
- **Build and release**: `eas.json` with `development`, `preview` and `production` profiles. No
  store submission in this issue. The bundle identifier and Android package name are **not
  decided**; the agent must ask the owner before choosing them (see the prompt).
- **Design**: mobile-first rules from `AGENTS.md` **Style → Frontend surfaces**: 44 pt touch
  targets, one primary action per screen, dynamic type respected, both light and dark system
  appearance (a small token set in `mobile/theme.ts` mirroring the web tokens from #112).
- **Accessibility**: every interactive element has an accessibility label from the dictionaries.

## Scope

1. Create the Expo app in `mobile/` inside the workspace; make sure `npm ci` at the root installs
   it and Metro resolves the shared packages.
2. Auth, session outcome screens, organization switch.
3. Home, Duties, Duty detail, Settings.
4. Add the app's strings to `@shift-planner/i18n` (both languages).
5. Tests: api-client bearer strategy (refresh single-flight, sign-out on failure) in the package;
   screen tests for sign-in errors, the three session outcomes, and the duties list grouping.
6. CI: a `mobile` job that runs `npm ci`, `npm run typecheck --workspace mobile`,
   `npm run lint --workspace mobile`, `npm run test --workspace mobile`. No native builds in CI.
7. Docs: `mobile/README.md` (run, configure, test, EAS profiles), root `README.md` section,
   `AGENTS.md` (the app exists, where it lives, what it may and may not contain: member features
   only, no business logic, all data through `/api/v1/me` and auth endpoints).

## Out of scope

- Offline capture (#123), wishes, swaps, hours, calendar (#124), push (#125).
- Any planner or admin feature. Ever, per ADR 0001.
- Store listings, signing credentials, submission.

## Acceptance criteria

- [ ] `mobile/` builds in Expo Go or a development build against the local Compose backend
      (screen recording or screenshots in the PR for iOS or Android).
- [ ] Sign-in, the three session outcomes, organization switch and sign-out work; sign-out revokes
      the device session on the server (verify with `GET /api/v1/auth/me/devices` from the web).
- [ ] Refresh is single-flight and signs out on failure (tests).
- [ ] Home and Duties render real data from `/api/v1/me`; times are shown in the organization's
      time zone regardless of the device time zone (test with a mocked device zone).
- [ ] All strings come from `@shift-planner/i18n`; parity check passes.
- [ ] The `mobile` CI job passes.
- [ ] Docs updated as listed.

## Dependencies

Needs #119, #120, #121. Blocks #123, #124, #125.

## Implementation prompt

```text
You are working in the `aegis301/shift-planner` repository.
Start from the latest `main`: `git fetch origin && git switch -c feat/mobile-scaffold origin/main`.
Do not continue on a branch from another issue.

Read these before writing any code, and follow them strictly:
1. `AGENTS.md`, especially **Purpose** (accounts, memberships, capabilities), **Style → Frontend surfaces** and **Testing Expectations**.
2. `docs/rollout/STATE.md`, especially **Traps this project has already hit**.
3. `docs/decisions/0001-desktop-first-workbench.md` (the app is member-only, forever).
4. This issue's spec in full: `docs/workbench/issues/14-expo-member-app-scaffold.md`.
5. The READMEs of `packages/api-client`, `packages/i18n` and `packages/domain`.

Standing rules that matter most here:
- The app contains no business logic. It reads and writes through `/api/v1/me/...` and the auth
  endpoints only. If a screen needs data those endpoints do not provide, that is a backend issue
  to report, not something to compute on the device.
- Every user-visible string lives in `@shift-planner/i18n` in both German and English.
- Update `README.md`, `CHANGELOG.md`, `PLAN.md`, `AGENTS.md` and `docs/rollout/STATE.md` in the same change.
- Before you finish: from the root `npm ci`, then typecheck, lint and test for `mobile` and the
  packages, and the web frontend's lint, typecheck and build (the workspace must not break it).

Task: create the Expo member app with sign-in, session outcome screens, home, duties, duty detail
and settings, plus CI.

1. BEFORE creating the project, ask the repository owner for the iOS bundle identifier, the
   Android package name and the display name. Do not invent them. Use placeholders only if the
   owner says so, and mark them clearly in `app.config.ts`.
2. Create the app with Expo Router in `mobile/`, wired into the npm workspace. Prove that Metro
   resolves `@shift-planner/*` before writing screens.
3. Implement the bearer strategy usage, secure storage and sign-in, then the session outcome
   screens, then the organization switch.
4. Implement Home, Duties, Duty detail and Settings on TanStack Query.
5. Add tests and the CI job.
6. Write the docs.

Do not change: backend code, the web frontend (except what the workspace requires), shared
package APIs (extend them only in a backwards-compatible way, with tests).

Stop and report instead of guessing if: Metro cannot resolve the workspace packages without
restructuring them, or an endpoint returns data in a shape the screens cannot use without
client-side business logic.

Prove it: walk the acceptance criteria one by one in the PR and name the test, screenshot or CI
run that proves each.
```
