import { Command } from "cmdk";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { t, type Locale } from "@/lib/i18n";
import type { PaletteCommand } from "@/lib/paletteCommands";

export function CommandPalette({
  locale,
  open,
  onOpenChange,
  commands
}: {
  locale: Locale;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  commands: PaletteCommand[];
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg overflow-hidden p-0">
        <DialogTitle className="sr-only">{t(locale, "commandPalette")}</DialogTitle>
        <Command label={t(locale, "commandPalette")} className="flex max-h-[24rem] flex-col">
          <Command.Input
            className="h-11 border-b border-slate-200 px-3 text-sm outline-none"
            placeholder={t(locale, "commandPalettePlaceholder")}
          />
          <Command.List className="min-h-0 flex-1 overflow-auto p-1">
            <Command.Empty className="px-3 py-4 text-sm text-slate-500">{t(locale, "noData")}</Command.Empty>
            {commands.map((command) => (
              <Command.Item
                key={command.id}
                className="flex items-center justify-between gap-3 rounded-md px-3 py-2 text-sm data-[selected=true]:bg-slate-100"
                disabled={command.disabledReason != null}
                value={command.label}
                onSelect={() => {
                  if (command.disabledReason) {
                    return;
                  }
                  command.run();
                  onOpenChange(false);
                }}
              >
                <span>{command.label}</span>
                {command.disabledReason ? <span className="text-xs text-amber-800">{command.disabledReason}</span> : null}
              </Command.Item>
            ))}
          </Command.List>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
