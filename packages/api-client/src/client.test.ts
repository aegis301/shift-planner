import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "./client";
import { ApiError, messageFromDetail } from "./errors";

describe("messageFromDetail", () => {
  it("reads a string, a validation message, or the status", () => {
    expect(messageFromDetail("nope", 400)).toBe("nope");
    expect(messageFromDetail([{ msg: "bad" }], 422)).toBe("bad");
    expect(messageFromDetail({}, 500)).toBe("API request failed: 500");
  });
});

describe("createApiClient", () => {
  it("throws ApiError for a refused cookie request", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "nope" }), { status: 403 }))
    );
    const client = createApiClient({ baseUrl: "http://example.test", auth: { kind: "cookie" } });
    await expect(client.GET("/api/v1/me/home")).rejects.toBeInstanceOf(ApiError);
    const [input, init] = vi.mocked(fetch).mock.calls[0] ?? [];
    const credentials = input instanceof Request ? input.credentials : (init as RequestInit | undefined)?.credentials;
    expect(credentials).toBe("include");
    vi.unstubAllGlobals();
  });

  it("refreshes a bearer token once after 401", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
      if (headers.get("Authorization") === "Bearer next") {
        return new Response(JSON.stringify({ duties: [], swap_actions: [], draft_wishes: null }), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: "expired" }), { status: 401 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const onSignedOut = vi.fn();
    const client = createApiClient({
      baseUrl: "http://example.test",
      auth: {
        kind: "bearer",
        getAccessToken: () => "old",
        refresh: async () => "next",
        onSignedOut
      }
    });
    const result = await client.GET("/api/v1/me/home");
    expect(result.data?.duties).toEqual([]);
    expect(onSignedOut).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    vi.unstubAllGlobals();
  });

  it("shares one refresh between concurrent 401 responses", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
      if (headers.get("Authorization") === "Bearer next") {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      return new Response(JSON.stringify({ detail: "expired" }), { status: 401 });
    });
    vi.stubGlobal("fetch", fetchMock);
    let release: (token: string) => void = () => undefined;
    const refresh = vi.fn(
      () =>
        new Promise<string | null>((resolve) => {
          release = resolve;
        })
    );
    const onSignedOut = vi.fn();
    const client = createApiClient({
      baseUrl: "http://example.test",
      auth: { kind: "bearer", getAccessToken: () => "old", refresh, onSignedOut }
    });
    const first = client.GET("/api/v1/me/duties", { params: { query: { from: "2026-10-01", to: "2026-10-31" } } });
    const second = client.GET("/api/v1/me/duties", { params: { query: { from: "2026-11-01", to: "2026-11-30" } } });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    await vi.waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
    release("next");
    const [one, two] = await Promise.all([first, second]);
    expect(one.data).toEqual([]);
    expect(two.data).toEqual([]);
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(onSignedOut).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("does not refresh or send credentials without auth", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ detail: "Invalid credentials" }), { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);
    const client = createApiClient({ baseUrl: "http://example.test", auth: { kind: "none" } });
    await expect(
      client.POST("/api/v1/auth/token", {
        body: { email: "a@example.test", password: "x", device_name: "Phone", platform: "ios" }
      })
    ).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [input] = fetchMock.mock.calls[0] as unknown as [Request];
    expect(input.credentials).toBe("omit");
    expect(input.headers.get("Authorization")).toBeNull();
    vi.unstubAllGlobals();
  });

  it("signs out when the bearer refresh returns nothing", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "expired" }), { status: 401 })));
    const onSignedOut = vi.fn();
    const client = createApiClient({
      baseUrl: "http://example.test",
      auth: {
        kind: "bearer",
        getAccessToken: () => "old",
        refresh: async () => null,
        onSignedOut
      }
    });
    await expect(client.GET("/api/v1/me/home")).rejects.toBeInstanceOf(ApiError);
    expect(onSignedOut).toHaveBeenCalledOnce();
    vi.unstubAllGlobals();
  });
});
