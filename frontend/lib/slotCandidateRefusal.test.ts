import { describe, expect, it } from "vitest";
import { slotCandidateRefusalLabel } from "@/lib/slotCandidateRefusal";

describe("slot candidate refusal label", () => {
  it("names each refusal reason in both locales", () => {
    const codes = ["not_on_period_roster", "not_in_covering_group", "no_go", "unavailable_day_status"] as const;
    for (const code of codes) {
      const de = slotCandidateRefusalLabel("de", { code });
      const en = slotCandidateRefusalLabel("en", { code });
      expect(de).toBeTruthy();
      expect(en).toBeTruthy();
      expect(de).not.toEqual(en);
    }
  });

  it("puts the rule code into a blocking rule reason", () => {
    expect(
      slotCandidateRefusalLabel("en", { code: "blocking_rule", rule_code: "ROSTER_CONSTRAINT_MIN_REST_HOURS" })
    ).toBe("Blocked by rule ROSTER_CONSTRAINT_MIN_REST_HOURS");
    expect(slotCandidateRefusalLabel("en", { code: "blocking_rule" })).toBe("Blocked by a rule");
  });

  it("returns null without a refusal", () => {
    expect(slotCandidateRefusalLabel("de", null)).toBeNull();
    expect(slotCandidateRefusalLabel("de", undefined)).toBeNull();
  });
});
