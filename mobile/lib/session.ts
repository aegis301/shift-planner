import type { AccountSessionRead, UserRead } from "@shift-planner/api-client";

export type MemberSession = UserRead | AccountSessionRead;

export type SessionOutcome = "member" | "no-member" | "onboarding";

export function sessionOutcome(session: MemberSession): SessionOutcome {
  if (session.auth_kind !== "user" || !("capabilities" in session)) {
    return "onboarding";
  }
  if (session.role === "applicant") {
    return "onboarding";
  }
  if (session.capabilities.team_member_portal && session.team_member_id != null) {
    return "member";
  }
  return "no-member";
}

export function userSession(session: MemberSession | null): UserRead | null {
  if (session && session.auth_kind === "user" && "capabilities" in session) {
    return session;
  }
  return null;
}
