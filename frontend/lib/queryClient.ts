import { QueryClient } from "@tanstack/react-query";
import { ApiError } from "@/lib/api";

const PLANNING_STALE_TIME_MS = 30_000;

function retryQuery(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
    return false;
  }
  return failureCount < 1;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: PLANNING_STALE_TIME_MS,
        refetchOnWindowFocus: true,
        retry: retryQuery
      },
      mutations: {
        retry: 0
      }
    }
  });
}
