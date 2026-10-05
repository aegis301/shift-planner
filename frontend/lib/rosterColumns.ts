import { localDateKey, localHour } from "@/lib/orgTime";

export type RosterView = "template" | "day-night" | "variant";

export function parseRosterView(value: string | null): RosterView {
  if (value === "day-night" || value === "variant") {
    return value;
  }
  return "template";
}

export type RosterColumnSlot = {
  id: number;
  slot_date: string;
  shift_template_id?: number | null;
  shift_variant_id?: number | null;
  variant_label?: string | null;
  starts_at?: string | null;
  ends_at?: string | null;
  position: number;
  template_code?: string | null;
  template_name?: string | null;
  category?: string | null;
};

export type RosterColumnTemplate = {
  id: number;
  code: string;
  name: string;
  category: string;
  display_order: number;
};

export type RosterColumnBand = "day" | "night" | null;

export type RosterGridColumn = {
  key: string;
  templateId: number | null;
  variantId: number | null;
  band: RosterColumnBand;
  position: number;
  code: string;
  name: string;
  variantLabel: string;
  category: string;
  displayOrder: number;
};

const DEFAULT_TIME_ZONE = "Europe/Berlin";

export function isNightRosterSlot(slot: RosterColumnSlot, timeZone: string = DEFAULT_TIME_ZONE): boolean {
  if (!slot.starts_at || !slot.ends_at) {
    return false;
  }
  if (localDateKey(slot.ends_at, timeZone) > localDateKey(slot.starts_at, timeZone)) {
    return true;
  }
  return localHour(slot.starts_at, timeZone) >= 14;
}

export function rosterGridColumns(
  slots: RosterColumnSlot[],
  templates: RosterColumnTemplate[],
  view: RosterView = "template",
  timeZone: string = DEFAULT_TIME_ZONE
): RosterGridColumn[] {
  const templatesById = new Map(templates.map((template) => [template.id, template]));
  const splitTemplates = new Set<number>();
  if (view === "day-night") {
    const seen = new Map<number, { day: boolean; night: boolean }>();
    for (const slot of slots) {
      const templateId = slot.shift_template_id;
      if (templateId == null) {
        continue;
      }
      const flags = seen.get(templateId) ?? { day: false, night: false };
      if (isNightRosterSlot(slot, timeZone)) {
        flags.night = true;
      } else {
        flags.day = true;
      }
      seen.set(templateId, flags);
    }
    for (const [templateId, flags] of seen) {
      if (flags.day && flags.night) {
        splitTemplates.add(templateId);
      }
    }
  }
  const columns = new Map<string, RosterGridColumn>();
  for (const slot of slots) {
    const templateId = slot.shift_template_id ?? null;
    const variantId = view === "variant" ? (slot.shift_variant_id ?? null) : null;
    const band: RosterColumnBand =
      view === "day-night" && templateId != null && splitTemplates.has(templateId)
        ? isNightRosterSlot(slot, timeZone)
          ? "night"
          : "day"
        : null;
    const key = `${templateId ?? -1}:${variantId ?? 0}:${band ?? "all"}:${slot.position}`;
    if (columns.has(key)) {
      continue;
    }
    const template = templateId == null ? undefined : templatesById.get(templateId);
    columns.set(key, {
      key,
      templateId,
      variantId,
      band,
      position: slot.position,
      code: template?.code ?? slot.template_code ?? "?",
      name: template?.name ?? slot.template_name ?? slot.template_code ?? "?",
      variantLabel: view === "variant" ? (slot.variant_label?.trim() ?? "") : "",
      category: template?.category ?? slot.category ?? "other",
      displayOrder: template?.display_order ?? 0
    });
  }
  return [...columns.values()].sort((left, right) => {
    return (
      left.displayOrder - right.displayOrder ||
      left.name.localeCompare(right.name) ||
      left.code.localeCompare(right.code) ||
      bandOrder(left.band) - bandOrder(right.band) ||
      left.variantLabel.localeCompare(right.variantLabel) ||
      left.position - right.position ||
      (left.variantId ?? 0) - (right.variantId ?? 0)
    );
  });
}

export function slotsForColumn(slots: RosterColumnSlot[], date: string, column: RosterGridColumn, timeZone: string = DEFAULT_TIME_ZONE): RosterColumnSlot[] {
  return slots
    .filter((slot) => slot.slot_date === date && slotMatchesColumn(slot, column, timeZone))
    .sort((left, right) => (left.starts_at ?? "").localeCompare(right.starts_at ?? "") || left.id - right.id);
}

export function slotForColumn(
  slots: RosterColumnSlot[],
  date: string,
  column: RosterGridColumn,
  timeZone: string = DEFAULT_TIME_ZONE
): RosterColumnSlot | null {
  return slotsForColumn(slots, date, column, timeZone)[0] ?? null;
}

export function columnHeader(column: RosterGridColumn, labels: { day: string; night: string } = { day: "Tag", night: "Nacht" }): string {
  const band = column.band === "day" ? labels.day : column.band === "night" ? labels.night : "";
  const parts = [column.code, column.variantLabel, band].filter((part) => part.length > 0);
  return `${parts.join(" ")} #${column.position}`;
}

export function stepWithinStack(index: number, delta: number, count: number): { index: number; leave: boolean } {
  if (count <= 1) {
    return { index: 0, leave: true };
  }
  const next = index + delta;
  if (next < 0 || next >= count) {
    return { index, leave: true };
  }
  return { index: next, leave: false };
}

function bandOrder(band: RosterColumnBand): number {
  if (band === "day") {
    return 0;
  }
  if (band === "night") {
    return 1;
  }
  return 0;
}

function slotMatchesColumn(slot: RosterColumnSlot, column: RosterGridColumn, timeZone: string): boolean {
  if ((slot.shift_template_id ?? null) !== column.templateId || slot.position !== column.position) {
    return false;
  }
  if (column.variantId != null && (slot.shift_variant_id ?? null) !== column.variantId) {
    return false;
  }
  if (column.band === "night") {
    return isNightRosterSlot(slot, timeZone);
  }
  if (column.band === "day") {
    return !isNightRosterSlot(slot, timeZone);
  }
  return true;
}
