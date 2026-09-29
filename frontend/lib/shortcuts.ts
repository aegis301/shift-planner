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
  { id: "clear", keys: "Esc", labelKey: "shortcutClearSelection" },
  { id: "grid-arrows", keys: "Arrow keys", labelKey: "shortcutGridArrows" },
  { id: "grid-extend", keys: "Shift+Arrows", labelKey: "shortcutGridExtend" },
  { id: "grid-row", keys: "Shift+Space", labelKey: "shortcutGridRow" },
  { id: "grid-column", keys: "Ctrl/Cmd+Space", labelKey: "shortcutGridColumn" },
  { id: "grid-all", keys: "Ctrl/Cmd+A", labelKey: "shortcutGridAll" },
  { id: "grid-edit", keys: "Enter", labelKey: "shortcutGridEdit" },
  { id: "grid-clear", keys: "Delete", labelKey: "shortcutGridClear" },
  { id: "grid-fill-down", keys: "Ctrl/Cmd+D", labelKey: "shortcutGridFillDown" },
  { id: "grid-fill-right", keys: "Ctrl/Cmd+R", labelKey: "shortcutGridFillRight" },
  { id: "grid-copy", keys: "Ctrl/Cmd+C", labelKey: "shortcutGridCopy" },
  { id: "grid-paste", keys: "Ctrl/Cmd+V", labelKey: "shortcutGridPaste" },
  { id: "undo", keys: "Ctrl/Cmd+Z", labelKey: "shortcutUndo" },
  { id: "redo", keys: "Ctrl/Cmd+Y", labelKey: "shortcutRedo" }
];

export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || Boolean(target.isContentEditable);
}
