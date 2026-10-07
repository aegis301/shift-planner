import { describe, expect, it } from "vitest";
import {
  anyShiftNoGoWrites,
  bandWrite,
  dayTemplateOptions,
  effectiveKind,
  intentBandCoversSlot,
  isAnyShiftNoGo,
  type DayIntent
} from "@/lib/wishesDay";

const templates = [
  { id: 1, name: "Bereitschaftsdienst", is_active: true },
  { id: 2, name: "Spätdienst", is_active: true },
  { id: 3, name: "Alt", is_active: false }
];

const slotDays = [
  { cell_date: "2026-10-10", shift_template_id: 1, shift_group_id: 5, has_day: true, has_night: true },
  { cell_date: "2026-10-12", shift_template_id: 1, shift_group_id: 5, has_day: false, has_night: true },
  { cell_date: "2026-10-12", shift_template_id: 2, shift_group_id: 5, has_day: true, has_night: false },
  { cell_date: "2026-10-12", shift_template_id: 3, shift_group_id: 5, has_day: true, has_night: false },
  { cell_date: "2026-10-12", shift_template_id: 2, shift_group_id: 6, has_day: true, has_night: false }
];

const bd = { templateId: 1, shiftGroupId: 5 };

function intent(band: "all" | "day" | "night", kind: "wish" | "no_go", templateId = 1): DayIntent {
  return { team_member_id: 9, cell_date: "2026-10-10", shift_group_id: 5, shift_template_id: templateId, band, kind };
}

describe("shifts that run on a day", () => {
  it("lists only templates with a slot that day, and marks day/night splits", () => {
    expect(dayTemplateOptions(slotDays, templates, "2026-10-10", 5)).toEqual([
      { templateId: 1, shiftGroupId: 5, name: "Bereitschaftsdienst", split: true }
    ]);
    expect(dayTemplateOptions(slotDays, templates, "2026-10-12", 5)).toEqual([
      { templateId: 1, shiftGroupId: 5, name: "Bereitschaftsdienst", split: false },
      { templateId: 2, shiftGroupId: 5, name: "Spätdienst", split: false }
    ]);
  });
});

describe("band kinds", () => {
  it("falls back to the whole-day row for a band without its own row", () => {
    const intents = [intent("all", "no_go"), intent("night", "wish")];
    expect(effectiveKind(intents, 9, "2026-10-10", bd, "day")).toBe("no_go");
    expect(effectiveKind(intents, 9, "2026-10-10", bd, "night")).toBe("wish");
    expect(effectiveKind([], 9, "2026-10-10", bd, "night")).toBeNull();
  });

  it("stores one whole-day row when both bands get the same kind", () => {
    expect(bandWrite([intent("day", "no_go")], 9, "2026-10-10", bd, "night", "no_go").band).toBe("all");
    expect(bandWrite([intent("day", "wish")], 9, "2026-10-10", bd, "night", "no_go").band).toBe("night");
    expect(bandWrite([], 9, "2026-10-10", bd, "night", null).band).toBe("all");
    expect(bandWrite([intent("all", "no_go")], 9, "2026-10-10", bd, "night", null)).toEqual({
      team_member_id: 9,
      cell_date: "2026-10-10",
      shift_group_id: 5,
      shift_template_id: 1,
      band: "night",
      kind: null
    });
  });
});

describe("no-go for every shift", () => {
  const options = dayTemplateOptions(slotDays, templates, "2026-10-12", 5);

  it("writes a whole-day no-go for each shift that runs that day", () => {
    expect(anyShiftNoGoWrites(options, 9, "2026-10-12", true).map((row) => [row.shift_template_id, row.band, row.kind])).toEqual([
      [1, "all", "no_go"],
      [2, "all", "no_go"]
    ]);
    expect(anyShiftNoGoWrites(options, 9, "2026-10-12", false).every((row) => row.kind === null)).toBe(true);
  });

  it("is set only when every shift of the day is a no-go", () => {
    const day = (templateId: number, band: "all" | "day" | "night"): DayIntent => ({
      ...intent(band, "no_go", templateId),
      cell_date: "2026-10-12"
    });
    expect(isAnyShiftNoGo([day(1, "all")], options, 9, "2026-10-12")).toBe(false);
    expect(isAnyShiftNoGo([day(1, "all"), day(2, "all")], options, 9, "2026-10-12")).toBe(true);
    const weekend = dayTemplateOptions(slotDays, templates, "2026-10-10", 5);
    expect(isAnyShiftNoGo([intent("day", "no_go"), intent("night", "no_go")], weekend, 9, "2026-10-10")).toBe(true);
    expect(isAnyShiftNoGo([], [], 9, "2026-10-10")).toBe(false);
  });
});

describe("intent band on a roster slot", () => {
  it("matches whole-day intents to every slot and band intents to their band", () => {
    expect(intentBandCoversSlot(undefined, true)).toBe(true);
    expect(intentBandCoversSlot("all", false)).toBe(true);
    expect(intentBandCoversSlot("night", true)).toBe(true);
    expect(intentBandCoversSlot("night", false)).toBe(false);
    expect(intentBandCoversSlot("day", true)).toBe(false);
  });
});
