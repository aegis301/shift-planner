import { createApiClient } from "@shift-planner/api-client";

import { API_BASE_URL } from "@/lib/api";

export const apiClient = createApiClient({
  baseUrl: API_BASE_URL,
  auth: { kind: "cookie" }
});
