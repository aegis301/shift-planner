import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { t, type Locale } from "@/lib/i18n";
import { workbenchShortcuts } from "@/lib/shortcuts";

export function ShortcutHelp({ locale, open, onOpenChange }: { locale: Locale; open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogTitle>{t(locale, "shortcutHelpTitle")}</DialogTitle>
        <ul className="mt-3 grid gap-2">
          {workbenchShortcuts.map((shortcut) => (
            <li key={shortcut.id} className="flex items-center justify-between gap-3 text-sm">
              <span>{t(locale, shortcut.labelKey)}</span>
              <kbd className="rounded border border-slate-200 bg-slate-50 px-2 py-0.5 font-mono text-xs">{shortcut.keys}</kbd>
            </li>
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
