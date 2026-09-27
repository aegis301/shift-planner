"use client";

import { useEffect, useState } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { LocaleShell } from "@/components/LocaleProvider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { createQueryClient } from "@/lib/queryClient";

function QueryDevtools() {
  const [enabled, setEnabled] = useState(false);
  useEffect(() => {
    if (process.env.NODE_ENV === "development" && !navigator.webdriver) {
      setEnabled(true);
    }
  }, []);
  if (!enabled) {
    return null;
  }
  return <ReactQueryDevtools buttonPosition="bottom-left" initialIsOpen={false} />;
}

export function ClientRoot({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => createQueryClient());
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={300}>
        <LocaleShell>{children}</LocaleShell>
      </TooltipProvider>
      <QueryDevtools />
    </QueryClientProvider>
  );
}
