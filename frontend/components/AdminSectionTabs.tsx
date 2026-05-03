"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { t, type Locale, type TranslationKey } from "@/lib/i18n";

export type AdminTabDef = { href: string; labelKey: TranslationKey; isActive: (pathname: string) => boolean };

export function AdminSectionTabs({ locale, tabs }: { locale: Locale; tabs: AdminTabDef[] }) {
  const pathname = usePathname();
  return (
    <nav className="mb-6 flex flex-wrap gap-1 border-b border-slate-200" aria-label={t(locale, "adminSectionTabsLabel")}>
      {tabs.map((tab) => {
        const active = tab.isActive(pathname);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={`relative -mb-px inline-flex items-center rounded-t-lg px-4 py-2.5 text-sm font-medium transition-colors ${
              active
                ? "border border-b-0 border-slate-200 bg-white text-ink shadow-sm"
                : "border border-transparent text-slate-600 hover:bg-slate-50 hover:text-slate-900"
            }`}
          >
            {t(locale, tab.labelKey)}
          </Link>
        );
      })}
    </nav>
  );
}
