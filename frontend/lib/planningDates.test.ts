import { describe, expect, it } from "vitest";
import {
  expandInclusiveDateRange,
  formatIsoDate,
  isoDateRangesOverlap,
  isoDateRangeStatus,
  monthDateBounds
} from "@/lib/planningDates";

describe("monthDateBounds", () => {
  it("covers a 31-day month and a non-leap February", () => {
    expect(monthDateBounds(2026, 10)).toEqual({ min: "2026-10-01", max: "2026-10-31" });
    expect(monthDateBounds(2026, 2)).toEqual({ min: "2026-02-01", max: "2026-02-28" });
  });

  it("includes 29 February in a leap year", () => {
    expect(monthDateBounds(2024, 2)).toEqual({ min: "2024-02-01", max: "2024-02-29" });
  });
});

describe("expandInclusiveDateRange", () => {
  it("lists every day from the start through the end", () => {
    expect(expandInclusiveDateRange("2026-10-30", "2026-11-01")).toEqual([
      "2026-10-30",
      "2026-10-31",
      "2026-11-01"
    ]);
  });

  it("returns nothing when the range is reversed or not a date", () => {
    expect(expandInclusiveDateRange("2026-10-03", "2026-10-01")).toEqual([]);
    expect(expandInclusiveDateRange("not-a-date", "2026-10-01")).toEqual([]);
  });
});

describe("isoDateRangesOverlap", () => {
  it("treats a shared boundary day as an overlap", () => {
    expect(isoDateRangesOverlap("2026-01-01", "2026-01-10", "2026-01-10", "2026-01-20")).toBe(true);
  });

  it("rejects ranges that only meet after one has ended", () => {
    expect(isoDateRangesOverlap("2026-01-01", "2026-01-10", "2026-01-11", "2026-01-20")).toBe(false);
  });

  it("treats a missing end as open", () => {
    expect(isoDateRangesOverlap("2026-03-01", "2026-03-10", "2026-01-01", null)).toBe(true);
    expect(isoDateRangesOverlap("2026-01-01", null, "2025-01-01", "2025-12-31")).toBe(false);
  });
});

describe("isoDateRangeStatus", () => {
  const onDate = "2026-06-15";

  it("classifies planned, ended, and active ranges against the given day", () => {
    expect(isoDateRangeStatus("2026-07-01", null, onDate)).toBe("planned");
    expect(isoDateRangeStatus("2026-01-01", "2026-06-01", onDate)).toBe("ended");
    expect(isoDateRangeStatus("2026-01-01", "2026-12-01", onDate)).toBe("active");
    expect(isoDateRangeStatus("2026-06-15", "2026-06-15", onDate)).toBe("active");
    expect(isoDateRangeStatus("2026-01-01", null, onDate)).toBe("active");
  });
});

describe("formatIsoDate", () => {
  it("formats German and English dates and returns the input when it is not a date", () => {
    expect(formatIsoDate("2026-10-01", "de")).toBe("01.10.2026");
    expect(formatIsoDate("2026-10-01", "en")).toBe("01/10/2026");
    expect(formatIsoDate("not-a-date", "de")).toBe("not-a-date");
  });
});
