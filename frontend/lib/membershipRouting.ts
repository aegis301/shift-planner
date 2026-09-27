import type { Locale } from "@/lib/i18n";
import type { MeAccountSession, MeUser, SessionMe } from "@/components/LocaleProvider";
import { t, type TranslationKey } from "@/lib/i18n";

export function isUserSession(me: SessionMe | null | undefined): me is MeUser {
  return me != null && me.auth_kind === "user";
}

export function isAccountSession(me: SessionMe | null | undefined): me is MeAccountSession {
  return me != null && me.auth_kind === "account";
}

export function membershipDefaultPath(me: SessionMe): string {
  if (me.auth_kind === "account") {
    return "/onboarding";
  }
  if (me.role === "applicant") {
    return "/pending-onboarding";
  }
  if (me.capabilities.planning) {
    return "/planning";
  }
  if (me.capabilities.team_member_portal) {
    return "/my";
  }
  return "/";
}

export function pathnameCompatibleWithMembership(pathname: string, me: SessionMe): boolean {
  const p = pathname === "" ? "/" : pathname;
  if (me.auth_kind === "account") {
    return p.startsWith("/onboarding") || p.startsWith("/settings");
  }
  if (me.role === "applicant") {
    return p.startsWith("/pending-onboarding") || p.startsWith("/settings");
  }
  if (p.startsWith("/onboarding")) {
    return false;
  }
  if (p.startsWith("/pending-onboarding")) {
    return false;
  }
  if (p === "/") {
    return me.capabilities.planning || me.capabilities.admin || !me.capabilities.team_member_portal;
  }
  if (p.startsWith("/planning")) {
    return me.capabilities.planning;
  }
  if (p.startsWith("/hours") && !p.startsWith("/hours/")) {
    return me.capabilities.planning;
  }
  if (p === "/my" || p.startsWith("/my/")) {
    return me.capabilities.team_member_portal;
  }
  if (p.startsWith("/my-hours") || p.startsWith("/my-planning") || p.startsWith("/profile")) {
    return me.capabilities.team_member_portal;
  }
  if (p.startsWith("/organization")) {
    return me.capabilities.admin;
  }
  return true;
}

const roleTranslationKeys: Record<string, TranslationKey> = {
  admin: "roleOptionAdmin",
  planner: "roleOptionPlanner",
  team_member: "roleOptionTeamMember",
  applicant: "roleOptionApplicant",
};

export function membershipRoleLabel(locale: Locale, role: string): string {
  const key = roleTranslationKeys[role];
  if (key) {
    return t(locale, key);
  }
  return role;
}
