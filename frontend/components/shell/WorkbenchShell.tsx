"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { LucideIcon } from "lucide-react";
import { CalendarDays, Clock, LayoutGrid, PanelLeft, PanelLeftClose, Sparkles, UsersRound } from "lucide-react";
import { useLocale } from "@/components/LocaleProvider";
import { NotificationSlot } from "@/components/shell/NotificationSlot";
import { ShellHeaderMenus, useAreaGuard, useShellSession } from "@/components/shell/shellSession";
import { WorkbenchNarrowNotice } from "@/components/shell/WorkbenchNarrowNotice";
import { applyDensity, readDensity } from "@/lib/density";
import { t, type TranslationKey } from "@/lib/i18n";
import { isUserSession, membershipDefaultPath } from "@/lib/membershipRouting";

const SIDEBAR_STORAGE_KEY = "shift-planner-sidebar-expanded";

type NavItem = { href: string; key: TranslationKey; icon: LucideIcon; match: (path: string) => boolean };

export function WorkbenchShell({ children }: { children: React.ReactNode }) {
  const { locale, setLocale } = useLocale();
  const session = useShellSession(locale, setLocale);
  const guard = useAreaGuard();
  const [sidebarExpanded, setSidebarExpanded] = useState(false);
  const { me, loading, pathname } = session;

  useEffect(() => {
    applyDensity(readDensity());
  }, []);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
      if (stored === "1") {
        setSidebarExpanded(true);
      }
    } catch {
      return;
    }
  }, []);

  useEffect(() => {
    if (guard.redirect && guard.me) {
      guard.router.replace(membershipDefaultPath(guard.me));
    }
  }, [guard.redirect, guard.me, guard.router]);

  const items: NavItem[] = [];
  if (me && isUserSession(me)) {
    items.push({ href: "/", key: "dashboard", icon: Sparkles, match: (path) => path === "/" });
    if (me.capabilities.planning) {
      items.push({ href: "/planning", key: "planning", icon: CalendarDays, match: (path) => path.startsWith("/planning") });
      items.push({ href: "/hours", key: "hoursNav", icon: Clock, match: (path) => path === "/hours" });
    }
    if (me.capabilities.admin) {
      items.push({
        href: "/organization/team",
        key: "navTeamManagement",
        icon: UsersRound,
        match: (path) => path.startsWith("/organization/team")
      });
      items.push({
        href: "/organization/shifts/groups",
        key: "navShiftManagement",
        icon: LayoutGrid,
        match: (path) => path.startsWith("/organization/shifts")
      });
    }
  }

  const areaSwitch =
    me && isUserSession(me) && me.capabilities.team_member_portal
      ? { href: "/my", label: t(locale, "memberArea") }
      : undefined;

  return (
    <div className="flex min-h-screen bg-slate-50">
      <aside
        id="app-sidebar"
        className={`sticky top-0 z-30 hidden h-screen shrink-0 flex-col border-r border-slate-200 bg-white shadow-sm md:flex ${
          sidebarExpanded ? "w-56" : "w-14"
        }`}
      >
        <div className={`flex items-center border-b border-slate-100 ${sidebarExpanded ? "gap-2 px-3 py-3" : "justify-center px-2 py-3"}`}>
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-mint text-white shadow-soft">
            <Sparkles aria-hidden size={18} />
          </div>
          {sidebarExpanded ? <p className="truncate text-sm font-semibold text-ink">{t(locale, "appName")}</p> : null}
        </div>
        <nav className="flex flex-1 flex-col gap-1 overflow-y-auto p-2">
          {items.map((item) => {
            const Icon = item.icon;
            const active = item.match(pathname);
            const label = t(locale, item.key);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                title={label}
                className={`flex items-center rounded-lg text-sm font-medium ${
                  sidebarExpanded ? "gap-3 px-3 py-2.5" : "justify-center py-2.5"
                } ${active ? "bg-ink text-white" : "text-slate-700 hover:bg-slate-100"}`}
              >
                <Icon aria-hidden size={18} />
                {sidebarExpanded ? <span className="truncate">{label}</span> : <span className="sr-only">{label}</span>}
              </Link>
            );
          })}
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <WorkbenchNarrowNotice locale={locale} />
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-slate-200/90 bg-white/95 px-4 backdrop-blur">
          <button
            type="button"
            className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-700"
            aria-expanded={sidebarExpanded}
            aria-controls="app-sidebar"
            onClick={() => {
              setSidebarExpanded((value) => {
                const next = !value;
                window.localStorage.setItem(SIDEBAR_STORAGE_KEY, next ? "1" : "0");
                return next;
              });
            }}
          >
            {sidebarExpanded ? <PanelLeftClose aria-hidden size={20} /> : <PanelLeft aria-hidden size={20} />}
          </button>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-ink">{t(locale, "appName")}</p>
            <p className="truncate text-xs text-slate-500">
              {me && isUserSession(me) ? me.organization.name || me.organization.slug : loading ? "" : t(locale, "aiFirst")}
            </p>
          </div>
          <NotificationSlot />
          <ShellHeaderMenus session={session} areaSwitch={areaSwitch} />
        </header>
        <main className="w-full min-w-0 flex-1 px-4 py-4">{children}</main>
      </div>
    </div>
  );
}
