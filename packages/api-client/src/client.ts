import createClient, { type Client } from "openapi-fetch";

import type { paths } from "../schema";
import { apiErrorFromResponse } from "./errors";

export type CookieAuth = { kind: "cookie" };

export type BearerAuth = {
  kind: "bearer";
  getAccessToken: () => string | null | Promise<string | null>;
  refresh: () => Promise<string | null>;
  onSignedOut: () => void;
};

export type ApiAuth = CookieAuth | BearerAuth;

const RETRY_HEADER = "x-shift-planner-auth-retry";

export function createApiClient(options: { baseUrl: string; auth: ApiAuth }): Client<paths> {
  const client = createClient<paths>({
    baseUrl: options.baseUrl,
    credentials: options.auth.kind === "cookie" ? "include" : "omit"
  });
  client.use({
    async onRequest({ request }) {
      if (options.auth.kind !== "bearer" || request.headers.has("Authorization")) {
        return request;
      }
      const token = await options.auth.getAccessToken();
      if (token) {
        request.headers.set("Authorization", `Bearer ${token}`);
      }
      return request;
    },
    async onResponse({ response, request }) {
      if (
        options.auth.kind === "bearer" &&
        response.status === 401 &&
        request.headers.get(RETRY_HEADER) !== "1"
      ) {
        const next = await options.auth.refresh();
        if (!next) {
          options.auth.onSignedOut();
          throw await apiErrorFromResponse(response.clone());
        }
        const retry = request.clone();
        retry.headers.set("Authorization", `Bearer ${next}`);
        retry.headers.set(RETRY_HEADER, "1");
        const retried = await fetch(retry);
        if (!retried.ok) {
          if (retried.status === 401) {
            options.auth.onSignedOut();
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
