import { describe, expect, it } from "vitest";
import { rosterSyncSummary } from "@/lib/organizationHolidays";

const empty = {
  planning_period_ids: [],
  slots_updated: 0,
  slots_added: 0,
  slots_removed: 0,
  assignments_kept: 0,
  assignments_cleared: 0,
  skipped_published: []
};

describe("rosterSyncSummary", () => {
  it("says nothing changed when no roster was touched", () => {
    expect(rosterSyncSummary("en", empty)).toEqual(["No existing rosters affected."]);
  });

  it("counts changed shifts and kept or cleared assignments", () => {
    expect(
      rosterSyncSummary("en", { ...empty, slots_updated: 2, slots_removed: 1, assignments_kept: 2, assignments_cleared: 1 })
    ).toEqual(["Existing rosters updated: 3 shifts changed, 2 assignments kept, 1 removed."]);
  });

  it("names published groups that were left alone", () => {
    const lines = rosterSyncSummary("de", {
      ...empty,
      skipped_published: [
        { planning_period_id: 4, year: 2026, month: 9, shift_group_id: 1, shift_group_name: "Anästhesie" }
      ]
    });
    expect(lines).toHaveLength(1);
    expect(lines[0]).toContain("Anästhesie (09/2026)");
  });
});
