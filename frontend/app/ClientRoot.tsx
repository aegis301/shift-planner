"use client";

import { useState } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { LocaleShell } from "@/components/LocaleProvider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { createQueryClient } from "@/lib/queryClient";

export function ClientRoot({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => createQueryClient());
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={300}>
        <LocaleShell>{children}</LocaleShell>
      </TooltipProvider>
      {process.env.NODE_ENV === "development" ? <ReactQueryDevtools buttonPosition="bottom-left" initialIsOpen={false} /> : null}
    </QueryClientProvider>
  );
}
