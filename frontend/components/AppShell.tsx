"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import type { LucideIcon } from "lucide-react";
import {
  Building2,
  CalendarDays,
  ChevronDown,
  Clock,
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
import { useSession, type MeUser, type SessionMe } from "@/components/LocaleProvider";
import { apiFetch } from "@/lib/api";
import { Locale, t, TranslationKey } from "@/lib/i18n";
import {
  isUserSession,
  membershipDefaultPath,
  membershipRoleLabel,
  pathnameCompatibleWithMembership,
} from "@/lib/membershipRouting";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const SIDEBAR_STORAGE_KEY = "shift-planner-sidebar-expanded";

type SidebarNavItem = { href: string; key: TranslationKey; icon: LucideIcon; match: (path: string) => boolean };

function OrgMembershipRows({
  locale,
  me,
  orgSwitchBusy,
  onPick,
}: {
  locale: Locale;
  me: MeUser;
  orgSwitchBusy: boolean;
  onPick: (slug: string) => void;
}) {
  return (
    <>
      {(me.memberships ?? []).map((m) => {
        const activeOrg = m.organization.id === me.organization_id;
        return (
          <DropdownMenuItem
            key={m.membership_id}
            disabled={activeOrg || orgSwitchBusy}
            className={`flex-col items-start gap-0.5 rounded-lg px-2 py-2 text-sm ${
              activeOrg ? "bg-slate-100 text-slate-900" : "text-slate-800"
            }`}
            onSelect={() => {
              if (!activeOrg && !orgSwitchBusy) {
                onPick(m.organization.slug);
              }
            }}
          >
            <span className="font-medium">
              {m.organization.name.trim() ? m.organization.name : m.organization.slug}
            </span>
            <span className="font-mono text-xs text-slate-500">{m.organization.slug}</span>
            <span className="text-xs text-slate-600">{membershipRoleLabel(locale, m.role)}</span>
            {m.team_member_id != null ? (
              <span className="text-xs text-slate-500">{t(locale, "membershipLinkedTeamProfile")}</span>
            ) : null}
            {activeOrg ? (
              <span className="text-xs text-emerald-800">{t(locale, "organizationSwitcherCurrent")}</span>
            ) : null}
          </DropdownMenuItem>
        );
      })}
    </>
  );
}

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
  const [sidebarExpanded, setSidebarExpanded] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [orgMenuOpen, setOrgMenuOpen] = useState(false);
  const [orgSwitchBusy, setOrgSwitchBusy] = useState(false);

  useEffect(() => {
    try {
      const v = window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
      if (v === "1") {
        setSidebarExpanded(true);
      } else if (v === "0") {
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
    setOrgMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (loading || !me) return;
    if (!pathnameCompatibleWithMembership(pathname, me)) {
      router.replace(membershipDefaultPath(me));
    }
  }, [loading, me, pathname, router]);

  const sidebarNavItems: SidebarNavItem[] = [];
  if (me) {
    if (me.auth_kind === "account") {
      sidebarNavItems.push({
        href: "/onboarding",
        key: "onboardingNav",
        icon: Building2,
        match: (p) => p.startsWith("/onboarding"),
      });
    } else if (me.role === "applicant") {
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
        sidebarNavItems.push({
          href: "/hours",
          key: "hoursNav",
          icon: Clock,
          match: (p) => p === "/hours",
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
          href: "/my-hours",
          key: "myHoursNav",
          icon: Clock,
          match: (p) => p.startsWith("/my-hours"),
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
    if (!me || !isUserSession(me) || slug === me.organization.slug) return;
    setOrgSwitchBusy(true);
    try {
      const updated = await apiFetch<MeUser>("/api/v1/auth/me/active-organization", {
        method: "POST",
        body: JSON.stringify({ organization_slug: slug }),
      });
      await refreshMe();
      const next = membershipDefaultPath(updated);
      if (!pathnameCompatibleWithMembership(pathname, updated)) {
        router.push(next);
      }
      router.refresh();
      setUserMenuOpen(false);
      setOrgMenuOpen(false);
    } catch {
      return;
    } finally {
      setOrgSwitchBusy(false);
    }
  }

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
                    {isUserSession(me)
                      ? me.organization.name.trim()
                        ? me.organization.name
                        : t(locale, "emptyValue")
                      : me.email}
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
                {isUserSession(me)
                  ? me.organization.name.trim()
                    ? me.organization.name
                    : t(locale, "emptyValue")
                  : t(locale, "onboardingHeaderSubtitle")}
              </p>
            ) : (
              <p className="truncate text-xs text-slate-500">{t(locale, "aiFirst")}</p>
            )}
          </div>
          {!loading && me && isUserSession(me) && (me.memberships ?? []).length > 1 ? (
            <DropdownMenu
              open={orgMenuOpen}
              onOpenChange={(next) => {
                setOrgMenuOpen(next);
                if (next) {
                  setUserMenuOpen(false);
                }
              }}
            >
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  aria-label={t(locale, "organizationSwitcherButton")}
                  title={t(locale, "organizationSwitcherButton")}
                  className="inline-flex h-10 max-w-[min(100%,18rem)] shrink-0 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 text-left text-sm font-medium text-slate-800 shadow-sm sm:gap-2 sm:px-3"
                >
                  <Building2 aria-hidden className="h-4 w-4 shrink-0 text-emerald-700" />
                  <span className="hidden min-w-0 truncate sm:inline">
                    {me.organization.name.trim() ? me.organization.name : me.organization.slug}
                  </span>
                  <span className="min-w-0 truncate sm:hidden">{t(locale, "organizationSwitcherButtonShort")}</span>
                  <ChevronDown
                    aria-hidden
                    className={`h-4 w-4 shrink-0 text-slate-500 transition-transform ${orgMenuOpen ? "rotate-180" : ""}`}
                  />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="end"
                aria-label={t(locale, "organizationSwitcherMenuAria")}
                className="max-h-[min(70vh,24rem)] w-[min(calc(100vw-2rem),20rem)] overflow-y-auto py-2"
              >
                <DropdownMenuLabel>{t(locale, "organizationSwitcherLabel")}</DropdownMenuLabel>
                <OrgMembershipRows
                  locale={locale}
                  me={me}
                  orgSwitchBusy={orgSwitchBusy}
                  onPick={(slug) => void switchOrganization(slug)}
                />
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
          {!loading && me ? (
            <DropdownMenu
              open={userMenuOpen}
              onOpenChange={(next) => {
                setUserMenuOpen(next);
                if (next) {
                  setOrgMenuOpen(false);
                }
              }}
            >
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  aria-label={t(locale, "userMenuAriaLabel")}
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-emerald-600 text-sm font-semibold uppercase text-white shadow-md ring-2 ring-white transition hover:bg-emerald-700"
                >
                  {me.email.trim().charAt(0) || "?"}
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                {isUserSession(me) && (me.memberships ?? []).length > 0 ? (
                  <>
                    <DropdownMenuLabel>{t(locale, "organizationSwitcherLabel")}</DropdownMenuLabel>
                    <OrgMembershipRows
                      locale={locale}
                      me={me}
                      orgSwitchBusy={orgSwitchBusy}
                      onPick={(slug) => void switchOrganization(slug)}
                    />
                    <DropdownMenuSeparator />
                  </>
                ) : null}
                <DropdownMenuItem asChild>
                  <Link href="/settings" className="text-slate-800">
                    <Settings aria-hidden size={16} className="text-slate-500" />
                    {t(locale, "settings")}
                  </Link>
                </DropdownMenuItem>
                <DropdownMenuItem className="text-slate-800" onSelect={() => setLocale(locale === "de" ? "en" : "de")}>
                  <Languages aria-hidden size={16} className="text-slate-500" />
                  {t(locale, "language")}: {locale.toUpperCase()}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem className="font-medium text-red-700 focus:bg-red-50" onSelect={() => void logout()}>
                  <LogOut aria-hidden size={16} />
                  {t(locale, "logout")}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
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
        <main className="mx-auto w-full min-w-0 max-w-7xl flex-1 px-4 py-6">{children}</main>
      </div>
    </div>
  );
}
