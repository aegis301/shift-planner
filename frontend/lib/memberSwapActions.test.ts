import { describe, expect, it } from "vitest";
import { isActionableMemberSwap } from "@/lib/memberSwapActions";

const memberId = 7;

describe("isActionableMemberSwap", () => {
  it("counts claimable giveaways and the member's own live requests", () => {
    expect(
      isActionableMemberSwap(
        { kind: "giveaway", status: "open", offered_by_team_member_id: 3, target_team_member_id: null },
        memberId
      )
    ).toBe(true);
    expect(
      isActionableMemberSwap(
        { kind: "giveaway", status: "open", offered_by_team_member_id: memberId, target_team_member_id: null },
        memberId
      )
    ).toBe(true);
    expect(
      isActionableMemberSwap(
        { kind: "exchange", status: "targeted", offered_by_team_member_id: 3, target_team_member_id: memberId },
        memberId
      )
    ).toBe(true);
  });

  it("ignores terminal rows and other people's requests", () => {
    for (const status of ["applied", "withdrawn", "rejected", "expired"]) {
      expect(
        isActionableMemberSwap(
          { kind: "giveaway", status, offered_by_team_member_id: memberId, target_team_member_id: null },
          memberId
        )
      ).toBe(false);
    }
    expect(
      isActionableMemberSwap(
        { kind: "exchange", status: "accepted", offered_by_team_member_id: 3, target_team_member_id: 9 },
        memberId
      )
    ).toBe(false);
    expect(
      isActionableMemberSwap(
        { kind: "giveaway", status: "open", offered_by_team_member_id: 3, target_team_member_id: null },
        null
      )
    ).toBe(false);
  });
});
