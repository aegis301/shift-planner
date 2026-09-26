"use client";

import { LocaleShell } from "@/components/LocaleProvider";
import { TooltipProvider } from "@/components/ui/tooltip";

export function ClientRoot({ children }: { children: React.ReactNode }) {
  return (
    <TooltipProvider delayDuration={300}>
      <LocaleShell>{children}</LocaleShell>
    </TooltipProvider>
  );
}
