"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";
import { t } from "@/lib/i18n";
import {
  formatTeamMemberPropertyValue,
  type TeamMemberPropertyDefinition
} from "@/lib/teamMemberProperties";

export function TeamMemberPropertyCellEditor({
  definition,
  value,
  onChange,
  compact = false,
  readOnly = false
}: {
  definition: TeamMemberPropertyDefinition;
  value: unknown;
  onChange: (value: unknown) => void;
  compact?: boolean;
  readOnly?: boolean;
}) {
  const { locale } = useLocale();
  const [multiSelectOpen, setMultiSelectOpen] = useState(false);
  const className = compact ? `${inputClass} h-9 min-w-32 px-2 py-1 text-sm` : inputClass;

  if (readOnly) {
    return (
      <span className="text-sm text-slate-700">
        {formatTeamMemberPropertyValue(definition.type, value)}
      </span>
    );
  }
  if (definition.type === "number") {
    return (
      <input
        className={className}
        type="number"
        value={value === null || value === undefined ? "" : String(value)}
        onChange={(event) =>
          onChange(event.target.value === "" ? null : Number(event.target.value))
        }
        aria-label={definition.name}
      />
    );
  }
  if (definition.type === "date") {
    return (
      <input
        className={className}
        type="date"
        value={typeof value === "string" ? value : ""}
        onChange={(event) => onChange(event.target.value || null)}
        aria-label={definition.name}
      />
    );
  }
  if (definition.type === "text") {
    return (
      <input
        className={className}
        type="text"
        value={typeof value === "string" ? value : ""}
        onChange={(event) => onChange(event.target.value || null)}
        aria-label={definition.name}
      />
    );
  }
  if (definition.type === "select") {
    return (
      <select
        className={className}
        value={typeof value === "string" ? value : ""}
        onChange={(event) => onChange(event.target.value || null)}
        aria-label={definition.name}
      >
        <option value="">{t(locale, "teamMemberPropertySelectEmpty")}</option>
        {definition.options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    );
  }

  const selectedValues = Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
  return (
    <div className="relative min-w-36">
      <button
        type="button"
        className="flex h-9 w-full items-center justify-between gap-2 rounded-lg border border-slate-200 bg-white px-2 text-left text-sm text-slate-700"
        onClick={() => setMultiSelectOpen((open) => !open)}
        aria-expanded={multiSelectOpen}
      >
        <span className="truncate">
          {formatTeamMemberPropertyValue(definition.type, selectedValues)}
        </span>
        <ChevronDown size={14} className="shrink-0" />
      </button>
      {multiSelectOpen ? (
        <div className="absolute left-0 top-full z-30 mt-1 flex min-w-full flex-wrap gap-2 rounded-lg border border-slate-200 bg-white p-2 shadow-soft">
          {definition.options.map((option) => {
            const selected = selectedValues.includes(option);
            return (
              <button
                key={option}
                type="button"
                className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 ${
                  selected
                    ? "bg-ink text-white ring-ink"
                    : "bg-white text-slate-700 ring-slate-200"
                }`}
                onClick={() =>
                  onChange(
                    selected
                      ? selectedValues.filter((item) => item !== option)
                      : [...selectedValues, option]
                  )
                }
              >
                {option}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
