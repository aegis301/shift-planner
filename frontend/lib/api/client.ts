import createClient from "openapi-fetch";

import { API_BASE_URL, apiErrorFromResponse } from "@/lib/api";
import type { paths } from "@/lib/api/schema";

export const apiClient = createClient<paths>({
  baseUrl: API_BASE_URL,
  credentials: "include"
});

apiClient.use({
  async onResponse({ response }) {
    if (!response.ok) {
      throw await apiErrorFromResponse(response.clone());
    }
    return response;
  }
});
