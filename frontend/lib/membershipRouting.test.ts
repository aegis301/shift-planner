import { describe, expect, it } from "vitest";
import type { MeAccountSession, MeUser } from "@/components/LocaleProvider";
import {
  membershipDefaultPath,
  membershipRoleLabel,
  pathnameCompatibleWithMembership
} from "@/lib/membershipRouting";

const organization = { id: 1, name: "Org", slug: "org", plan_tier: "team" };

function user(overrides: Partial<MeUser> = {}): MeUser {
  return {
    auth_kind: "user",
    id: 1,
    email: "person@example.com",
    role: "team_member",
    locale: "de",
    organization_id: 1,
    organization,
    team_member_id: null,
    shift_groups: [],
    planner_shift_groups: [],
    capabilities: { admin: false, planning: false, team_member_portal: false },
    memberships: [],
    organization_timezone: "Europe/Berlin",
    ...overrides
  };
}

function account(): MeAccountSession {
  return {
    auth_kind: "account",
    email: "new@example.com",
    locale: "de",
    memberships: []
  };
}

describe("membershipDefaultPath", () => {
  it("sends an account session to onboarding", () => {
    expect(membershipDefaultPath(account())).toBe("/onboarding");
  });

  it("sends an applicant to pending onboarding even when planning is set", () => {
    expect(
      membershipDefaultPath(
        user({
          role: "applicant",
          capabilities: { admin: false, planning: true, team_member_portal: false }
        })
      )
    ).toBe("/pending-onboarding");
  });

  it("prefers planning over the member portal", () => {
    expect(
      membershipDefaultPath(
        user({
          role: "planner",
          capabilities: { admin: false, planning: true, team_member_portal: true }
        })
      )
    ).toBe("/planning");
  });

  it("sends a team member to my planning and anyone else home", () => {
    expect(
      membershipDefaultPath(
        user({
          capabilities: { admin: false, planning: false, team_member_portal: true }
        })
      )
    ).toBe("/my-planning");
    expect(membershipDefaultPath(user())).toBe("/");
  });
});

describe("pathnameCompatibleWithMembership", () => {
  const admin = user({
    role: "admin",
    capabilities: { admin: true, planning: true, team_member_portal: false }
  });
  const planner = user({
    role: "planner",
    capabilities: { admin: false, planning: true, team_member_portal: false }
  });
  const plannerMember = user({
    role: "planner",
    team_member_id: 4,
    capabilities: { admin: false, planning: true, team_member_portal: true }
  });
  const member = user({
    role: "team_member",
    team_member_id: 4,
    capabilities: { admin: false, planning: false, team_member_portal: true }
  });
  const applicant = user({ role: "applicant" });

  it("limits an account session to onboarding and settings", () => {
    const session = account();
    expect(pathnameCompatibleWithMembership("/onboarding", session)).toBe(true);
    expect(pathnameCompatibleWithMembership("/settings", session)).toBe(true);
    expect(pathnameCompatibleWithMembership("/planning", session)).toBe(false);
    expect(pathnameCompatibleWithMembership("/", session)).toBe(false);
  });

  it("limits an applicant to pending onboarding and settings", () => {
    expect(pathnameCompatibleWithMembership("/pending-onboarding", applicant)).toBe(true);
    expect(pathnameCompatibleWithMembership("/settings", applicant)).toBe(true);
    expect(pathnameCompatibleWithMembership("/planning", applicant)).toBe(false);
    expect(pathnameCompatibleWithMembership("/my-planning", applicant)).toBe(false);
  });

  it("keeps onboarding routes closed for signed-in members", () => {
    expect(pathnameCompatibleWithMembership("/onboarding", admin)).toBe(false);
    expect(pathnameCompatibleWithMembership("/pending-onboarding", planner)).toBe(false);
  });

  it("gates planning, hours, the member area, and organization admin", () => {
    expect(pathnameCompatibleWithMembership("/planning", planner)).toBe(true);
    expect(pathnameCompatibleWithMembership("/hours", planner)).toBe(true);
    expect(pathnameCompatibleWithMembership("/organization/team", planner)).toBe(false);
    expect(pathnameCompatibleWithMembership("/my-planning", planner)).toBe(false);
    expect(pathnameCompatibleWithMembership("/my-hours", planner)).toBe(false);

    expect(pathnameCompatibleWithMembership("/organization/team", admin)).toBe(true);
    expect(pathnameCompatibleWithMembership("/planning", admin)).toBe(true);

    expect(pathnameCompatibleWithMembership("/my-planning", member)).toBe(true);
    expect(pathnameCompatibleWithMembership("/profile", member)).toBe(true);
    expect(pathnameCompatibleWithMembership("/my-hours", member)).toBe(true);
    expect(pathnameCompatibleWithMembership("/planning", member)).toBe(false);
    expect(pathnameCompatibleWithMembership("/hours", member)).toBe(false);
    expect(pathnameCompatibleWithMembership("/organization", member)).toBe(false);

    expect(pathnameCompatibleWithMembership("/planning", plannerMember)).toBe(true);
    expect(pathnameCompatibleWithMembership("/hours", plannerMember)).toBe(true);
    expect(pathnameCompatibleWithMembership("/my-planning", plannerMember)).toBe(true);
    expect(pathnameCompatibleWithMembership("/profile", plannerMember)).toBe(true);
    expect(pathnameCompatibleWithMembership("/organization", plannerMember)).toBe(false);
  });

  it("treats an empty pathname as home and allows settings for a user", () => {
    expect(pathnameCompatibleWithMembership("", member)).toBe(true);
    expect(pathnameCompatibleWithMembership("/settings", member)).toBe(true);
  });
});

describe("membershipRoleLabel", () => {
  it("translates known roles and returns an unknown role unchanged", () => {
    expect(membershipRoleLabel("de", "planner")).toBe("Planer");
    expect(membershipRoleLabel("en", "team_member")).toBe("Team member");
    expect(membershipRoleLabel("de", "custom")).toBe("custom");
  });
});
