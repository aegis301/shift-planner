import { describe, expect, it } from "vitest";
import { columnHeader, rosterGridColumns, slotForColumn, slotsForColumn, stepWithinStack } from "@/lib/rosterColumns";

const templates = [{ id: 8, code: "BD", name: "Bereit", category: "bereitschaftsdienst", display_order: 1 }];

describe("roster columns", () => {
  it("makes one column per template position", () => {
    const columns = rosterGridColumns(
      [
        { id: 1, slot_date: "2026-10-01", shift_template_id: 8, position: 1, template_code: "BD" },
        { id: 2, slot_date: "2026-10-01", shift_template_id: 8, position: 2, template_code: "BD" },
        { id: 3, slot_date: "2026-10-02", shift_template_id: 8, position: 1, template_code: "BD" },
        { id: 4, slot_date: "2026-10-01", shift_template_id: 9, position: 1, template_code: "RD" }
      ],
      [
        { id: 9, code: "RD", name: "Ruf", category: "rufdienst", display_order: 2 },
        { id: 8, code: "BD", name: "Bereit", category: "bereitschaftsdienst", display_order: 1 }
      ]
    );
    expect(columns.map((column) => columnHeader(column))).toEqual(["BD #1", "BD #2", "RD #1"]);
    expect(
      slotForColumn(
        [
          { id: 2, slot_date: "2026-10-01", shift_template_id: 8, position: 2 },
          { id: 1, slot_date: "2026-10-01", shift_template_id: 8, position: 1 }
        ],
        "2026-10-01",
        columns[1]
      )?.id
    ).toBe(2);
    expect(slotForColumn([], "2026-10-03", columns[1])).toBeNull();
  });

  it("collapses weekday and weekend variants into one template column", () => {
    const slots = [
      slot(1, "2026-10-01", 11, "weekday", "2026-10-01T06:00:00Z", "2026-10-01T14:00:00Z"),
      slot(2, "2026-10-03", 12, "weekend", "2026-10-03T06:00:00Z", "2026-10-03T14:00:00Z")
    ];
    const columns = rosterGridColumns(slots, templates, "template");
    expect(columns.map((column) => columnHeader(column))).toEqual(["BD #1"]);
    expect(slotsForColumn(slots, "2026-10-01", columns[0]).map((row) => row.id)).toEqual([1]);
    expect(slotsForColumn(slots, "2026-10-03", columns[0]).map((row) => row.id)).toEqual([2]);
  });

  it("stacks a weekend day shift and night shift, and splits them into two columns", () => {
    const slots = [
      slot(1, "2026-10-03", 21, "Tag", "2026-10-03T06:00:00Z", "2026-10-03T14:00:00Z"),
      slot(2, "2026-10-03", 22, "Nacht", "2026-10-03T18:00:00Z", "2026-10-04T04:00:00Z"),
      slot(3, "2026-10-04", 21, "Tag", "2026-10-04T06:00:00Z", "2026-10-04T14:00:00Z")
    ];
    const stacked = rosterGridColumns(slots, templates, "template");
    expect(stacked.map((column) => columnHeader(column))).toEqual(["BD #1"]);
    expect(slotsForColumn(slots, "2026-10-03", stacked[0]).map((row) => row.id)).toEqual([1, 2]);
    expect(slotsForColumn(slots, "2026-10-05", stacked[0])).toEqual([]);

    const split = rosterGridColumns(slots, templates, "day-night");
    expect(split.map((column) => columnHeader(column))).toEqual(["BD Tag #1", "BD Nacht #1"]);
    expect(slotForColumn(slots, "2026-10-03", split[0])?.id).toBe(1);
    expect(slotForColumn(slots, "2026-10-03", split[1])?.id).toBe(2);
    expect(slotForColumn(slots, "2026-10-04", split[1])).toBeNull();
  });

  it("keeps a template that never has both day and night as one column", () => {
    const slots = [
      slot(1, "2026-10-01", 11, "weekday", "2026-10-01T06:00:00Z", "2026-10-01T14:00:00Z"),
      slot(2, "2026-10-03", 12, "weekend", "2026-10-03T07:00:00Z", "2026-10-03T15:00:00Z")
    ];
    const columns = rosterGridColumns(slots, templates, "day-night");
    expect(columns.map((column) => columnHeader(column))).toEqual(["BD #1"]);
  });

  it("keeps variant headers unchanged", () => {
    const slots = [
      slot(1, "2026-10-03", 21, "Tag", "2026-10-03T06:00:00Z", "2026-10-03T14:00:00Z"),
      slot(2, "2026-10-03", 22, "Nacht", "2026-10-03T18:00:00Z", "2026-10-04T04:00:00Z"),
      slot(3, "2026-10-04", 21, "Tag", "2026-10-04T06:00:00Z", "2026-10-04T14:00:00Z")
    ];
    const columns = rosterGridColumns(slots, templates, "variant");
    expect(columns.map((column) => columnHeader(column))).toEqual(["BD Nacht #1", "BD Tag #1"]);
    expect(slotForColumn(slots, "2026-10-03", columns[0])?.id).toBe(2);
    expect(slotForColumn(slots, "2026-10-03", columns[1])?.id).toBe(1);
    expect(slotForColumn(slots, "2026-10-05", columns[0])).toBeNull();
  });

  it("moves inside a stack before leaving the cell", () => {
    expect(stepWithinStack(0, 1, 2)).toEqual({ index: 1, leave: false });
    expect(stepWithinStack(1, 1, 2)).toEqual({ index: 1, leave: true });
    expect(stepWithinStack(0, -1, 2)).toEqual({ index: 0, leave: true });
    expect(stepWithinStack(0, 1, 1)).toEqual({ index: 0, leave: true });
  });
});

function slot(
  id: number,
  slotDate: string,
  variantId: number,
  label: string,
  startsAt: string,
  endsAt: string
) {
  return {
    id,
    slot_date: slotDate,
    shift_template_id: 8,
    shift_variant_id: variantId,
    variant_label: label,
    position: 1,
    template_code: "BD",
    starts_at: startsAt,
    ends_at: endsAt
  };
}
