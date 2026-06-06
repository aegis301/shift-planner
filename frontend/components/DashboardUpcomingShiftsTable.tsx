"use client";

import { Calendar } from "lucide-react";
import { categoryLabel } from "@/components/dashboardCharts";
import type { TeamMemberDashboard } from "@/lib/dashboard";
import { API_BASE_URL } from "@/lib/api";
import { formatPlanningDate, formatShiftTimeRange } from "@/lib/shiftDisplay";
import type { Locale, TranslationKey } from "@/lib/i18n";
import { t } from "@/lib/i18n";

type UpcomingSlot = TeamMemberDashboard["upcoming_slots"][number];

function dayClassLabel(locale: Locale, dayClass: string): string {
  const map: Record<string, TranslationKey> = {
    weekday: "weekday",
    weekend: "weekend",
    holiday: "holiday",
  };
  const key = map[dayClass];
  return key ? t(locale, key) : dayClass;
}

function templateLabel(locale: Locale, slot: UpcomingSlot): string {
  const name = slot.template_name;
  const base = name ?? slot.template_code ?? "—";
  return slot.variant_label ? `${base} · ${slot.variant_label}` : base;
}

export function DashboardUpcomingShiftsTable({
  locale,
  slots,
  emptyLabelKey = "dashboardUpcomingShiftsEmpty",
  showIcsExport = false,
}: {
  locale: Locale;
  slots: UpcomingSlot[];
  emptyLabelKey?: TranslationKey;
  showIcsExport?: boolean;
}) {
  if (slots.length === 0) {
    return <p className="text-sm text-slate-500">{t(locale, emptyLabelKey)}</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50">
          <tr>
            <th scope="col" className="px-3 py-2 text-left font-semibold text-slate-700">
              {t(locale, "dashboardUpcomingShiftsColDate")}
            </th>
            <th scope="col" className="px-3 py-2 text-left font-semibold text-slate-700">
              {t(locale, "dashboardUpcomingShiftsColShift")}
            </th>
            <th scope="col" className="hidden px-3 py-2 text-left font-semibold text-slate-700 sm:table-cell">
              {t(locale, "dashboardUpcomingShiftsColTime")}
            </th>
            <th scope="col" className="hidden px-3 py-2 text-left font-semibold text-slate-700 md:table-cell">
              {t(locale, "dashboardUpcomingShiftsColCategory")}
            </th>
            {showIcsExport ? (
              <th scope="col" className="px-3 py-2 text-right font-semibold text-slate-700">
                <span className="sr-only">{t(locale, "dashboardUpcomingShiftsColExport")}</span>
              </th>
            ) : null}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 bg-white">
          {slots.map((slot, index) => {
            const timeRange = formatShiftTimeRange(slot.starts_at, slot.ends_at);
            return (
              <tr key={`${slot.slot_date}-${slot.template_code ?? index}-${index}`}>
                <td className="whitespace-nowrap px-3 py-2.5 font-medium text-ink">
                  <div>{formatPlanningDate(locale, slot.slot_date)}</div>
                  {slot.day_class ? (
                    <span className="mt-0.5 inline-block rounded-full bg-slate-100 px-1.5 py-0.5 text-xs font-medium text-slate-600">
                      {dayClassLabel(locale, slot.day_class)}
                    </span>
                  ) : null}
                </td>
                <td className="px-3 py-2.5 text-slate-700">
                  <div>{templateLabel(locale, slot)}</div>
                  {timeRange ? <div className="mt-0.5 text-xs text-slate-500 sm:hidden">{timeRange}</div> : null}
                </td>
                <td className="hidden whitespace-nowrap px-3 py-2.5 text-slate-600 sm:table-cell">
                  {timeRange || "—"}
                </td>
                <td className="hidden px-3 py-2.5 text-slate-600 md:table-cell">
                  {slot.category ? categoryLabel(locale, slot.category) : "—"}
                </td>
                {showIcsExport ? (
                  <td className="whitespace-nowrap px-3 py-2.5 text-right">
                    <a
                      aria-label={t(locale, "shiftIcsExport")}
                      className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-700 shadow-sm hover:bg-slate-50"
                      href={`${API_BASE_URL}/api/v1/exports/roster-slots/${slot.roster_slot_id}.ics`}
                      title={t(locale, "shiftIcsExport")}
                    >
                      <Calendar size={16} />
                    </a>
                  </td>
                ) : null}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
