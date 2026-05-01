"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { LucideIcon } from "lucide-react";
import {
  CalendarDays,
  ClipboardList,
  ContactRound,
  Languages,
  LogOut,
  Settings,
  Sparkles,
  Stethoscope,
  UserRound,
  UsersRound
} from "lucide-react";
import { useSession } from "@/components/LocaleProvider";
import { apiFetch } from "@/lib/api";
import { Locale, t, TranslationKey } from "@/lib/i18n";

type NavItem = { href: string; key: TranslationKey; icon: LucideIcon };

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
  const router = useRouter();
  const { me, loading, refreshMe } = useSession();

  const navItems: NavItem[] = [];
  if (me) {
    if (me.role === "applicant") {
      navItems.push({ href: "/pending-onboarding", key: "pendingNav", icon: CalendarDays });
    } else {
      navItems.push({ href: "/", key: "dashboard", icon: Sparkles });
      if (me.capabilities.planning) {
        navItems.push({ href: "/planning", key: "planning", icon: CalendarDays });
      }
      if (me.capabilities.doctor_portal) {
        navItems.push({ href: "/my-planning", key: "myPlanning", icon: CalendarDays });
        navItems.push({ href: "/profile", key: "profile", icon: UserRound });
      }
      if (me.capabilities.admin) {
        navItems.push({ href: "/doctors", key: "doctors", icon: Stethoscope });
        navItems.push({ href: "/shift-groups", key: "shiftGroups", icon: UsersRound });
        navItems.push({ href: "/shift-types", key: "shiftTypes", icon: CalendarDays });
        navItems.push({ href: "/organization", key: "joinRequestsNav", icon: ClipboardList });
        navItems.push({ href: "/organization/users", key: "orgUserAccountsNav", icon: ContactRound });
      }
    }
    navItems.push({ href: "/settings", key: "settings", icon: Settings });
  }

  async function logout() {
    try {
      await apiFetch("/api/v1/auth/logout", { method: "POST" });
    } catch {
      return;
    }
    await refreshMe();
    router.push("/login");
    router.refresh();
  }

  return (
    <div className="min-h-screen">
      <nav className="sticky top-0 z-10 border-b border-slate-200/80 bg-white/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-mint text-white shadow-soft">
            <Sparkles aria-hidden size={20} />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-ink">{t(locale, "appName")}</p>
            <p className="truncate text-xs text-slate-500">
              {me
                ? me.organization.name.trim()
                  ? me.organization.name
                  : t(locale, "emptyValue")
                : t(locale, "aiFirst")}
            </p>
          </div>
          {!loading && me ? (
            <button
              type="button"
              onClick={() => void logout()}
              className="inline-flex h-10 shrink-0 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 shadow-sm"
            >
              <LogOut aria-hidden size={17} />
              {t(locale, "logout")}
            </button>
          ) : !loading ? (
            <Link
              href="/login"
              className="inline-flex h-10 shrink-0 items-center rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 shadow-sm"
            >
              {t(locale, "login")}
            </Link>
          ) : null}
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
