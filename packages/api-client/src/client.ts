import createClient, { type Client } from "openapi-fetch";

import type { paths } from "../schema";
import { apiErrorFromResponse } from "./errors";

export type CookieAuth = { kind: "cookie" };

export type NoAuth = { kind: "none" };

export type BearerAuth = {
  kind: "bearer";
  getAccessToken: () => string | null | Promise<string | null>;
  refresh: () => Promise<string | null>;
  onSignedOut: () => void;
};

export type ApiAuth = CookieAuth | NoAuth | BearerAuth;

const RETRY_HEADER = "x-shift-planner-auth-retry";

export function singleFlight<T>(task: () => Promise<T>): () => Promise<T> {
  let pending: Promise<T> | null = null;
  return () => {
    if (!pending) {
      pending = task().finally(() => {
        pending = null;
      });
    }
    return pending;
  };
}

export function createApiClient(options: { baseUrl: string; auth: ApiAuth }): Client<paths> {
  const auth = options.auth;
  const client = createClient<paths>({
    baseUrl: options.baseUrl,
    credentials: auth.kind === "cookie" ? "include" : "omit"
  });
  const refresh = auth.kind === "bearer" ? singleFlight(auth.refresh) : null;
  client.use({
    async onRequest({ request }) {
      if (auth.kind !== "bearer" || request.headers.has("Authorization")) {
        return request;
      }
      const token = await auth.getAccessToken();
      if (token) {
        request.headers.set("Authorization", `Bearer ${token}`);
      }
      return request;
    },
    async onResponse({ response, request }) {
      if (auth.kind === "bearer" && refresh && response.status === 401 && request.headers.get(RETRY_HEADER) !== "1") {
        const next = await refresh();
        if (!next) {
          auth.onSignedOut();
          throw await apiErrorFromResponse(response.clone());
        }
        const retry = request.clone();
        retry.headers.set("Authorization", `Bearer ${next}`);
        retry.headers.set(RETRY_HEADER, "1");
        const retried = await fetch(retry);
        if (!retried.ok) {
          if (retried.status === 401) {
            auth.onSignedOut();
          }
          throw await apiErrorFromResponse(retried);
        }
        return retried;
      }
      if (!response.ok) {
        throw await apiErrorFromResponse(response.clone());
      }
      return response;
    }
  });
  return client;
}
