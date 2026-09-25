---
title: "npm workspace with shared packages: api-client, i18n, domain"
labels: frontend, architecture, chore
---

## Context

Part of ADR 0001 (`docs/decisions/0001-desktop-first-workbench.md`, decision 4). The Expo app
(#122) must share the generated API types, the DE/EN dictionaries and pure domain helpers with
the web frontend. Copying them would repeat the drift problem #111 solved. This issue creates the
workspace and moves shared code into packages, with **no behaviour change** in the web app.

What exists on `main`:

- `frontend/` is a standalone npm project (`frontend/package.json`, `frontend/package-lock.json`,
  `frontend/.npmrc` with fetch retry settings, `frontend/.dockerignore`). There is no root
  `package.json`.
- Docker: `frontend/Dockerfile` (dev) and `frontend/Dockerfile.prod` both assume the build context
  is `./frontend` (`COPY package.json package-lock.json* ./`, `COPY . .`).
  `docker-compose.yml` builds with `context: ./frontend`, mounts `./frontend:/app` plus a named
  `frontend_node_modules` volume, and runs `npm install && npm run dev`.
  `docker-compose.prod.yml` builds with `context: ./frontend` (around line 74).
- CI (`.github/workflows/ci.yml`): the `frontend` job uses `working-directory: frontend` and
  `cache-dependency-path: frontend/package-lock.json`. `container-smoke` builds from
  `docker-compose.prod.yml`. From #110 there is also an `e2e` job.
- `deploy/README.md` describes the stack and the CI jobs.
- Shared code candidates on `main` (after #109 and #111):
  - `frontend/lib/api/` (generated `openapi.json`, `schema.d.ts`, `client.ts`, `types.ts`)
  - `frontend/lib/i18n.ts` (2,346 lines: `dictionaries.de`, `dictionaries.en`, the
    `I18nKeysMatch` parity type, `TranslationKey`, `t()`)
  - pure helpers: `frontend/lib/shiftDisplay.ts`, `shiftOverlap.ts`, `planningDates.ts`,
    `teamMemberDisplay.ts`, `orgTime.ts` (from #109), the pure parts of `dutyActivity.ts` and
    `shiftSwaps.ts`

## Decision for this issue

- **npm workspaces** (the repo already uses npm; Expo SDK 52 and later detect npm workspaces
  without extra Metro configuration). Root `package.json` with
  `"workspaces": ["frontend", "packages/*", "mobile"]` and one root `package-lock.json`.
  `mobile/` does not exist yet; #122 creates it. **`frontend/` stays where it is** to avoid
  churning every path in `AGENTS.md`, CI and deploy docs.
- Packages, all TypeScript source consumed directly (no build step), `"private": true`:
  - `packages/api-client` (`@shift-planner/api-client`): `openapi.json`, generated
    `schema.d.ts`, friendly type aliases, and `createApiClient({ baseUrl, auth })` where `auth` is
    either `{ kind: "cookie" }` (web: `credentials: "include"`) or
    `{ kind: "bearer", getAccessToken, refresh, onSignedOut }` (mobile). Shared `ApiError`.
    The `api:generate` / `api:check` scripts from #111 move here.
  - `packages/i18n` (`@shift-planner/i18n`): `de.json`, `en.json`, `t()`, `TranslationKey`, the
    compile-time parity check and a Vitest runtime parity test. Platform-neutral: no React.
  - `packages/domain` (`@shift-planner/domain`): pure functions only, no DOM, no Next.js, no React
    Native imports. Enforced with an ESLint `no-restricted-imports` rule in the package.
- `frontend/lib/i18n.ts` and `frontend/lib/api/*` become thin re-exports so existing imports keep
  working. New code imports from the packages.
- Next.js: `transpilePackages: ["@shift-planner/api-client", "@shift-planner/i18n",
  "@shift-planner/domain"]` in `frontend/next.config.mjs`.
- Docker: build context becomes the **repo root** for the frontend images, with a root
  `.dockerignore` that excludes `backend/`, `mcp-server/`, `mobile/`, `.git`, and every
  `node_modules`. Dockerfiles copy the root manifest, the lockfile, `frontend/package.json` and
  `packages/*/package.json` first (layer cache), run `npm ci --workspace frontend
  --include-workspace-root`, then copy sources. Keep the retry loop and `.npmrc` settings (move
  `.npmrc` to the root).

## Scope

1. Root `package.json`, root lockfile (delete `frontend/package-lock.json`), root `.npmrc`,
   root `.dockerignore`.
2. The three packages with their `package.json`, `tsconfig.json` (extending a root
   `tsconfig.base.json`), Vitest tests (move the existing unit tests for moved modules along with
   them).
3. Re-export shims in `frontend/lib/`.
4. Docker: update `frontend/Dockerfile`, `frontend/Dockerfile.prod`, `docker-compose.yml`
   (context, volumes: mount the repo root or `./frontend` plus `./packages`, keep a named
   `node_modules` volume) and `docker-compose.prod.yml`.
5. CI: install from the root (`npm ci`), run `npm run lint --workspace frontend` and so on, run
   package tests (`npm run test --workspaces --if-present`), cache on the root lockfile. The
   `container-smoke` and `e2e` jobs keep working.
6. Docs: `README.md` (install and scripts from the root), `deploy/README.md` (build context),
   `AGENTS.md` (paths of i18n, API types and domain helpers; the i18n parity rule now points at
   `packages/i18n`).

## Out of scope

- Creating `mobile/` (#122).
- Moving `frontend/` to `apps/web`.
- Any change to what the web app does or looks like.

## Acceptance criteria

- [ ] `npm ci` at the root installs everything; `npm run build --workspace frontend` works.
- [ ] The three packages exist, contain the moved code, and have passing tests; `packages/domain`
      fails lint if it imports `react`, `next`, `react-native` or touches `window`.
- [ ] `docker compose up` (dev) and `docker compose -f docker-compose.prod.yml up --build` both
      start the frontend; `container-smoke` passes.
- [ ] All frontend Playwright tests and golden screenshots pass unchanged.
- [ ] `grep -rn "frontend/package-lock.json" .github docker-compose*.yml frontend/Dockerfile*` is
      empty.
- [ ] Docs updated as listed.
- [ ] `npm run lint`, `npm run typecheck`, `npm run build`, `npm run test`, `npm run test:e2e`
      green (from the root or per workspace, as documented).

## Dependencies

Needs #111 and #114 (so shared code is already separated from page code). Should follow
#109 so `orgTime.ts` moves once. Blocks #122.

## Implementation prompt

```text
You are working in the `aegis301/shift-planner` repository.
Start from the latest `main`: `git fetch origin && git switch -c chore/js-workspace origin/main`.
Do not continue on a branch from another issue.

Read these before writing any code, and follow them strictly:
1. `AGENTS.md`, especially **Working an issue**, **Internationalization**, **Style → Frontend surfaces** and **Testing Expectations**.
2. `docs/rollout/STATE.md`, especially **Traps this project has already hit**.
3. `docs/decisions/0001-desktop-first-workbench.md`.
4. `deploy/README.md`.
5. This issue's spec in full: `docs/workbench/issues/13-js-workspace-packages.md`.

Standing rules that matter most here:
- This is a behaviour-preserving restructuring. The web app must look and behave exactly the same.
- German and English dictionaries must keep identical keys (compile-time and runtime check).
- Docker startup stays the baseline development path.
- Update `README.md`, `deploy/README.md`, `CHANGELOG.md`, `AGENTS.md` and `docs/rollout/STATE.md` in the same change.
- Before you finish: from the root `npm ci`, then lint, typecheck, build, unit tests and e2e for
  the frontend workspace, unit tests for every package, and a local
  `docker compose -f docker-compose.prod.yml up --build frontend backend postgres`.

Task: introduce an npm workspace with `packages/api-client`, `packages/i18n` and `packages/domain`,
move shared code into them, and keep the web app, Docker and CI working unchanged.

1. Confirm the full frontend test suite and `container-smoke` are green on `main`. If not, stop and
   report.
2. Create the root workspace and move the lockfile. Run the frontend build before moving any code.
3. Move `lib/api` into `packages/api-client`, add the auth strategies, leave a re-export shim.
   Build and test.
4. Move the dictionaries into JSON in `packages/i18n`. Generate the JSON from the current
   `dictionaries` object with a one-off script (do not retype strings) and keep the parity check.
   Build and test.
5. Move the pure helpers into `packages/domain`, one module per commit, with their tests and the
   lint restriction.
6. Update Docker, Compose, CI and docs. Prove `container-smoke` and `e2e` pass in the PR.

Do not change: any component, any page, any user-visible string, backend code.

Stop and report instead of guessing if: a helper you planned to move turns out to depend on the
DOM or Next.js, or the Docker image size grows by more than 20 % (paste before and after sizes).

Prove it: walk the acceptance criteria one by one in the PR and name the test, command output or
CI run that proves each.
```
