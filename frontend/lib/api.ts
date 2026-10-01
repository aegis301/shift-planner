import { apiErrorFromResponse } from "@shift-planner/api-client";

export { ApiError, apiErrorFromResponse, messageFromDetail } from "@shift-planner/api-client";

function normalizeApiBase(): string {
  const raw = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (raw === "") {
    return "";
  }
  const base = raw ?? "http://localhost:18180";
  return base.replace(/\/$/, "");
}

const API_BASE_URL = normalizeApiBase();

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });
  if (!response.ok) {
    throw await apiErrorFromResponse(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  const text = await response.text();
  if (!text.trim()) {
    return undefined as T;
  }
  return JSON.parse(text) as T;
}

export { API_BASE_URL };
