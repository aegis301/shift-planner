"use client";

import { t, type Locale } from "@/lib/i18n";
import {
  activePlanningDayStatusDefinitions,
  planningDayStatusBadgeClass,
  planningDayStatusLabel,
  type PlanningDayStatusDefinition
} from "@/lib/planningDayStatus";

export function PlanningDayStatusLegend({
  locale,
  definitions
}: {
  locale: Locale;
  definitions: PlanningDayStatusDefinition[];
}) {
  const items = activePlanningDayStatusDefinitions(definitions);
  if (!items.length) {
    return null;
  }
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-slate-100 pt-3">
      <p id="day-status-legend-title" className="text-xs font-medium text-slate-700">
        {t(locale, "dayStatusLegendTitle")}
      </p>
      <ul className="flex flex-wrap items-center gap-2" aria-labelledby="day-status-legend-title">
        {items.map((item) => (
          <li key={item.code}>
            <span
              className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ${planningDayStatusBadgeClass(item.color_preset)}`}
            >
              {planningDayStatusLabel(item, locale)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
