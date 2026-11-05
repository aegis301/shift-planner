import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Platform } from "react-native";
import * as Device from "expo-device";
import { useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@shift-planner/api-client";
import { apiBaseUrl } from "@/lib/config";
import type { MemberSession } from "@/lib/session";
import { clearRefreshToken, readRefreshToken, writeRefreshToken } from "@/lib/tokenStore";

type ApiClient = ReturnType<typeof createApiClient>;

export type AuthStatus = "loading" | "signed-out" | "signed-in";

type AuthContextValue = {
  status: AuthStatus;
  session: MemberSession | null;
  api: ApiClient;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  switchOrganization: (organizationSlug: string) => Promise<void>;
};

type TokenPair = { access_token: string; refresh_token: string; session: MemberSession };

const AuthContext = createContext<AuthContextValue | null>(null);

export function devicePlatform(): "ios" | "android" | "other" {
  if (Platform.OS === "ios" || Platform.OS === "android") {
    return Platform.OS;
  }
  return "other";
}

export function deviceName(): string {
  return Device.deviceName || Device.modelName || "Mobile";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [session, setSession] = useState<MemberSession | null>(null);
  const accessToken = useRef<string | null>(null);
  const baseUrl = apiBaseUrl();
  const publicApi = useMemo(() => createApiClient({ baseUrl, auth: { kind: "none" } }), [baseUrl]);

  const clearLocal = useCallback(async () => {
    accessToken.current = null;
    await clearRefreshToken();
    queryClient.clear();
    setSession(null);
    setStatus("signed-out");
  }, [queryClient]);

  const accept = useCallback(async (pair: TokenPair) => {
    accessToken.current = pair.access_token;
    await writeRefreshToken(pair.refresh_token);
    setSession(pair.session);
    setStatus("signed-in");
  }, []);

  const refresh = useCallback(async (): Promise<string | null> => {
    const stored = await readRefreshToken();
    if (!stored) {
      return null;
    }
    try {
      const { data } = await publicApi.POST("/api/v1/auth/token/refresh", { body: { refresh_token: stored } });
      if (!data) {
        return null;
      }
      await accept(data as TokenPair);
      return data.access_token;
    } catch {
      return null;
    }
  }, [accept, publicApi]);

  const api = useMemo(
    () =>
      createApiClient({
        baseUrl,
        auth: {
          kind: "bearer",
          getAccessToken: () => accessToken.current,
          refresh,
          onSignedOut: () => void clearLocal()
        }
      }),
    [baseUrl, clearLocal, refresh]
  );

  useEffect(() => {
    let active = true;
    void refresh().then((token) => {
      if (active && !token) {
        void clearLocal();
      }
    });
    return () => {
      active = false;
    };
  }, [clearLocal, refresh]);

  const signIn = useCallback(
    async (email: string, password: string) => {
      const { data } = await publicApi.POST("/api/v1/auth/token", {
        body: { email, password, device_name: deviceName(), platform: devicePlatform() }
      });
      if (data) {
        await accept(data as TokenPair);
      }
    },
    [accept, publicApi]
  );

  const signOut = useCallback(async () => {
    try {
      if (accessToken.current) {
        await api.POST("/api/v1/auth/token/revoke");
      }
    } catch {
      accessToken.current = null;
    } finally {
      await clearLocal();
    }
  }, [api, clearLocal]);

  const switchOrganization = useCallback(
    async (organizationSlug: string) => {
      const { data } = await api.POST("/api/v1/auth/me/active-organization", {
        body: { organization_slug: organizationSlug }
      });
      if (!data) {
        return;
      }
      if (data.access_token) {
        accessToken.current = data.access_token;
      }
      queryClient.clear();
      const { access_token: _token, ...user } = data;
      setSession({ ...user, auth_kind: "user" } as MemberSession);
    },
    [api, queryClient]
  );

  const value = useMemo<AuthContextValue>(
    () => ({ status, session, api, signIn, signOut, switchOrganization }),
    [api, session, signIn, signOut, status, switchOrganization]
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth outside AuthProvider");
  }
  return value;
}
