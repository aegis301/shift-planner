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
