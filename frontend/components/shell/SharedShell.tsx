"use client";

import { useLocale } from "@/components/LocaleProvider";
import { ShellHeaderMenus, useShellSession } from "@/components/shell/shellSession";
import { t } from "@/lib/i18n";

export function SharedShell({ children }: { children: React.ReactNode }) {
  const { locale, setLocale } = useLocale();
  const session = useShellSession(locale, setLocale);
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="flex h-14 items-center justify-between border-b border-slate-200 bg-white px-4">
        <p className="text-sm font-semibold text-ink">{t(locale, "appName")}</p>
        <ShellHeaderMenus session={session} />
      </header>
      <main className="mx-auto w-full max-w-lg px-4 py-8">{children}</main>
    </div>
  );
}
