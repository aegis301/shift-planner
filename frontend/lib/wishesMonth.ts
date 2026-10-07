import type { IntentBand } from "@/lib/wishesDay";

export type WishesMonthCell = {
  team_member_id: number;
  cell_date: string;
  comment?: string | null;
};

export type WishesMonthIntent = {
  team_member_id: number;
  cell_date: string;
  shift_template_id: number;
  band?: IntentBand | null;
  kind: "wish" | "no_go";
};

export type WishesMonthTemplate = {
  id: number;
  name: string;
};

export type WishesMonthRow =
  | { kind: "comment"; date: string; text: string }
  | { kind: "wish" | "no_go"; date: string; templateId: number; templateName: string; band: IntentBand };

export function intentChipClass(kind: "wish" | "no_go"): string {
  return kind === "wish" ? "bg-sky-800 text-white" : "bg-rose-800 text-white";
}

export function wishesMonthOverview(
  memberId: number,
  cells: readonly WishesMonthCell[],
  intents: readonly WishesMonthIntent[],
  templates: readonly WishesMonthTemplate[]
): WishesMonthRow[] {
  const names = new Map(templates.map((template) => [template.id, template.name]));
  const rows: WishesMonthRow[] = [];
  for (const cell of cells) {
    if (cell.team_member_id !== memberId) {
      continue;
    }
    const text = cell.comment?.trim() ?? "";
    if (!text) {
      continue;
    }
    rows.push({ kind: "comment", date: cell.cell_date, text });
  }
  for (const intent of intents) {
    if (intent.team_member_id !== memberId) {
      continue;
    }
    rows.push({
      kind: intent.kind,
      date: intent.cell_date,
      templateId: intent.shift_template_id,
      templateName: names.get(intent.shift_template_id) ?? String(intent.shift_template_id),
      band: intent.band ?? "all"
    });
  }
  rows.sort(
    (left, right) =>
      left.date.localeCompare(right.date) ||
      kindOrder(left.kind) - kindOrder(right.kind) ||
      rowLabel(left).localeCompare(rowLabel(right), undefined, { sensitivity: "base" }) ||
      bandOrder(left) - bandOrder(right)
  );
  return rows;
}

function kindOrder(kind: WishesMonthRow["kind"]): number {
  if (kind === "comment") {
    return 0;
  }
  if (kind === "wish") {
    return 1;
  }
  return 2;
}

function rowLabel(row: WishesMonthRow): string {
  return row.kind === "comment" ? row.text : row.templateName;
}

function bandOrder(row: WishesMonthRow): number {
  if (row.kind === "comment") {
    return 0;
  }
  return row.band === "all" ? 0 : row.band === "day" ? 1 : 2;
}
