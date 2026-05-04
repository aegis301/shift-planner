import type { Locale } from "@/lib/i18n";
import type { MeUser } from "@/components/LocaleProvider";
import { t, type TranslationKey } from "@/lib/i18n";

export function membershipDefaultPath(user: MeUser): string {
  if (user.role === "applicant") {
    return "/pending-onboarding";
  }
  if (user.capabilities.planning) {
    return "/planning";
  }
  if (user.capabilities.team_member_portal) {
    return "/my-planning";
  }
  return "/";
}

export function pathnameCompatibleWithMembership(pathname: string, user: MeUser): boolean {
  const p = pathname === "" ? "/" : pathname;
  if (user.role === "applicant") {
    return p.startsWith("/pending-onboarding") || p.startsWith("/settings");
  }
  if (p.startsWith("/pending-onboarding")) {
    return false;
  }
  if (p.startsWith("/planning")) {
    return user.capabilities.planning;
  }
  if (p.startsWith("/my-planning") || p.startsWith("/profile")) {
    return user.capabilities.team_member_portal;
  }
  if (p.startsWith("/organization")) {
    return user.capabilities.admin;
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
