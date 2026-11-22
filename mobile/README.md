# Shift Planner member app

The native member app (Expo SDK 58, Expo Router, React Native 0.88, React 19.3). It is a member client only:
sign in, home, my duties, duty detail, and settings. Planner and admin work stays in the web
workbench. Wishes and swaps (#124), offline duty activity (#123), and push (#125) come later.

The app has no business logic. It reads through `/api/v1/me/...` and the auth endpoints
(`/api/v1/auth/token`, `/token/refresh`, `/token/revoke`, `/auth/me/active-organization`).
Types come from `@shift-planner/api-client`, strings from `@shift-planner/i18n`, and time
formatting from `@shift-planner/domain`.

## Run

Install from the repository root, not from `mobile/`:

```bash
npm ci
```

Start the local Compose backend (`docker compose up -d postgres backend`; the API listens on
port `18180`), then start Metro with the API address the device can reach:

```bash
cd mobile
EXPO_PUBLIC_API_BASE_URL=http://192.168.1.20:18180 npx expo start
```

Expo Go on a phone must match the SDK of the app. This app is on SDK 58, so use the SDK 58 build
of Expo Go. If Expo Go refuses to open the project, the SDK numbers differ.

| Where the app runs | `EXPO_PUBLIC_API_BASE_URL` |
|---|---|
| Phone in Expo Go on the same Wi-Fi | `http://<your computer's LAN IP>:18180` |
| iOS simulator | `http://localhost:18180` |
| Android emulator | `http://10.0.2.2:18180` |

The backend must accept the phone's origin. Bearer requests do not use cookies, so CORS only
matters for the web build. A phone on the LAN needs the backend bound to `0.0.0.0` (Compose
publishes the port on all interfaces).

`EXPO_PUBLIC_WEB_BASE_URL` is the web app address that the "open the web app" and "open setup"
buttons use (for example `http://192.168.1.20:18130`). It defaults to the API address. There is
no default that points at production.

Seed users for a quick check: `docker compose exec backend python -m app.scripts.seed_e2e` creates
a member, a planner, and an admin for October 2026 (see the root `README.md`).

## Sign-in outcomes

| Session after `POST /api/v1/auth/token` | Screen |
|---|---|
| `user` with `capabilities.team_member_portal` and a linked team member | Home, Duties, Settings tabs |
| `user` without a linked team member (planner or admin only) | "This app is for team members", link to the web app, sign out |
| `account` (no membership) or `role: applicant` | "Finish setup in the browser", link to `/onboarding`, sign out |

The refresh token is stored with `expo-secure-store`. The access token lives in memory only. The
bearer client in `@shift-planner/api-client` refreshes once on a 401, shares one refresh between
concurrent requests, and signs out when the refresh fails. Sign-out revokes the device session on
the server (`POST /api/v1/auth/token/revoke`), wipes secure storage, and clears the query cache.
The web Settings page lists device sessions (`GET /api/v1/auth/me/devices`), so you can confirm the
revoke there.

Switching organization in Settings calls `POST /api/v1/auth/me/active-organization`, keeps the
returned access token, and clears the query cache.

Times are shown in the organization's time zone (`organization_timezone` on the session), not the
device zone. The duties list covers today minus 7 days to today plus 60 days in that zone, grouped
by week.

## Test

```bash
npm run typecheck --workspace mobile
npm run lint --workspace mobile
npm run test --workspace mobile
```

Jest 30 runs through `jest-expo` with React Native Testing Library 14, whose `render` and
`fireEvent` are asynchronous, so tests await them (`renderApp` in `__tests__/support.tsx` is async).
The suite runs with the device zone set to
`Pacific/Honolulu` (`jest.global-setup.js`) so a time shown in the organization zone cannot pass by
accident. CI runs the same three commands in the `mobile` job. There are no native builds in CI.

To check that Metro resolves the workspace packages without a device:

```bash
cd mobile
EXPO_PUBLIC_API_BASE_URL=http://10.0.2.2:18180 npx expo export --platform android --output-dir /tmp/expo-export
EXPO_PUBLIC_API_BASE_URL=http://localhost:18180 npx expo export --platform ios --output-dir /tmp/expo-export-ios
```

## Upgrading the SDK

From `mobile/`, run `npx expo install expo@^58 --fix`, then `npx expo install --check`, and commit the
updated `package.json` files and root `package-lock.json`. Expo rewrites the Expo packages, React,
React Native, and the native modules to the versions of that SDK. It does not touch `expo`'s range,
`@expo/log-box`, or the dev dependencies (`jest-expo`, `babel-preset-expo`, `eslint-config-expo`,
`@react-native/jest-preset`, `@testing-library/react-native`, `@types/react`), so set those to the
versions in the new SDK's `bundledNativeModules.json` and peer ranges. Pin `react` and `react-dom`
to the same version, and keep `react-native-web` at the version the SDK bundles. Regenerating the
lockfile needs npm 11 (`npx npm@11.6.2 install` from the repository root); npm 10 only runs
`npm ci` against it. Then run the checks below and the Metro export for both platforms.

## Workspace notes

The web app uses React 18 and the app uses React 19.3, so npm installs React, React Native, and the
Expo modules under `mobile/node_modules`. `metro.config.js` and `jest.config.js` resolve `react`
and `react-native` from `mobile/` so a package hoisted to the root (for example
`@tanstack/react-query`) does not load the web copy of React. The frontend Docker images ignore
`mobile/` (`.dockerignore`).

## EAS profiles

`eas.json` has `development` (development client, internal distribution), `preview` (internal
distribution), and `production`. There is no store submission yet.

The display name, iOS bundle identifier, and Android package name in `app.config.ts` are
**placeholders** (`com.example.shiftplanner.placeholder`). The repository owner has not chosen them
yet. Replace all three before the first EAS build.
