import type { TranslationKey } from "@/lib/i18n";

export type ShortcutDef = {
  id: string;
  keys: string;
  labelKey: TranslationKey;
};

export const workbenchShortcuts: ShortcutDef[] = [
  { id: "palette", keys: "Ctrl/Cmd+K", labelKey: "shortcutPalette" },
  { id: "help", keys: "?", labelKey: "shortcutHelp" },
  { id: "previous-period", keys: "[", labelKey: "shortcutPrevPeriod" },
  { id: "next-period", keys: "]", labelKey: "shortcutNextPeriod" },
  { id: "tab-wishes", keys: "g w", labelKey: "shortcutTabWishes" },
  { id: "tab-roster", keys: "g r", labelKey: "shortcutTabRoster" },
  { id: "tab-analysis", keys: "g a", labelKey: "shortcutTabAnalysis" },
  { id: "inspector", keys: "i", labelKey: "shortcutToggleInspector" },
  { id: "clear", keys: "Esc", labelKey: "shortcutClearSelection" }
];

export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || Boolean(target.isContentEditable);
}
