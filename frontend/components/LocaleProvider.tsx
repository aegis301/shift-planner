"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { apiFetch } from "@/lib/api";
import { Locale } from "@/lib/i18n";

export type MembershipSummary = {
  membership_id: number;
  organization: { id: number; name: string; slug: string; plan_tier: string };
  role: string;
  team_member_id: number | null;
};

export type MeUser = {
  id: number;
  email: string;
  role: string;
  locale: string;
  organization_id: number;
  organization: { id: number; name: string; slug: string; plan_tier: string };
  team_member_id: number | null;
  shift_groups: { id: number; code: string; name_de: string; name_en: string; is_active?: boolean }[];
  planner_shift_groups: { id: number; code: string; name_de: string; name_en: string; is_active?: boolean }[];
  organization_shift_groups?: { id: number; code: string; name_de: string; name_en: string; is_active?: boolean }[];
  capabilities: { admin: boolean; planning: boolean; team_member_portal: boolean };
  memberships: MembershipSummary[];
};

type SessionValue = {
  me: MeUser | null;
  loading: boolean;
  refreshMe: () => Promise<void>;
};

const LocaleContext = createContext<{ locale: Locale; setLocale: (locale: Locale) => void } | null>(null);
const SessionContext = createContext<SessionValue | null>(null);

export function LocaleShell({ children }: { children: React.ReactNode }) {
  const [locale, setLocale] = useState<Locale>("de");
  const [me, setMe] = useState<MeUser | null>(null);
  const [loading, setLoading] = useState(true);
  const localeValue = useMemo(() => ({ locale, setLocale }), [locale]);

  const refreshMe = useCallback(async () => {
    setLoading(true);
    try {
      const next = await apiFetch<MeUser>("/api/v1/auth/me");
      setMe(next);
    } catch {
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshMe();
  }, [refreshMe]);

  const sessionValue = useMemo(() => ({ me, loading, refreshMe }), [me, loading, refreshMe]);

  return (
    <LocaleContext.Provider value={localeValue}>
      <SessionContext.Provider value={sessionValue}>
        <AppShell locale={locale} setLocale={setLocale}>
          {children}
        </AppShell>
      </SessionContext.Provider>
    </LocaleContext.Provider>
  );
}

export function useLocale() {
  const context = useContext(LocaleContext);
  if (!context) {
    throw new Error("Locale context missing");
  }
  return context;
}

export function useSession() {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error("Session context missing");
  }
  return context;
}
