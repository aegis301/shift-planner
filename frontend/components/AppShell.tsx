"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { CalendarDays, Languages, Settings, Sparkles, Stethoscope } from "lucide-react";
import { Locale, t } from "@/lib/i18n";

const navItems = [
  { href: "/", key: "dashboard", icon: Sparkles },
  { href: "/planning", key: "planning", icon: CalendarDays },
  { href: "/doctors", key: "doctors", icon: Stethoscope },
  { href: "/shift-types", key: "shiftTypes", icon: CalendarDays },
  { href: "/settings", key: "settings", icon: Settings }
] as const;

export function AppShell({
  locale,
  setLocale,
  children
}: {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  return (
    <div className="min-h-screen">
      <nav className="sticky top-0 z-10 border-b border-slate-200/80 bg-white/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-mint text-white shadow-soft">
            <Sparkles aria-hidden size={20} />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-ink">{t(locale, "appName")}</p>
            <p className="truncate text-xs text-slate-500">{t(locale, "aiFirst")}</p>
          </div>
          <button
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium shadow-sm"
            onClick={() => setLocale(locale === "de" ? "en" : "de")}
            title={t(locale, "language")}
          >
            <Languages aria-hidden size={17} />
            {locale.toUpperCase()}
          </button>
        </div>
        <div className="mx-auto flex max-w-7xl gap-2 overflow-x-auto px-4 pb-3">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`inline-flex h-10 shrink-0 items-center gap-2 rounded-lg px-3 text-sm font-medium ${
                  active ? "bg-ink text-white" : "bg-white text-slate-600 ring-1 ring-slate-200"
                }`}
              >
                <Icon aria-hidden size={16} />
                {t(locale, item.key)}
              </Link>
            );
          })}
        </div>
      </nav>
      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
    </div>
  );
}
