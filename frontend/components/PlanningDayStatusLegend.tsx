"use client";

import { t, type Locale, type TranslationKey } from "@/lib/i18n";

const DAY_STATUS_LEGEND: Array<{ label: TranslationKey; color: string }> = [
  { label: "urlaub", color: "bg-rose-100 text-rose-800 ring-rose-200" },
  { label: "forschung", color: "bg-violet-100 text-violet-800 ring-violet-200" },
  { label: "lehre", color: "bg-amber-100 text-amber-800 ring-amber-200" },
  { label: "frei", color: "bg-slate-100 text-slate-700 ring-slate-200" }
];

export function PlanningDayStatusLegend({ locale }: { locale: Locale }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-slate-100 pt-3">
      <p id="day-status-legend-title" className="text-xs font-medium text-slate-700">
        {t(locale, "dayStatusLegendTitle")}
      </p>
      <ul className="flex flex-wrap items-center gap-2" aria-labelledby="day-status-legend-title">
        {DAY_STATUS_LEGEND.map((item) => (
          <li key={item.label}>
            <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ${item.color}`}>{t(locale, item.label)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
