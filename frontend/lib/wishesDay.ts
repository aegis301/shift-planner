export type IntentBand = "all" | "day" | "night";
export type IntentKind = "wish" | "no_go";

export type DayTemplateSlot = {
  cell_date: string;
  shift_template_id: number;
  shift_group_id?: number | null;
  has_day?: boolean;
  has_night?: boolean;
};

export type DayIntent = {
  team_member_id: number;
  cell_date: string;
  shift_group_id: number;
  shift_template_id: number;
  band?: IntentBand | null;
  kind: IntentKind;
};

export type DayTemplateOption = {
  templateId: number;
  shiftGroupId: number;
  name: string;
  split: boolean;
};

export type IntentWrite = {
  team_member_id: number;
  cell_date: string;
  shift_group_id: number;
  shift_template_id: number;
  band: IntentBand;
  kind: IntentKind | null;
};

export function intentBand(intent: { band?: IntentBand | null }): IntentBand {
  return intent.band ?? "all";
}

/** Templates that generate a slot on `date`, with `split` when they run both a day and a night shift. */
export function dayTemplateOptions(
  slotDays: readonly DayTemplateSlot[],
  templates: readonly { id: number; name: string; is_active?: boolean }[],
  date: string,
  shiftGroupId?: number
): DayTemplateOption[] {
  const byId = new Map(templates.filter((row) => row.is_active !== false).map((row) => [row.id, row]));
  const out = new Map<string, DayTemplateOption>();
  for (const row of slotDays) {
    if (row.cell_date !== date) {
      continue;
    }
    const groupId = shiftGroupId ?? row.shift_group_id ?? null;
    if (groupId == null || (shiftGroupId != null && row.shift_group_id != null && row.shift_group_id !== shiftGroupId)) {
      continue;
    }
    const template = byId.get(row.shift_template_id);
    if (!template) {
      continue;
    }
    out.set(`${row.shift_template_id}:${groupId}`, {
      templateId: row.shift_template_id,
      shiftGroupId: groupId,
      name: template.name,
      split: Boolean(row.has_day && row.has_night)
    });
  }
  return [...out.values()].sort(
    (left, right) =>
      left.name.localeCompare(right.name, undefined, { sensitivity: "base" }) ||
      left.templateId - right.templateId ||
      left.shiftGroupId - right.shiftGroupId
  );
}

function sameTarget(intent: DayIntent, memberId: number, date: string, option: { templateId: number; shiftGroupId: number }): boolean {
  return (
    intent.team_member_id === memberId &&
    intent.cell_date === date &&
    intent.shift_template_id === option.templateId &&
    intent.shift_group_id === option.shiftGroupId
  );
}

/** The kind that applies to one band: the band's own row, else the whole-day row. */
export function effectiveKind(
  intents: readonly DayIntent[],
  memberId: number,
  date: string,
  option: { templateId: number; shiftGroupId: number },
  band: IntentBand
): IntentKind | null {
  const rows = intents.filter((row) => sameTarget(row, memberId, date, option));
  const own = rows.find((row) => intentBand(row) === band);
  if (own) {
    return own.kind;
  }
  if (band === "all") {
    return null;
  }
  return rows.find((row) => intentBand(row) === "all")?.kind ?? null;
}

/**
 * The write for setting one band. When both bands end up with the same kind, it is stored as one
 * whole-day row instead of two band rows.
 */
export function bandWrite(
  intents: readonly DayIntent[],
  memberId: number,
  date: string,
  option: { templateId: number; shiftGroupId: number },
  band: IntentBand,
  kind: IntentKind | null
): IntentWrite {
  let target: IntentBand = band;
  if (band !== "all") {
    const other = band === "day" ? "night" : "day";
    if (effectiveKind(intents, memberId, date, option, other) === kind) {
      target = "all";
    }
  }
  return {
    team_member_id: memberId,
    cell_date: date,
    shift_group_id: option.shiftGroupId,
    shift_template_id: option.templateId,
    band: target,
    kind
  };
}

/** Writes that put (or lift) a whole-day no-go on every shift that runs that day. */
export function anyShiftNoGoWrites(
  options: readonly DayTemplateOption[],
  memberId: number,
  date: string,
  noGo: boolean
): IntentWrite[] {
  return options.map((option) => ({
    team_member_id: memberId,
    cell_date: date,
    shift_group_id: option.shiftGroupId,
    shift_template_id: option.templateId,
    band: "all",
    kind: noGo ? "no_go" : null
  }));
}

export function isAnyShiftNoGo(
  intents: readonly DayIntent[],
  options: readonly DayTemplateOption[],
  memberId: number,
  date: string
): boolean {
  if (options.length === 0) {
    return false;
  }
  return options.every((option) => {
    if (effectiveKind(intents, memberId, date, option, "all") === "no_go") {
      return true;
    }
    return (
      option.split &&
      effectiveKind(intents, memberId, date, option, "day") === "no_go" &&
      effectiveKind(intents, memberId, date, option, "night") === "no_go"
    );
  });
}

/** Whether an intent with `band` applies to a slot that is (or is not) a night slot. */
export function intentBandCoversSlot(band: IntentBand | null | undefined, isNight: boolean): boolean {
  const value = band ?? "all";
  return value === "all" || (value === "night") === isNight;
}
