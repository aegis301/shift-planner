import type { ReactNode } from "react";
import { cn } from "@/components/ui/cn";

export const inspectorAsideClassName =
  "sticky top-4 h-[calc(100vh-6rem)] w-[400px] shrink-0 overflow-hidden rounded-token-lg border border-default";

export function Inspector({
  title,
  className,
  children
}: {
  title: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <aside aria-label={title} className={cn("flex min-h-0 flex-col bg-surface", className)} data-testid="workbench-inspector">
      <div className="flex items-center justify-between border-b border-default px-3 py-2">
        <h2 className="text-sm font-semibold text-ink">{title}</h2>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-3">{children}</div>
    </aside>
  );
}
