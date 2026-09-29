import { teamMemberPlanningDisplayName } from "@/lib/teamMemberDisplay";

export type ClipboardMember = {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
  nickname?: string | null;
};

export type InternalCell = {
  memberId: number | null;
};

export type ParsedClipboard = {
  format: "json" | "tsv";
  rows: (InternalCell | string)[][];
};

export type ResolvedPasteCell =
  | { kind: "member"; memberId: number }
  | { kind: "clear" }
  | { kind: "unresolved"; name: string }
  | { kind: "skip" };

const INTERNAL_KIND = "shift-planner-roster";

export function toTsv(labels: (string | null)[][]): string {
  return labels.map((row) => row.map((cell) => cell ?? "").join("\t")).join("\n");
}

export function toInternalClipboard(rows: InternalCell[][]): string {
  return JSON.stringify({ kind: INTERNAL_KIND, rows });
}

export function parseClipboard(text: string): ParsedClipboard | null {
  let body = text.replace(/^\uFEFF/, "");
  if (body.endsWith("\r\n")) {
    body = body.slice(0, -2);
  } else if (body.endsWith("\n")) {
    body = body.slice(0, -1);
  }
  if (body.trim().startsWith("{")) {
    try {
      const parsed = JSON.parse(body.trim()) as { kind?: string; rows?: InternalCell[][] };
      if (parsed.kind === INTERNAL_KIND && Array.isArray(parsed.rows)) {
        return { format: "json", rows: parsed.rows };
      }
    } catch {
      return null;
    }
  }
  if (body === "") {
    return { format: "tsv", rows: [[""]] };
  }
  return { format: "tsv", rows: body.split(/\r?\n/).map((line) => line.split("\t")) };
}

export function resolvePasteCell(value: InternalCell | string, members: ClipboardMember[]): ResolvedPasteCell {
  if (typeof value !== "string") {
    if (value.memberId == null) {
      return { kind: "clear" };
    }
    return members.some((member) => member.id === value.memberId) ? { kind: "member", memberId: value.memberId } : { kind: "unresolved", name: String(value.memberId) };
  }
  const name = value.trim();
  if (!name || name === "—") {
    return { kind: "clear" };
  }
  const needle = name.toLowerCase();
  const byEmail = members.filter((member) => member.email.trim().toLowerCase() === needle);
  if (byEmail.length === 1) {
    return { kind: "member", memberId: byEmail[0].id };
  }
  if (byEmail.length > 1) {
    return { kind: "unresolved", name };
  }
  const byDisplay = members.filter((member) => teamMemberPlanningDisplayName(member).toLowerCase() === needle);
  if (byDisplay.length === 1) {
    return { kind: "member", memberId: byDisplay[0].id };
  }
  return { kind: "unresolved", name };
}
