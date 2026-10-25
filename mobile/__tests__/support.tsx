import type { ReactElement, ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react-native";
import * as SecureStore from "expo-secure-store";
import { AuthProvider } from "@/lib/auth";
import { LocaleProvider } from "@/lib/locale";

export type Route = { method: string; path: string; query?: Record<string, string>; status?: number; body?: unknown };

export type Call = { method: string; path: string; query: Record<string, string>; authorization: string | null; body: unknown };

export function mockApi(routes: Route[]): Call[] {
  const calls: Call[] = [];
  globalThis.fetch = jest.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : new Request(String(input), init);
    const url = new URL(request.url);
    const text = request.method === "GET" ? "" : await request.clone().text();
    const query = Object.fromEntries(url.searchParams);
    calls.push({
      method: request.method,
      path: url.pathname,
      query,
      authorization: request.headers.get("Authorization"),
      body: text ? JSON.parse(text) : null
    });
    const route = routes.find((row) => {
      if (row.method !== request.method || row.path !== url.pathname) {
        return false;
      }
      if (!row.query) {
        return true;
      }
      return Object.entries(row.query).every(([key, value]) => url.searchParams.get(key) === value);
    });
    if (!route) {
      return new Response(JSON.stringify({ detail: "not mocked" }), { status: 404 });
    }
    const status = route.status ?? 200;
    return new Response(status === 204 ? null : JSON.stringify(route.body ?? {}), {
      status,
      headers: { "Content-Type": "application/json" }
    });
  }) as typeof fetch;
  return calls;
}

export function tokenPair(session: unknown, access = "access-1", refresh = "refresh-2") {
  return { access_token: access, refresh_token: refresh, expires_in: 900, token_type: "bearer", session };
}

export function organization(id: number, name: string, slug: string) {
  return { id, name, slug, plan_tier: "team" };
}

export function memberSession(overrides: Record<string, unknown> = {}) {
  return {
    auth_kind: "user",
    id: 11,
    email: "member@example.test",
    role: "team_member",
    locale: "en",
    organization_id: 1,
    organization: organization(1, "Klinik Nord", "nord"),
    organization_timezone: "Europe/Berlin",
    capabilities: { admin: false, planning: false, team_member_portal: true },
    team_member_id: 7,
    memberships: [],
    shift_groups: [],
    planner_shift_groups: [],
    organization_shift_groups: [],
    ...overrides
  };
}

export async function storeRefreshToken(token = "refresh-1") {
  await SecureStore.setItemAsync("shift-planner.refresh-token", token);
}

export function renderApp(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <LocaleProvider initialLocale="en">
        <AuthProvider>{children}</AuthProvider>
      </LocaleProvider>
    </QueryClientProvider>
  );
  return { ...render(ui, { wrapper }), queryClient };
}
