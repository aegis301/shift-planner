"use client";

import { useEffect, useRef, useState } from "react";
import {
  Combobox,
  ComboboxAnchor,
  ComboboxContent,
  ComboboxInput,
  ComboboxItem,
  ComboboxList
} from "@/components/ui/combobox";
import { t, type Locale } from "@/lib/i18n";
import { planningDayStatusLabel, type PlanningDayStatusDefinition } from "@/lib/planningDayStatus";

export function WishesStatusEditor({
  definitions,
  filter,
  locale,
  onOpenChange,
  onSelect
}: {
  definitions: PlanningDayStatusDefinition[];
  filter: string;
  locale: Locale;
  onOpenChange: (open: boolean) => void;
  onSelect: (status: string | null) => void;
}) {
  const [query, setQuery] = useState(filter);
  const anchorRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const node = document.querySelector<HTMLElement>("[data-grid-active='true']");
    const anchor = anchorRef.current;
    if (!node || !anchor) {
      return;
    }
    const box = node.getBoundingClientRect();
    anchor.style.position = "fixed";
    anchor.style.top = `${box.top}px`;
    anchor.style.left = `${box.left}px`;
    anchor.style.width = `${box.width}px`;
    anchor.style.height = `${box.height}px`;
  }, []);
  const needle = query.trim().toLowerCase();
  const matched = definitions.filter((row) => {
    if (!needle) {
      return true;
    }
    return row.code.toLowerCase().includes(needle) || row.label.toLowerCase().includes(needle);
  });
  return (
    <Combobox open onOpenChange={onOpenChange}>
      <ComboboxAnchor ref={anchorRef} className="pointer-events-none" />
      <ComboboxContent className="w-64" shouldFilter={false} onKeyDown={(event) => event.stopPropagation()}>
        <ComboboxInput
          aria-label={t(locale, "wishesStatusLabel")}
          autoFocus
          placeholder={t(locale, "wishesStatusLabel")}
          value={query}
          onValueChange={setQuery}
        />
        <ComboboxList>
          {matched.map((row) => (
            <ComboboxItem key={row.code} value={row.code} onSelect={() => onSelect(row.code)}>
              <span className="font-medium text-ink">{planningDayStatusLabel(row, locale)}</span>
              <span className="text-muted">{row.code}</span>
            </ComboboxItem>
          ))}
          {needle ? null : (
            <ComboboxItem value="__clear__" onSelect={() => onSelect(null)}>
              {t(locale, "emptyValue")}
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  );
}
