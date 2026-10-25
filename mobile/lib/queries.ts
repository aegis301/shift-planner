import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/lib/auth";
import { queryKeys } from "@/lib/queryKeys";
import { userSession } from "@/lib/session";

export function useMemberHome() {
  const { api, session } = useAuth();
  const user = userSession(session);
  return useQuery({
    queryKey: queryKeys.memberHome(user?.organization_id ?? 0),
    enabled: user != null,
    queryFn: async () => (await api.GET("/api/v1/me/home")).data ?? null
  });
}

export function useMemberDuties(window: { from: string; to: string }) {
  const { api, session } = useAuth();
  const user = userSession(session);
  return useQuery({
    queryKey: queryKeys.memberDuties(user?.organization_id ?? 0, window.from, window.to),
    enabled: user != null,
    queryFn: async () => (await api.GET("/api/v1/me/duties", { params: { query: window } })).data ?? []
  });
}
