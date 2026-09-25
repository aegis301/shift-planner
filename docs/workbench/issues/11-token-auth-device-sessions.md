---
title: "Bearer token authentication with refresh tokens and revocable device sessions"
labels: backend, schema, architecture, frontend
---

## Context

Part of ADR 0001 (`docs/decisions/0001-desktop-first-workbench.md`, decision 5). The Expo member
app (#122) cannot use the web session cookie well: cookies in React Native are fragile, cannot
be scoped per device, and cannot be revoked one device at a time.

What exists on `main`:

- One cookie, `shift_planner_session`, set in `backend/app/api/v1/auth.py`
  (`_set_user_session_cookie`, `_set_account_session_cookie`; `httponly`, `samesite="lax"`,
  `secure` from `SESSION_COOKIE_SECURE`, optional `SESSION_COOKIE_DOMAIN`).
- Its value is an `itsdangerous` signed payload (`backend/app/core/security.py`,
  `create_user_session_token` / `create_account_session_token`) with `typ` `user` (a `User.id`,
  one organization membership) or `account` (an `Account.id` with no membership yet), `sub`,
  `iat`, and `SESSION_MAX_AGE_SECONDS` of 7 days. There is no server-side session record, so a
  session cannot be revoked before it expires. `AGENTS.md` states this: "Existing sessions stay
  valid until cookie expiry" after a password change.
- `backend/app/api/deps.py`, `get_current_session_holder`, reads only the cookie. Every
  permission dependency (`get_current_user`, `get_current_account_session`,
  `get_current_admin`, `get_current_planning_user`, ...) builds on it.
- Organization switching (`POST /api/v1/auth/me/active-organization`) and onboarding rotate the
  cookie to a different `User.id`.
- MCP authenticates with one shared `MCP_ADMIN_TOKEN` and no user. That is a known weakness
  (not fixed here), but this design should make per-user MCP tokens a small follow-up.

## Decision for this issue

- **Device sessions** are stored server-side: table `auth_device_sessions` with `id`,
  `account_id`, `user_id` (active membership, nullable for account-only sessions), `name`
  (for example "Pixel 8"), `platform` (`ios`, `android`, `web`, `other`), `created_at`,
  `last_used_at`, `expires_at`, `revoked_at`, `revoked_reason`.
- **Refresh token history**: table `auth_refresh_tokens` with `id`, `device_session_id` (FK),
  `token_hash` (SHA-256, unique), `issued_at`, `rotated_at` (null for the current token). This is
  the only place refresh token hashes live. Exactly one unrotated row per active session (partial
  unique index on `device_session_id WHERE rotated_at IS NULL`). Rotated rows are kept until the
  device session expires, as tombstones for reuse detection.
- **Access tokens** are short-lived `itsdangerous` signed payloads with `typ` `access`,
  `sid` (device session id), `sub` and `kind` (`user` or `account`), `iat`, lifetime 15 minutes
  (`ACCESS_TOKEN_TTL_SECONDS`). Signed with a separate salt from the cookie so a cookie value can
  never be used as a bearer token and the other way round.
- **Refresh tokens** have the form `<device_session_id>.<secret>`, where the secret is 32 random
  bytes, URL-safe base64. They are returned once and only the hash is stored. Lifetime 60 days
  sliding (`REFRESH_TOKEN_TTL_DAYS`). Every refresh **rotates** the token: the presented row gets
  `rotated_at`, a new row is issued.
- **Reuse detection** works even when an attacker refreshes first. The embedded session id finds the
  device session, and the hash lookup in `auth_refresh_tokens` decides:
  - hash is the session's current, unrotated token: rotate normally;
  - hash is a **rotated** token of that session: this is reuse, so revoke the whole device session
    (`revoked_reason = "refresh_reuse"`). This also catches the legitimate client presenting its
    old token after an attacker rotated it, which kills the attacker's new token too;
  - hash is unknown: `401`, and do **not** revoke, so a guessed or malformed token cannot sign
    someone else out.
  A single-hash design cannot do this: after the attacker rotates, the legitimate client's token
  just looks unknown and the attacker keeps a valid session.
- **Every request with a bearer token** checks that its device session is not revoked. That is
  one indexed lookup next to the existing `User` lookup and gives immediate revocation.
- `get_current_session_holder` accepts `Authorization: Bearer <access token>` **or** the cookie.
  If both are present, the bearer token wins. Everything built on it keeps working unchanged.
- The cookie flow for the web stays exactly as it is.
- **Revocation events**: changing one's password, an admin password reset
  (`POST /api/v1/organization/users/{id}/reset-password`), deleting the account and removing a
  membership revoke every device session of the affected account (or of that membership).
  Update the `AGENTS.md` sentence about sessions staying valid.

## Endpoints

- `POST /api/v1/auth/token` with `{ email, password, device_name, platform }` returns
  `{ access_token, refresh_token, token_type: "bearer", expires_in, session: <same union as
  login: AccountSessionRead | UserRead> }`. Membership selection is the same deterministic rule as
  `POST /api/v1/auth/login` (organization slug, then `users.id`).
- `POST /api/v1/auth/token/refresh` with `{ refresh_token }` returns a new pair.
- `POST /api/v1/auth/token/revoke` (bearer) revokes the calling device session.
- `GET /api/v1/auth/me/devices` lists the account's device sessions (current one flagged).
  `DELETE /api/v1/auth/me/devices/{id}` revokes one.
- `POST /api/v1/auth/me/active-organization` with a bearer token updates the device session's
  `user_id` and returns a new access token in the body (the cookie flow is unchanged).
- Onboarding (`/api/v1/auth/me/onboarding/*`) with an account bearer token updates the device
  session to the new `User.id` and returns a new access token, mirroring the cookie rotation.
- `/settings` (web) gets a "Signed-in devices" card listing device sessions with revoke buttons.

Business logic lives in `backend/app/services/device_sessions.py`. Route handlers only translate.

## Scope

- Model, Alembic migration, service, endpoints, dependency change, revocation hooks, settings card
  (both dictionaries), config values with defaults in `backend/app/core/config.py` and
  `.env.example`.
- pytest: token issue and use; refresh rotation; reuse detection revokes the session, including
  the case where the attacker refreshes first and the legitimate client then presents its old
  token; an unknown token with a valid session id returns 401 without revoking; expiry;
  revoked session rejected immediately; password change, admin reset, account deletion and
  membership removal revoke; bearer wins over cookie; cookie value rejected as bearer and the other
  way round; org switch with bearer; onboarding with account bearer; every existing auth test
  passes unchanged.
- CORS: bearer requests from a native app do not need CORS. Do not widen `BACKEND_CORS_ORIGINS`.
- Brute-force protection on `POST /api/v1/auth/token`: reuse whatever the login route has. If it
  has none, add a note to the PR and do not build rate limiting here.

## Out of scope

- Per-user MCP authentication (follow-up; name it in the PR). The swap notification design
  (#101, `docs/rollout/swap-notifications-design.md`) lists "MCP has no membership identity" as the
  blocker for recipient-scoped notification reads over MCP. Device sessions from this issue are the
  intended basis for that follow-up, so keep `services/device_sessions.py` free of cookie or HTTP
  assumptions that would stop an MCP personal access token from reusing it.
- OAuth or SSO providers.
- Push token registration (#125).
- Any change to how the web frontend authenticates.

## Acceptance criteria

- [ ] All endpoints above exist with pytest coverage for every scenario in the scope list.
- [ ] Refresh tokens are stored only as hashes (assert the raw token never reaches the database).
- [ ] Revoking a device takes effect on the next request (test).
- [ ] Existing auth, onboarding and organization tests pass without modification.
- [ ] Migration verified against Postgres (paste the run).
- [ ] `AGENTS.md` **Purpose** and **Password recovery** paragraphs describe bearer tokens and the
      new revocation behaviour; `README.md` documents the token flow with a `curl` example.
- [ ] MCP resource or tool: none required. State in the PR why (device sessions are personal
      security data and the MCP token is not a person).
- [ ] `ruff check app`, `pytest`, MCP tests, `npm run lint`, `npm run typecheck`, `npm run build`
      green.

## Dependencies

None. Blocks #122 and #125.

## Implementation prompt

```text
You are working in the `aegis301/shift-planner` repository.
Start from the latest `main`: `git fetch origin && git switch -c feat/token-auth origin/main`.
Do not continue on a branch from another issue.

Read these before writing any code, and follow them strictly:
1. `AGENTS.md`, especially **Purpose** (sessions, memberships, onboarding), **Password recovery**, **Working an issue** and **Testing Expectations**.
2. `docs/rollout/STATE.md`, especially **Traps this project has already hit**.
3. `docs/decisions/0001-desktop-first-workbench.md`.
4. This issue's spec in full: `docs/workbench/issues/11-token-auth-device-sessions.md`.

Standing rules that matter most here:
- Business logic lives in typed service functions under `backend/app/services/`, never in route
  handlers.
- Schema changes ship with a forward-only Alembic migration. `pytest` never runs Alembic; verify
  the migration by hand against Postgres and paste the run in the PR.
- Every user-visible string exists in both dictionaries in `frontend/lib/i18n.ts`.
- Update `README.md`, `CHANGELOG.md`, `PLAN.md`, `AGENTS.md`, `.env.example` and
  `docs/rollout/STATE.md` in the same change.
- Before you finish: `cd backend && ruff check app && pytest`, `cd mcp-server && pytest`,
  `cd frontend && npm run lint && npm run typecheck && npm run build`.

Task: add bearer token authentication with rotating refresh tokens and revocable device sessions,
next to the existing web cookie.

1. Read `backend/app/core/security.py`, `backend/app/api/deps.py`, `backend/app/api/v1/auth.py`
   and `backend/app/services/users.py` end to end. Write down every place a session is created,
   rotated or ended; each needs a bearer equivalent or a revocation hook.
2. Before changing production code, run the existing auth tests and note their count; they must
   all pass unchanged at the end.
3. Add the model, migration and `services/device_sessions.py` with unit tests.
4. Extend `get_current_session_holder` for bearer tokens.
5. Add the endpoints, then the revocation hooks, then the settings card.
6. Verify the migration on Postgres.

Do not change: cookie names, cookie attributes, the login route's response, any permission
dependency's behaviour for cookie clients, MCP authentication.

Stop and report instead of guessing if: a flow rotates the cookie in a way that has no clean
bearer equivalent, or keeping cookie behaviour identical conflicts with the dependency change.

Prove it: walk the acceptance criteria one by one in the PR and name the test or pasted run that
proves each.
```
