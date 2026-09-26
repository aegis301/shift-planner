import { useQuery } from "@tanstack/react-query";
import { ApiError } from "@/lib/api";
import { apiClient } from "@/lib/api/client";
import { queryKeys } from "@/lib/queryKeys";
import { readData } from "@/lib/queries/read";

export function useSessionQuery() {
  return useQuery({
    queryKey: queryKeys.session(),
    queryFn: async () => {
      try {
        return await readData(await apiClient.GET("/api/v1/auth/me"));
      } catch (error) {
        if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
          return null;
        }
        throw error;
      }
    }
  });
}
