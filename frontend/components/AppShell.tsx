"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import type { LucideIcon } from "lucide-react";
import {
  CalendarDays,
  Languages,
  LayoutGrid,
  LogOut,
  PanelLeft,
  PanelLeftClose,
  Settings,
  Sparkles,
  UserRound,
  UsersRound
} from "lucide-react";
import { useSession } from "@/components/LocaleProvider";
import { apiFetch } from "@/lib/api";
import { Locale, t, TranslationKey } from "@/lib/i18n";

const SIDEBAR_STORAGE_KEY = "shift-planner-sidebar-expanded";

type SidebarNavItem = { href: string; key: TranslationKey; icon: LucideIcon; match: (path: string) => boolean };

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
  const [sidebarExpanded, setSidebarExpanded] = useState(true);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [orgSwitchBusy, setOrgSwitchBusy] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      const v = window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
      if (v === "0") {
        setSidebarExpanded(false);
      }
      const legacy = window.localStorage.getItem("shift-planner-sidebar-open");
      if (legacy === "0" && v == null) {
        setSidebarExpanded(false);
      }
    } catch {
      return;
    }
  }, []);

  useEffect(() => {
    setUserMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!userMenuOpen) return;
    function onDocMouseDown(ev: MouseEvent) {
      const el = userMenuRef.current;
      if (el && !el.contains(ev.target as Node)) {
        setUserMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocMouseDown);
    return () => document.removeEventListener("mousedown", onDocMouseDown);
  }, [userMenuOpen]);

  const sidebarNavItems: SidebarNavItem[] = [];
  if (me) {
    if (me.role === "applicant") {
      sidebarNavItems.push({
        href: "/pending-onboarding",
        key: "pendingNav",
        icon: CalendarDays,
        match: (p) => p.startsWith("/pending-onboarding"),
      });
    } else {
      sidebarNavItems.push({
        href: "/",
        key: "dashboard",
        icon: Sparkles,
        match: (p) => p === "/" || p === "",
      });
      if (me.capabilities.planning) {
        sidebarNavItems.push({
          href: "/planning",
          key: "planning",
          icon: CalendarDays,
          match: (p) => p.startsWith("/planning"),
        });
      }
      if (me.capabilities.team_member_portal) {
        sidebarNavItems.push({
          href: "/my-planning",
          key: "myPlanning",
          icon: CalendarDays,
          match: (p) => p.startsWith("/my-planning"),
        });
        sidebarNavItems.push({
          href: "/profile",
          key: "profile",
          icon: UserRound,
          match: (p) => p.startsWith("/profile"),
        });
      }
      if (me.capabilities.admin) {
        sidebarNavItems.push({
          href: "/organization/team",
          key: "navTeamManagement",
          icon: UsersRound,
          match: (p) => p.startsWith("/organization/team"),
        });
        sidebarNavItems.push({
          href: "/organization/shifts/groups",
          key: "navShiftManagement",
          icon: LayoutGrid,
          match: (p) => p.startsWith("/organization/shifts"),
        });
      }
    }
  }

  function persistSidebarExpanded(next: boolean) {
    try {
      window.localStorage.setItem(SIDEBAR_STORAGE_KEY, next ? "1" : "0");
    } catch {
      return;
    }
  }

  function toggleSidebar() {
    setSidebarExpanded((v) => {
      const next = !v;
      persistSidebarExpanded(next);
      return next;
    });
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

  async function switchOrganization(slug: string) {
    if (!me || slug === me.organization.slug) return;
    setOrgSwitchBusy(true);
    try {
      await apiFetch("/api/v1/auth/me/active-organization", {
        method: "POST",
        body: JSON.stringify({ organization_slug: slug }),
      });
      await refreshMe();
      router.refresh();
      setUserMenuOpen(false);
    } catch {
      return;
    } finally {
      setOrgSwitchBusy(false);
    }
  }

  const applicantOnly = me?.role === "applicant";

  return (
    <div className="flex min-h-screen bg-slate-50">
      {me ? (
        <aside
          id="app-sidebar"
          className={`sticky top-0 z-30 flex h-screen shrink-0 flex-col border-r border-slate-200 bg-white shadow-sm transition-[width] duration-200 ease-out ${
            sidebarExpanded ? "w-56" : "w-14"
          }`}
        >
          <div className="flex h-full min-h-0 w-full min-w-0 flex-col">
            <div
              className={`flex items-center border-b border-slate-100 ${sidebarExpanded ? "gap-2 px-3 py-3" : "justify-center px-2 py-3"}`}
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-mint text-white shadow-soft">
                <Sparkles aria-hidden size={18} />
              </div>
              {sidebarExpanded ? (
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-ink">{t(locale, "appName")}</p>
                  <p className="truncate text-xs text-slate-500">
                    {me.organization.name.trim() ? me.organization.name : t(locale, "emptyValue")}
                  </p>
                </div>
              ) : null}
            </div>
            <nav className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto p-2">
              {sidebarNavItems.map((item) => {
                const Icon = item.icon;
                const active = item.match(pathname);
                const label = t(locale, item.key);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    title={label}
                    className={`flex items-center rounded-lg text-sm font-medium transition-colors ${
                      sidebarExpanded ? "gap-3 px-3 py-2.5" : "justify-center px-0 py-2.5"
                    } ${active ? "bg-ink text-white shadow-sm" : "text-slate-700 hover:bg-slate-100"}`}
                  >
                    <Icon aria-hidden size={18} className="shrink-0 opacity-90" />
                    {sidebarExpanded ? (
                      <span className="truncate">{label}</span>
                    ) : (
                      <span className="sr-only">{label}</span>
                    )}
                  </Link>
                );
              })}
            </nav>
          </div>
        </aside>
      ) : null}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-3 border-b border-slate-200/90 bg-white/95 px-4 backdrop-blur">
          {me ? (
            <button
              type="button"
              onClick={toggleSidebar}
              className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-700 shadow-sm"
              aria-expanded={sidebarExpanded}
              aria-controls="app-sidebar"
              title={sidebarExpanded ? t(locale, "navToggleSidebarHide") : t(locale, "navToggleSidebarShow")}
            >
              {sidebarExpanded ? <PanelLeftClose aria-hidden size={20} /> : <PanelLeft aria-hidden size={20} />}
            </button>
          ) : null}
          {!me && !loading ? (
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-mint text-white shadow-soft">
              <Sparkles aria-hidden size={18} />
            </div>
          ) : null}
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-ink">{t(locale, "appName")}</p>
            {me ? (
              <p className="truncate text-xs text-slate-500">
                {me.organization.name.trim() ? me.organization.name : t(locale, "emptyValue")}
              </p>
            ) : (
              <p className="truncate text-xs text-slate-500">{t(locale, "aiFirst")}</p>
            )}
          </div>
          {!loading && me ? (
            <div ref={userMenuRef} className="relative shrink-0">
              <button
                type="button"
                aria-expanded={userMenuOpen}
                aria-haspopup="menu"
                aria-label={t(locale, "userMenuAriaLabel")}
                className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-600 text-sm font-semibold uppercase text-white shadow-md ring-2 ring-white transition hover:bg-emerald-700"
                onClick={() => setUserMenuOpen((o) => !o)}
              >
                {me.email.trim().charAt(0) || "?"}
              </button>
              {userMenuOpen ? (
                <div
                  role="menu"
                  className="absolute right-0 top-full z-50 mt-2 w-56 overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-lg"
                >
                  {me.memberships.length > 1 ? (
                    <div className="border-b border-slate-100 px-2 py-2" role="none">
                      <p className="px-2 pb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                        {t(locale, "organizationSwitcherLabel")}
                      </p>
                      {me.memberships.map((m) => {
                        const activeOrg = m.organization.id === me.organization_id;
                        return (
                          <button
                            key={m.membership_id}
                            type="button"
                            role="menuitem"
                            disabled={activeOrg || orgSwitchBusy}
                            className={`flex w-full flex-col gap-0.5 rounded-lg px-2 py-2 text-left text-sm ${
                              activeOrg ? "bg-slate-100 text-slate-900" : "text-slate-800 hover:bg-slate-50"
                            } disabled:opacity-60`}
                            onClick={() => void switchOrganization(m.organization.slug)}
                          >
                            <span className="font-medium">
                              {m.organization.name.trim() ? m.organization.name : m.organization.slug}
                            </span>
                            <span className="font-mono text-xs text-slate-500">{m.organization.slug}</span>
                            {activeOrg ? (
                              <span className="text-xs text-emerald-800">{t(locale, "organizationSwitcherCurrent")}</span>
                            ) : null}
                          </button>
                        );
                      })}
                    </div>
                  ) : null}
                  <Link
                    role="menuitem"
                    href="/settings"
                    className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm text-slate-800 hover:bg-slate-50"
                    onClick={() => setUserMenuOpen(false)}
                  >
                    <Settings aria-hidden size={16} className="text-slate-500" />
                    {t(locale, "settings")}
                  </Link>
                  <button
                    type="button"
                    role="menuitem"
                    className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm text-slate-800 hover:bg-slate-50"
                    onClick={() => setLocale(locale === "de" ? "en" : "de")}
                  >
                    <Languages aria-hidden size={16} className="text-slate-500" />
                    {t(locale, "language")}: {locale.toUpperCase()}
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    className="flex w-full items-center gap-2 border-t border-slate-100 px-4 py-2.5 text-left text-sm font-medium text-red-700 hover:bg-red-50"
                    onClick={() => void logout()}
                  >
                    <LogOut aria-hidden size={16} />
                    {t(locale, "logout")}
                  </button>
                </div>
              ) : null}
            </div>
          ) : !loading ? (
            <div className="flex shrink-0 items-center gap-2">
              <Link
                href="/login"
                className="inline-flex h-10 items-center rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 shadow-sm"
              >
                {t(locale, "login")}
              </Link>
              <button
                type="button"
                className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium shadow-sm"
                onClick={() => setLocale(locale === "de" ? "en" : "de")}
                title={t(locale, "language")}
              >
                <Languages aria-hidden size={17} />
                {locale.toUpperCase()}
              </button>
            </div>
          ) : null}
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">{children}</main>
      </div>
    </div>
  );
}
