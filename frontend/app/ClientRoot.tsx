"use client";

import { LocaleShell } from "@/components/LocaleProvider";

export function ClientRoot({ children }: { children: React.ReactNode }) {
  return <LocaleShell>{children}</LocaleShell>;
}
