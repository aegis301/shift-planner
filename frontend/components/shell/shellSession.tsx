"use client";

import Link from "next/link";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { Building2, ChevronDown, Languages, LogOut, Settings } from "lucide-react";
import { useSession, type MeUser, type SessionMe } from "@/components/LocaleProvider";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger
} from "@/components/ui/dropdown-menu";
import { apiFetch } from "@/lib/api";
import { Locale, t } from "@/lib/i18n";
import {
  isUserSession,
  membershipDefaultPath,
  membershipRoleLabel,
  pathnameCompatibleWithMembership
} from "@/lib/membershipRouting";
import { clearOrganizationCache } from "@/lib/queries/invalidation";

export function useShellSession(locale: Locale, setLocale: (locale: Locale) => void) {
  const pathname = usePathname();
  const router = useRouter();
  const { me, loading, refreshMe } = useSession();
  const queryClient = useQueryClient();
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [orgMenuOpen, setOrgMenuOpen] = useState(false);
  const [orgSwitchBusy, setOrgSwitchBusy] = useState(false);

  async function logout() {
    try {
      await apiFetch("/api/v1/auth/logout", { method: "POST" });
    } catch {
      return;
    }
    clearOrganizationCache(queryClient);
    await refreshMe();
    router.push("/login");
    router.refresh();
  }

  async function switchOrganization(slug: string) {
    if (!me || !isUserSession(me) || slug === me.organization.slug) {
      return;
    }
    setOrgSwitchBusy(true);
    try {
      const updated = await apiFetch<MeUser>("/api/v1/auth/me/active-organization", {
        method: "POST",
        body: JSON.stringify({ organization_slug: slug })
      });
      clearOrganizationCache(queryClient);
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

  return {
    me,
    loading,
    pathname,
    router,
    userMenuOpen,
    setUserMenuOpen,
    orgMenuOpen,
    setOrgMenuOpen,
    orgSwitchBusy,
    logout,
    switchOrganization,
    locale,
    setLocale
  };
}

function OrgMembershipRows({
  locale,
  me,
  orgSwitchBusy,
  onPick
}: {
  locale: Locale;
  me: MeUser;
  orgSwitchBusy: boolean;
  onPick: (slug: string) => void;
}) {
  return (
    <>
      {(me.memberships ?? []).map((membership) => {
        const activeOrg = membership.organization.id === me.organization_id;
        return (
          <DropdownMenuItem
            key={membership.membership_id}
            disabled={activeOrg || orgSwitchBusy}
            className={`flex-col items-start gap-0.5 rounded-lg px-2 py-2 text-sm ${
              activeOrg ? "bg-slate-100 text-slate-900" : "text-slate-800"
            }`}
            onSelect={() => {
              if (!activeOrg && !orgSwitchBusy) {
                onPick(membership.organization.slug);
              }
            }}
          >
            <span className="font-medium">
              {membership.organization.name.trim() ? membership.organization.name : membership.organization.slug}
            </span>
            <span className="font-mono text-xs text-slate-500">{membership.organization.slug}</span>
            <span className="text-xs text-slate-600">{membershipRoleLabel(locale, membership.role)}</span>
          </DropdownMenuItem>
        );
      })}
    </>
  );
}

export function ShellHeaderMenus({
  session,
  areaSwitch
}: {
  session: ReturnType<typeof useShellSession>;
  areaSwitch?: { href: string; label: string };
}) {
  const { me, loading, locale, setLocale, orgMenuOpen, setOrgMenuOpen, userMenuOpen, setUserMenuOpen, orgSwitchBusy, switchOrganization, logout } =
    session;
  return (
    <>
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
              className="inline-flex h-11 max-w-[min(100%,18rem)] shrink-0 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 text-left text-sm font-medium text-slate-800 shadow-sm"
            >
              <Building2 aria-hidden className="h-4 w-4 shrink-0 text-emerald-700" />
              <span className="hidden min-w-0 truncate sm:inline">
                {me.organization.name.trim() ? me.organization.name : me.organization.slug}
              </span>
              <span className="min-w-0 truncate sm:hidden">{t(locale, "organizationSwitcherButtonShort")}</span>
              <ChevronDown aria-hidden className={`h-4 w-4 shrink-0 text-slate-500 ${orgMenuOpen ? "rotate-180" : ""}`} />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" aria-label={t(locale, "organizationSwitcherMenuAria")} className="w-80">
            <DropdownMenuLabel>{t(locale, "organizationSwitcherLabel")}</DropdownMenuLabel>
            <OrgMembershipRows locale={locale} me={me} orgSwitchBusy={orgSwitchBusy} onPick={(slug) => void switchOrganization(slug)} />
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
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-emerald-600 text-sm font-semibold uppercase text-white shadow-md ring-2 ring-white"
            >
              {me.email.trim().charAt(0) || "?"}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            {areaSwitch ? (
              <DropdownMenuItem asChild>
                <Link href={areaSwitch.href}>{areaSwitch.label}</Link>
              </DropdownMenuItem>
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
            <DropdownMenuItem className="font-medium text-red-700" onSelect={() => void logout()}>
              <LogOut aria-hidden size={16} />
              {t(locale, "logout")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ) : !loading ? (
        <Link href="/login" className="inline-flex h-11 items-center rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700">
          {t(locale, "login")}
        </Link>
      ) : null}
    </>
  );
}

export function useAreaGuard() {
  const pathname = usePathname();
  const router = useRouter();
  const { me, loading } = useSession();
  return { pathname, router, me, loading, redirect: !loading && me != null && !pathnameCompatibleWithMembership(pathname, me) };
}

export type { SessionMe };
