import { describe, expect, it } from "vitest";
import { intentChipClass, wishesMonthOverview } from "@/lib/wishesMonth";

const templates = [
  { id: 8, name: "Bereit" },
  { id: 9, name: "Ruf" }
];

describe("wish and no-go chips", () => {
  it("uses a filled chip with white text", () => {
    expect(intentChipClass("wish")).toBe("bg-sky-800 text-white");
    expect(intentChipClass("no_go")).toBe("bg-rose-800 text-white");
    expect(contrast("#ffffff", "#075985")).toBeGreaterThanOrEqual(4.5);
    expect(contrast("#ffffff", "#9f1239")).toBeGreaterThanOrEqual(4.5);
  });
});

describe("wishes month overview", () => {
  it("lists that member's comments and wishes and omits everyone else", () => {
    const rows = wishesMonthOverview(
      1,
      [
        { team_member_id: 1, cell_date: "2026-10-03", comment: "  Late train  " },
        { team_member_id: 1, cell_date: "2026-10-01", comment: "   " },
        { team_member_id: 2, cell_date: "2026-10-02", comment: "Other person's note" }
      ],
      [
        { team_member_id: 1, cell_date: "2026-10-03", shift_template_id: 9, kind: "no_go" },
        { team_member_id: 1, cell_date: "2026-10-03", shift_template_id: 8, kind: "wish" },
        { team_member_id: 2, cell_date: "2026-10-04", shift_template_id: 8, kind: "wish" },
        { team_member_id: 1, cell_date: "2026-10-11", shift_template_id: 8, kind: "wish" }
      ],
      templates
    );
    expect(rows).toEqual([
      { kind: "comment", date: "2026-10-03", text: "Late train" },
      { kind: "wish", date: "2026-10-03", templateId: 8, templateName: "Bereit", band: "all" },
      { kind: "no_go", date: "2026-10-03", templateId: 9, templateName: "Ruf", band: "all" },
      { kind: "wish", date: "2026-10-11", templateId: 8, templateName: "Bereit", band: "all" }
    ]);
  });
});

function contrast(background: string, foreground: string): number {
  const lighter = Math.max(luminance(background), luminance(foreground));
  const darker = Math.min(luminance(background), luminance(foreground));
  return (lighter + 0.05) / (darker + 0.05);
}

function luminance(hex: string): number {
  const value = Number.parseInt(hex.slice(1), 16);
  const channels = [(value >> 16) & 255, (value >> 8) & 255, value & 255].map((channel) => {
    const unit = channel / 255;
    return unit <= 0.04045 ? unit / 12.92 : ((unit + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}
