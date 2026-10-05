import { describe, expect, it } from "vitest";
import { planningDayStatusBadgeClass, planningDayStatusFillClass, PLANNING_DAY_STATUS_COLOR_PRESETS } from "@/lib/planningDayStatus";

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
