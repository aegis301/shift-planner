"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AppShell } from "@/components/AppShell";
import type { MeUser, SessionMe } from "@/lib/api/types";
import { Locale } from "@/lib/i18n";
import { queryKeys } from "@/lib/queryKeys";
import { useSessionQuery } from "@/lib/queries/session";

export type { MeAccountSession, MembershipSummary, MeUser, SessionMe } from "@/lib/api/types";

type SessionValue = {
  me: SessionMe | null;
  loading: boolean;
  refreshMe: () => Promise<void>;
};

const LocaleContext = createContext<{ locale: Locale; setLocale: (locale: Locale) => void } | null>(null);
const SessionContext = createContext<SessionValue | null>(null);

export function LocaleShell({ children }: { children: React.ReactNode }) {
  const [locale, setLocale] = useState<Locale>("de");
  const queryClient = useQueryClient();
  const session = useSessionQuery();
  const localeValue = useMemo(() => ({ locale, setLocale }), [locale]);
  const me = session.data ?? null;
  const loading = session.isPending;

  const refreshMe = useCallback(async () => {
    await queryClient.refetchQueries({ queryKey: queryKeys.session() });
  }, [queryClient]);

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
