import { describe, expect, it } from "vitest";
import { isTypingTarget, workbenchShortcuts } from "@/lib/shortcuts";

describe("workbench shortcuts", () => {
  it("declares the initial set once", () => {
    expect(workbenchShortcuts.map((row) => row.id)).toEqual([
      "palette",
      "help",
      "previous-period",
      "next-period",
      "tab-wishes",
      "tab-roster",
      "tab-analysis",
      "inspector",
      "clear"
    ]);
  });

  it("ignores shortcuts while typing", () => {
    expect(isTypingTarget(document.createElement("input"))).toBe(true);
    expect(isTypingTarget(document.createElement("div"))).toBe(false);
  });
});
