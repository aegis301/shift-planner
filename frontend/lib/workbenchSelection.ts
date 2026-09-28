export type WorkbenchTab = "wishes" | "roster" | "analysis";

export type WorkbenchSelection = {
  period: string;
  shiftGroup: string;
  tab: WorkbenchTab;
  slot: string;
  member: string;
  day: string;
  finding: string;
};

const selectionKeys = ["period", "shiftGroup", "tab", "slot", "member", "day", "finding"] as const;

export function readWorkbenchSelection(params: URLSearchParams): WorkbenchSelection {
  const tab = params.get("tab");
  return {
    period: params.get("period") ?? "",
    shiftGroup: params.get("shiftGroup") ?? "",
    tab: tab === "roster" || tab === "analysis" ? tab : "wishes",
    slot: params.get("slot") ?? "",
    member: params.get("member") ?? "",
    day: params.get("day") ?? "",
    finding: params.get("finding") ?? ""
  };
}

export function selectionQuery(current: URLSearchParams, patch: Partial<Record<(typeof selectionKeys)[number], string | null>>): string {
  const next = new URLSearchParams(current.toString());
  for (const key of selectionKeys) {
    if (!(key in patch)) {
      continue;
    }
    const value = patch[key];
    if (value == null || value === "" || (key === "tab" && value === "wishes")) {
      next.delete(key);
    } else {
      next.set(key, value);
    }
  }
  return next.toString();
}
