import type { Locale } from "@/lib/i18n";

export type PlanningDayStatusColorPreset =
  | "rose"
  | "violet"
  | "amber"
  | "slate"
  | "emerald"
  | "sky"
  | "cyan"
  | "orange"
  | "lime"
  | "fuchsia"
  | "zinc"
  | "indigo"
  | "teal";

export type PlanningDayStatusDefinition = {
  id: number;
  organization_id: number;
  code: string;
  label: string;
  color_preset: PlanningDayStatusColorPreset;
  blocks_roster_assignment: boolean;
  display_order: number;
  is_active: boolean;
};

export const PLANNING_DAY_STATUS_COLOR_PRESETS: PlanningDayStatusColorPreset[] = [
  "rose",
  "violet",
  "amber",
  "slate",
  "emerald",
  "sky",
  "cyan",
  "orange",
  "lime",
  "fuchsia",
  "zinc",
  "indigo",
  "teal"
];

const BADGE_BY_PRESET: Record<PlanningDayStatusColorPreset, string> = {
  rose: "bg-rose-100 text-rose-800 ring-rose-200",
  violet: "bg-violet-100 text-violet-800 ring-violet-200",
  amber: "bg-amber-100 text-amber-800 ring-amber-200",
  slate: "bg-slate-100 text-slate-700 ring-slate-200",
  emerald: "bg-emerald-100 text-emerald-800 ring-emerald-200",
  sky: "bg-sky-100 text-sky-800 ring-sky-200",
  cyan: "bg-cyan-100 text-cyan-800 ring-cyan-200",
  orange: "bg-orange-100 text-orange-800 ring-orange-200",
  lime: "bg-lime-100 text-lime-800 ring-lime-200",
  fuchsia: "bg-fuchsia-100 text-fuchsia-800 ring-fuchsia-200",
  zinc: "bg-zinc-100 text-zinc-800 ring-zinc-200",
  indigo: "bg-indigo-100 text-indigo-800 ring-indigo-200",
  teal: "bg-teal-100 text-teal-800 ring-teal-200"
};

const SELECT_BY_PRESET: Record<PlanningDayStatusColorPreset, string> = {
  rose: "border-rose-400 bg-rose-50 text-rose-900",
  violet: "border-violet-400 bg-violet-50 text-violet-900",
  amber: "border-amber-400 bg-amber-50 text-amber-950",
  slate: "border-slate-400 bg-slate-50 text-slate-800",
  emerald: "border-emerald-400 bg-emerald-50 text-emerald-900",
  sky: "border-sky-400 bg-sky-50 text-sky-900",
  cyan: "border-cyan-400 bg-cyan-50 text-cyan-900",
  orange: "border-orange-400 bg-orange-50 text-orange-900",
  lime: "border-lime-400 bg-lime-50 text-lime-950",
  fuchsia: "border-fuchsia-400 bg-fuchsia-50 text-fuchsia-900",
  zinc: "border-zinc-400 bg-zinc-50 text-zinc-900",
  indigo: "border-indigo-400 bg-indigo-50 text-indigo-900",
  teal: "border-teal-400 bg-teal-50 text-teal-900"
};

const SOLID_BY_PRESET: Record<PlanningDayStatusColorPreset, string> = {
  rose: "bg-rose-500",
  violet: "bg-violet-500",
  amber: "bg-amber-500",
  slate: "bg-slate-400",
  emerald: "bg-emerald-500",
  sky: "bg-sky-500",
  cyan: "bg-cyan-500",
  orange: "bg-orange-500",
  lime: "bg-lime-500",
  fuchsia: "bg-fuchsia-500",
  zinc: "bg-zinc-500",
  indigo: "bg-indigo-500",
  teal: "bg-teal-500"
};

export function planningDayStatusLabel(definition: PlanningDayStatusDefinition, _locale?: Locale): string {
  return definition.label;
}

export function planningDayStatusBadgeClass(preset: PlanningDayStatusColorPreset): string {
  return BADGE_BY_PRESET[preset] ?? BADGE_BY_PRESET.slate;
}

export function planningDayStatusSolidClass(preset: PlanningDayStatusColorPreset): string {
  return SOLID_BY_PRESET[preset] ?? SOLID_BY_PRESET.slate;
}

export const planningDayStatusSelectShellClass =
  "h-11 min-w-0 rounded-lg px-3 text-sm font-medium outline-none transition focus:ring-4 focus:ring-mint/20";

export function planningDayStatusSelectClass(
  code: string,
  definitions: PlanningDayStatusDefinition[]
): string {
  if (!code) {
    return "border-2 border-slate-200 bg-white text-slate-700";
  }
  const row = planningDayStatusByCode(definitions).get(code);
  if (!row) {
    return "border-2 border-slate-200 bg-white text-slate-700";
  }
  return `border-2 ${SELECT_BY_PRESET[row.color_preset] ?? SELECT_BY_PRESET.slate}`;
}

export function sortPlanningDayStatusDefinitions(
  definitions: PlanningDayStatusDefinition[]
): PlanningDayStatusDefinition[] {
  return [...definitions].sort(
    (a, b) =>
      a.label.localeCompare(b.label, undefined, { sensitivity: "base" }) ||
      a.code.localeCompare(b.code, undefined, { sensitivity: "base" })
  );
}

export function activePlanningDayStatusDefinitions(
  definitions: PlanningDayStatusDefinition[]
): PlanningDayStatusDefinition[] {
  return sortPlanningDayStatusDefinitions(definitions.filter((row) => row.is_active));
}

export function planningDayStatusByCode(
  definitions: PlanningDayStatusDefinition[]
): Map<string, PlanningDayStatusDefinition> {
  return new Map(definitions.map((row) => [row.code, row]));
}

export function labelForPlanningDayStatusCode(
  code: string,
  definitions: PlanningDayStatusDefinition[],
  _locale?: Locale
): string {
  const row = planningDayStatusByCode(definitions).get(code);
  return row ? row.label : code;
}

export function badgeClassForPlanningDayStatusCode(
  code: string,
  definitions: PlanningDayStatusDefinition[]
): string {
  const row = planningDayStatusByCode(definitions).get(code);
  return row ? planningDayStatusBadgeClass(row.color_preset) : BADGE_BY_PRESET.slate;
}

export function rosterBlocksForPlanningDayStatusCode(
  code: string,
  definitions: PlanningDayStatusDefinition[]
): boolean {
  const row = planningDayStatusByCode(definitions).get(code);
  if (!row) {
    return true;
  }
  return row.blocks_roster_assignment;
}
