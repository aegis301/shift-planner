import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { getLocales } from "expo-localization";
import { t as translate, type Locale, type TranslationKey } from "@shift-planner/i18n";
import { readLocaleOverride, writeLocaleOverride } from "@/lib/tokenStore";

type LocaleContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: TranslationKey, vars?: Record<string, string>) => string;
};

export function deviceLocale(): Locale {
  return getLocales()[0]?.languageCode === "de" ? "de" : "en";
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

export function LocaleProvider({ children, initialLocale }: { children: ReactNode; initialLocale?: Locale }) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale ?? deviceLocale());

  useEffect(() => {
    if (initialLocale) {
      return;
    }
    void readLocaleOverride().then((stored) => {
      if (stored === "de" || stored === "en") {
        setLocaleState(stored);
      }
    });
  }, [initialLocale]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    void writeLocaleOverride(next);
  }, []);

  const value = useMemo<LocaleContextValue>(
    () => ({ locale, setLocale, t: (key, vars) => translate(locale, key, vars) }),
    [locale, setLocale]
  );
  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale(): LocaleContextValue {
  const value = useContext(LocaleContext);
  if (!value) {
    throw new Error("useLocale outside LocaleProvider");
  }
  return value;
}
