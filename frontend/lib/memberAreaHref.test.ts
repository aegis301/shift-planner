import { describe, expect, it } from "vitest";
import { memberAreaHref } from "@/lib/memberAreaHref";

describe("memberAreaHref", () => {
  it("keeps period and shift group on member planning tabs", () => {
    const search = new URLSearchParams("period=12&shiftGroup=4&tab=roster");
    expect(memberAreaHref("/my-planning", search)).toBe("/my-planning?period=12&shiftGroup=4");
    expect(memberAreaHref("/my-planning", search, "roster")).toBe("/my-planning?period=12&shiftGroup=4&tab=roster");
    expect(memberAreaHref("/my-planning", search, "shifts")).toBe("/my-planning?period=12&shiftGroup=4&tab=shifts");
  });

  it("keeps the planning scope on home, hours, and profile", () => {
    const search = new URLSearchParams("period=12&shiftGroup=4&tab=shifts");
    expect(memberAreaHref("/my", search)).toBe("/my?period=12&shiftGroup=4");
    expect(memberAreaHref("/my-hours", search)).toBe("/my-hours?period=12&shiftGroup=4");
    expect(memberAreaHref("/profile", search)).toBe("/profile?period=12&shiftGroup=4");
  });
});
