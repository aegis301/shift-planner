import { describe, expect, it } from "vitest";
import { readWorkbenchSelection, selectionQuery } from "@/lib/workbenchSelection";

describe("workbench selection", () => {
  it("reads period, group, tab, and the selected slot from the URL", () => {
    const selection = readWorkbenchSelection(new URLSearchParams("period=4&shiftGroup=2&tab=roster&slot=9"));
    expect(selection).toMatchObject({ period: "4", shiftGroup: "2", tab: "roster", slot: "9", member: "", day: "" });
  });

  it("keeps the current search when one selection changes", () => {
    const current = new URLSearchParams("period=4&shiftGroup=2&tab=wishes");
    expect(selectionQuery(current, { slot: "9", tab: "roster", member: null })).toBe("period=4&shiftGroup=2&tab=roster&slot=9");
  });
});
