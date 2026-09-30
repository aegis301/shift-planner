import { describe, expect, it } from "vitest";
import { columnHeader, rosterGridColumns, slotForColumn } from "@/lib/rosterColumns";

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
    expect(columns.map(columnHeader)).toEqual(["BD #1", "BD #2", "RD #1"]);
    expect(slotForColumn(
      [
        { id: 2, slot_date: "2026-10-01", shift_template_id: 8, position: 2 },
        { id: 1, slot_date: "2026-10-01", shift_template_id: 8, position: 1 }
      ],
      "2026-10-01",
      columns[1]
    )?.id).toBe(2);
    expect(slotForColumn([], "2026-10-03", columns[1])).toBeNull();
  });

  it("keeps a weekend day shift and night shift as separate columns", () => {
    const slots = [
      {
        id: 1,
        slot_date: "2026-10-03",
        shift_template_id: 8,
        shift_variant_id: 21,
        variant_label: "Tag",
        position: 1,
        template_code: "BD"
      },
      {
        id: 2,
        slot_date: "2026-10-03",
        shift_template_id: 8,
        shift_variant_id: 22,
        variant_label: "Nacht",
        position: 1,
        template_code: "BD"
      },
      {
        id: 3,
        slot_date: "2026-10-04",
        shift_template_id: 8,
        shift_variant_id: 21,
        variant_label: "Tag",
        position: 1,
        template_code: "BD"
      }
    ];
    const columns = rosterGridColumns(slots, [
      { id: 8, code: "BD", name: "Bereit", category: "bereitschaftsdienst", display_order: 1 }
    ]);
    expect(columns.map(columnHeader)).toEqual(["BD Nacht #1", "BD Tag #1"]);
    expect(slotForColumn(slots, "2026-10-03", columns[0])?.id).toBe(2);
    expect(slotForColumn(slots, "2026-10-03", columns[1])?.id).toBe(1);
    expect(slotForColumn(slots, "2026-10-05", columns[0])).toBeNull();
  });
});
