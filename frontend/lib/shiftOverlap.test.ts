import { describe, expect, it } from "vitest";
import { inferEndDayOffset, overlapCalendarDaysForSlot } from "@/lib/shiftOverlap";

describe("inferEndDayOffset", () => {
  it("stays on the same day when the end is later", () => {
    expect(inferEndDayOffset("08:00", "16:30")).toBe(0);
  });

  it("rolls to the next day when the end is earlier or the same clock time", () => {
    expect(inferEndDayOffset("22:00", "06:00")).toBe(1);
    expect(inferEndDayOffset("08:00", "08:00")).toBe(1);
    expect(inferEndDayOffset("8:00", "7:59")).toBe(1);
  });

  it("returns zero when a time cannot be parsed", () => {
    expect(inferEndDayOffset("nope", "08:00")).toBe(0);
  });
});

describe("overlapCalendarDaysForSlot", () => {
  it("returns nothing without a slot date", () => {
    expect(overlapCalendarDaysForSlot({ slot_date: "" })).toEqual([]);
  });

  it("returns the slot date when times are missing", () => {
    expect(overlapCalendarDaysForSlot({ slot_date: "2026-10-01" })).toEqual(["2026-10-01"]);
  });

  it("stays on one day for a daytime wall-clock shift", () => {
    expect(
      overlapCalendarDaysForSlot({
        slot_date: "2026-10-01",
        starts_at: "08:00",
        ends_at: "16:00"
      })
    ).toEqual(["2026-10-01"]);
  });

  it("includes the next day when wall-clock times cross midnight", () => {
    expect(
      overlapCalendarDaysForSlot({
        slot_date: "2026-10-01",
        starts_at: "20:00",
        ends_at: "08:00"
      })
    ).toEqual(["2026-10-01", "2026-10-02"]);
  });

  it("uses an explicit end-day offset instead of inferring one", () => {
    expect(
      overlapCalendarDaysForSlot({
        slot_date: "2026-10-01",
        starts_at: "08:00",
        ends_at: "16:00",
        end_day_offset: 2
      })
    ).toEqual(["2026-10-01", "2026-10-02", "2026-10-03"]);
    expect(
      overlapCalendarDaysForSlot({
        slot_date: "2026-10-01",
        starts_at: "20:00",
        ends_at: "08:00",
        end_day_offset: 0
      })
    ).toEqual(["2026-10-01"]);
  });

  it("derives the end day from UTC instants in Europe/Berlin", () => {
    expect(
      overlapCalendarDaysForSlot(
        {
          slot_date: "2026-10-01",
          starts_at: "2026-10-01T20:00:00Z",
          ends_at: "2026-10-02T04:00:00Z"
        },
        "Europe/Berlin"
      )
    ).toEqual(["2026-10-01", "2026-10-02"]);
  });
});
