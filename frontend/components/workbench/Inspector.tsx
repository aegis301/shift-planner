import type { ReactNode } from "react";
import { useState } from "react";
import { t, type Locale } from "@/lib/i18n";

export function Inspector({
  locale,
  open,
  title,
  children
}: {
  locale: Locale;
  open: boolean;
  title: string;
  children: ReactNode;
}) {
  const [width, setWidth] = useState(400);
  if (!open) {
    return null;
  }
  return (
    <aside
      className="sticky top-4 flex h-[calc(100vh-6rem)] shrink-0 flex-col overflow-hidden rounded-lg border border-slate-200 bg-white"
      style={{ width }}
    >
      <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2">
        <h2 className="text-sm font-semibold text-ink">{title}</h2>
        <input
          aria-label={t(locale, "shortcutToggleInspector")}
          className="w-16"
          max={440}
          min={360}
          type="range"
          value={width}
          onChange={(event) => setWidth(Number(event.target.value))}
        />
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-3">{children}</div>
    </aside>
  );
}
