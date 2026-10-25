import type { AuthStatus } from "@/lib/auth";
import { sessionOutcome, type MemberSession, type SessionOutcome } from "@/lib/session";

export type AppRoute = "/sign-in" | "/(tabs)" | "/no-member" | "/onboarding";

const OUTCOME_ROUTES: Record<SessionOutcome, AppRoute> = {
  member: "/(tabs)",
  "no-member": "/no-member",
  onboarding: "/onboarding"
};

export function routeFor(status: AuthStatus, session: MemberSession | null): AppRoute | null {
  if (status === "loading") {
    return null;
  }
  if (status === "signed-out" || !session) {
    return "/sign-in";
  }
  return OUTCOME_ROUTES[sessionOutcome(session)];
}
