---
title: "Generate frontend API types from the backend OpenAPI schema"
labels: frontend, backend, architecture
---

## Context

Part of ADR 0001 (`docs/decisions/0001-desktop-first-workbench.md`, decision 3). A second client
(the Expo member app, #122) is coming. With two clients, hand-written payload types drift
immediately.

Today:

- FastAPI already builds a complete OpenAPI schema: `app.openapi()` returns 135 paths and 206
  component schemas (`backend/app/main.py`, `FastAPI(title="Shift Planner API", version="0.1.0")`).
- The frontend ignores it. Payload types are written by hand in `frontend/lib/*.ts` (67 exported
  types, for example in `lib/solver.ts`, `lib/shiftSwaps.ts`, `lib/fairness.ts`,
  `lib/dashboard.ts`, `lib/hoursLedger.ts`, `lib/dutyActivity.ts`) and in about 35 component files
  (for example `RosterMatrix` in `components/RosterMatrixEditor.tsx:127`, `MeUser` and
  `SessionMe` in `components/LocaleProvider.tsx`).
- `frontend/lib/api.ts` has one untyped `apiFetch<T>(path, init)`. The caller picks `T`, so a
  wrong `T` compiles.
- About 27 routes have no `response_model`. Most are file exports (CSV, XLSX, PDF) or `204`
  deletes, which is fine. These are not fine and need a response model so the schema describes
  them:
  - `GET /api/v1/planning-periods/{id}/versions/suggest` (`api/v1/planning.py`)
  - the four untyped `@router.get(` blocks in `api/v1/planning.py` without a `response_model`
    (read them and decide per route)
  - `POST /api/v1/time-entries/derive` (`api/v1/time_entries.py`)
  - `POST /api/v1/roster-matrix/assignments/clear` (`api/v1/roster_matrix.py`)
  - `POST /api/v1/matrix/{id}/cells/clear` (`api/v1/matrix.py`)
  - `POST /api/v1/auth/logout` (`api/v1/auth.py`)
  - the `POST` in `api/v1/work_time_consents.py` without a model
  Find the full list with
  `grep -rn "@router\.\(get\|post\|put\|patch\|delete\)" backend/app/api/v1 | grep -v response_model`.

## Decision for this issue

- **Tooling:** `openapi-typescript` generates `frontend/lib/api/schema.d.ts`. `openapi-fetch`
  provides the typed client. Both are small, have no runtime code generation, and work in React
  Native too, which matters for #121.
- **Source of truth:** the schema is exported from the app object, not fetched from a running
  server: `python -m app.scripts.export_openapi > frontend/lib/api/openapi.json`. The JSON is
  committed so the frontend can build without Python.
- **Drift check:** CI regenerates both files and fails on any diff.
- **Operation ids:** FastAPI's default operation ids are long and unstable
  (`get_roster_matrix_api_v1_roster_matrix__planning_period_id__get`). Set
  `generate_unique_id_function` on the app to `f"{route.tags[0]}_{route.name}"` so ids are
  readable and stable. Check for collisions in a test.
- **Where it lives:** `frontend/lib/api/` for now. #121 moves it into `packages/api-client`.

## Scope

1. `backend/app/scripts/export_openapi.py` prints `app.openapi()` as sorted, indented JSON
   (stable output, so diffs are readable).
2. `generate_unique_id_function` on the FastAPI app, and a pytest that asserts all operation ids
   are unique and match `^[a-z_]+$`.
3. Add `response_model` (or `responses=` for file downloads) to every JSON route that lacks one.
   Where a route returns an ad-hoc `dict`, create a Pydantic schema in `app/schemas/domain.py`.
   No behaviour change: existing tests must pass unchanged.
4. `frontend/lib/api/openapi.json`, `frontend/lib/api/schema.d.ts` (generated, with a header
   comment "generated, do not edit"), and `frontend/lib/api/client.ts` that creates an
   `openapi-fetch` client with `credentials: "include"` and the same base URL logic as
   `lib/api.ts` (`NEXT_PUBLIC_API_BASE_URL`, empty string means same origin).
5. Keep `apiFetch` working, but make its error handling shared with the new client so `ApiError`
   stays the one error type callers catch. Add a `lib/api/types.ts` that re-exports friendly
   names: `export type RosterMatrix = components["schemas"]["RosterMatrixRead"]` and so on.
6. **Replace hand-written payload types** in `frontend/lib/*.ts` and in components with aliases
   from `lib/api/types.ts`. Where the hand-written type differs from the schema, the schema wins,
   and you fix the call site. List every such difference in the PR, because each one is either a
   latent bug or a missing backend field.
   Types that are UI-only (view models, form state) stay hand-written.
7. Scripts in `frontend/package.json`: `api:generate` (runs the Python export through
   `docker compose exec` or a local venv, then `openapi-typescript`) and `api:check` (regenerate
   into a temp dir and diff). Document both in `README.md`.
8. CI: in the `backend` job, run the export and upload `openapi.json` as an artifact. In the
   `frontend` job, download it, run `openapi-typescript`, and `git diff --exit-code
   frontend/lib/api/`. Simpler alternative if artifacts are awkward: one job that installs both
   Python and Node. Pick one and explain why in the PR.
9. MCP: no change needed, but check that `mcp-server` tests still pass because they import the
   schemas you touched.

## Out of scope

- Migrating call sites from `apiFetch` to the typed client. New code uses the typed client; old
  call sites move when #113 rewrites the data loading. Do not do a mass rewrite here.
- npm workspaces or packages (#121).
- Changing any API behaviour or URL.

## Acceptance criteria

- [ ] `python -m app.scripts.export_openapi` prints a stable schema (same output twice).
- [ ] Every JSON route has a response model. A pytest walks `app.routes` and fails if a route
      without a model returns JSON (allow-list file downloads and `204`).
- [ ] Operation ids are unique and readable. Test.
- [ ] `frontend/lib/api/schema.d.ts` is generated and committed. `npm run api:check` passes and
      fails when a backend schema changes without regeneration (show both in the PR).
- [ ] No hand-written type in `frontend/lib/*.ts` or `frontend/components/**` mirrors a backend
      schema any more. The PR lists each replaced type and each mismatch found.
- [ ] CI fails on drift.
- [ ] `ruff check app`, `pytest`, MCP tests, `npm run lint`, `npm run typecheck`, `npm run build`,
      `npm run test` green.

## Dependencies

None. Blocks #113, #120, #121.

## Implementation prompt

```text
You are working in the `aegis301/shift-planner` repository.
Start from the latest `main`: `git fetch origin && git switch -c feat/generated-api-types origin/main`.
Do not continue on a branch from another issue.

Read these before writing any code, and follow them strictly:
1. `AGENTS.md`, especially **Working an issue**, **Style → Frontend surfaces** and **Testing Expectations**.
2. `docs/rollout/STATE.md`, especially **Decisions already made** and **Traps this project has already hit**.
3. `docs/decisions/0001-desktop-first-workbench.md`.
4. This issue's spec in full: `docs/workbench/issues/03-generated-api-types.md`.

Standing rules that matter most here:
- Business logic lives in typed service functions under `backend/app/services/`, never in route
  handlers or React components.
- Every capability is reachable from the web UI, REST and MCP (`mcp-server/mcp_app/server.py`).
- Update `README.md`, `CHANGELOG.md`, `AGENTS.md` and `docs/rollout/STATE.md` in the same change.
- Before you finish: `cd backend && ruff check app && pytest`, `cd mcp-server && pytest`, and
  `cd frontend && npm run lint && npm run typecheck && npm run build && npm run test`.

Task: generate the frontend's API types from the backend OpenAPI schema and remove the
hand-written copies.

1. Backend first: stable operation ids, the export script, and response models on every JSON route
   that lacks one. Existing tests must pass unchanged. Commit this step on its own.
2. Generate `frontend/lib/api/openapi.json` and `schema.d.ts`, add the `openapi-fetch` client and
   `lib/api/types.ts`. Share error handling with `lib/api.ts` so `ApiError` stays the single error
   type.
3. Replace hand-written payload types, module by module, one commit per module. After each
   module run `npm run typecheck`. When the generated type disagrees with the hand-written one,
   fix the call site and note the mismatch; do not loosen the generated type with `as` or `any`.
4. Add `api:generate` / `api:check` and the CI drift check.
5. Update `README.md` (how to regenerate, when to regenerate) and `AGENTS.md` (the new rule is
   already in **Style → Frontend foundations**; make the commands concrete).

Do not change: any URL, any response shape, `apiFetch` call sites beyond their type parameter,
any component's rendering.

Stop and report instead of guessing if: the generated schema reveals that a frontend page reads a
field the backend never sends, or sends a field the backend ignores. Those are bugs; list them
and ask before fixing anything that changes behaviour.

Prove it: walk the acceptance criteria one by one in the PR and name the test, command output or
CI run that proves each.
```
