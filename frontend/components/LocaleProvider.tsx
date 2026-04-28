"use client";

import { createContext, useContext, useMemo, useState } from "react";
import { Locale } from "@/lib/i18n";
import { AppShell } from "@/components/AppShell";

const LocaleContext = createContext<{ locale: Locale; setLocale: (locale: Locale) => void } | null>(null);

export function LocaleShell({ children }: { children: React.ReactNode }) {
  const [locale, setLocale] = useState<Locale>("de");
  const value = useMemo(() => ({ locale, setLocale }), [locale]);
  return (
    <LocaleContext.Provider value={value}>
      <AppShell locale={locale} setLocale={setLocale}>
        {children}
      </AppShell>
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

