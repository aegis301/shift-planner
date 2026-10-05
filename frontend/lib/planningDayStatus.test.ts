import { describe, expect, it } from "vitest";
import {
  activePlanningDayStatusDefinitions,
  definitionForStoredStatus,
  planningDayStatusBadgeClass,
  planningDayStatusFillClass,
  PLANNING_DAY_STATUS_COLOR_PRESETS,
  type PlanningDayStatusDefinition
} from "@/lib/planningDayStatus";

const FILL_HEX: Record<(typeof PLANNING_DAY_STATUS_COLOR_PRESETS)[number], [string, string]> = {
  rose: ["#ffe4e6", "#9f1239"],
  violet: ["#ede9fe", "#5b21b6"],
  amber: ["#fef3c7", "#92400e"],
  slate: ["#f1f5f9", "#334155"],
  emerald: ["#d1fae5", "#065f46"],
  sky: ["#e0f2fe", "#075985"],
  cyan: ["#cffafe", "#155e75"],
  orange: ["#ffedd5", "#9a3412"],
  lime: ["#ecfccb", "#3f6212"],
  fuchsia: ["#fae8ff", "#86198f"],
  zinc: ["#f4f4f5", "#27272a"],
  indigo: ["#e0e7ff", "#3730a3"],
  teal: ["#ccfbf1", "#115e59"]
};

describe("stored day status", () => {
  it("resolves an inactive blocking status that is still on a cell", () => {
    const inactive = statusDefinition({
      code: "urlaub",
      label: "Urlaub",
      color_preset: "rose",
      blocks_roster_assignment: true,
      is_active: false
    });
    const active = statusDefinition({
      code: "frei",
      label: "Frei",
      color_preset: "slate",
      blocks_roster_assignment: false,
      is_active: true
    });
    const stored = definitionForStoredStatus("urlaub", [inactive, active]);
    expect(stored?.is_active).toBe(false);
    expect(stored?.blocks_roster_assignment).toBe(true);
    expect(stored ? planningDayStatusFillClass(stored.color_preset) : "").toContain("bg-rose-100");
    expect(activePlanningDayStatusDefinitions([inactive, active]).map((row) => row.code)).toEqual(["frei"]);
    expect(definitionForStoredStatus(null, [inactive])).toBeUndefined();
  });
});

describe("planning day status fill", () => {
  it("keeps dark text on the light preset background at 4.5:1 or better", () => {
    for (const preset of PLANNING_DAY_STATUS_COLOR_PRESETS) {
      const [background, foreground] = FILL_HEX[preset];
      const fill = planningDayStatusFillClass(preset);
      expect(fill).toContain(`bg-${preset}-100`);
      expect(planningDayStatusBadgeClass(preset).startsWith(fill)).toBe(true);
      expect(contrast(background, foreground)).toBeGreaterThanOrEqual(4.5);
    }
  });
});

function statusDefinition(row: Pick<PlanningDayStatusDefinition, "code" | "label" | "color_preset" | "blocks_roster_assignment" | "is_active">): PlanningDayStatusDefinition {
  return {
    id: row.code.length,
    organization_id: 1,
    display_order: 0,
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
    ...row
  };
}

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
