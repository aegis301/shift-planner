"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  DashboardDonutChart,
  DashboardStackedMonthTemplateChart,
  DashboardTemplateBarChart,
} from "@/components/dashboardCharts";
import { DashboardUpcomingShiftsTable } from "@/components/DashboardUpcomingShiftsTable";
import { DashboardKpiTile, DashboardPeriodCards, DashboardSection } from "@/components/DashboardShared";
import type { TeamMemberDashboard } from "@/lib/dashboard";
import {
  fillPercent,
  formatMonthLong,
  monthTemplateSeriesForYear,
  myPlanningDeepLink,
} from "@/lib/dashboard";
import type { Locale, TranslationKey } from "@/lib/i18n";
import { t } from "@/lib/i18n";

function wishStatusLabel(locale: Locale, status: string): string {
  const map: Record<string, TranslationKey> = {
    urlaub: "urlaub",
    forschung: "forschung",
    lehre: "lehre",
    frei: "frei",
    empty: "dashboardWishesEmpty",
  };
  const key = map[status];
  return key ? t(locale, key) : status;
}

function defaultCategoryMonth(data: TeamMemberDashboard): number {
  return data.current_period?.month ?? new Date().getMonth() + 1;
}

export function DashboardMemberPanel({
  locale,
  data,
  shiftGroupId,
}: {
  locale: Locale;
  data: TeamMemberDashboard;
  shiftGroupId: string;
}) {
  const [categoryMonth, setCategoryMonth] = useState(() => defaultCategoryMonth(data));
  const shiftsByMonth = useMemo(
    () => monthTemplateSeriesForYear(data.year, data.shifts_by_month),
    [data.year, data.shifts_by_month]
  );
  const totalShiftsYear = useMemo(
    () =>
      data.shifts_by_month.reduce(
        (sum, month) => sum + month.templates.reduce((monthSum, row) => monthSum + row.count, 0),
        0
      ),
    [data.shifts_by_month]
  );
  const templateData = useMemo(() => {
    const row = shiftsByMonth.find((month) => month.month === categoryMonth);
    return row?.templates ?? [];
  }, [categoryMonth, shiftsByMonth]);
  const wishesChart = data.wishes_day_statuses.map((row) => ({
    name: wishStatusLabel(locale, row.status),
    value: row.count,
  }));
  const fill = data.current_period ? fillPercent(data.current_period) : 0;

  useEffect(() => {
    setCategoryMonth(defaultCategoryMonth(data));
  }, [data.year, data.current_period?.month]);

  return (
    <div className="grid gap-5">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <DashboardKpiTile label={t(locale, "dashboardMyShiftsYear")} value={totalShiftsYear} />
        <DashboardKpiTile label={t(locale, "dashboardMyErrors")} value={data.my_validation_errors} />
        <DashboardKpiTile label={t(locale, "dashboardMyWarnings")} value={data.my_validation_warnings} />
        <DashboardKpiTile label={t(locale, "dashboardFillRate")} value={data.current_period ? `${fill}%` : "—"} />
      </div>
      <DashboardSection title={t(locale, "dashboardUpcomingShifts")}>
        <p className="mb-3 text-sm text-slate-600">{t(locale, "dashboardUpcomingShiftsHint")}</p>
        <DashboardUpcomingShiftsTable locale={locale} slots={data.upcoming_slots} />
      </DashboardSection>
      <div className="grid gap-5 lg:grid-cols-2">
        <DashboardSection title={t(locale, "dashboardMyShiftsByMonth")}>
          <DashboardStackedMonthTemplateChart locale={locale} series={shiftsByMonth} />
        </DashboardSection>
        <DashboardSection title={t(locale, "dashboardMyTemplateMix")}>
          <label className="mb-4 flex flex-wrap items-center gap-2 text-sm text-slate-600">
            {t(locale, "month")}
            <select
              className="rounded-md border border-slate-200 bg-white px-2 py-1.5 text-sm"
              value={categoryMonth}
              onChange={(event) => setCategoryMonth(Number(event.target.value))}
            >
              {Array.from({ length: 12 }, (_, index) => {
                const month = index + 1;
                return (
                  <option key={month} value={month}>
                    {formatMonthLong(locale, data.year, month)}
                  </option>
                );
              })}
            </select>
          </label>
          <DashboardTemplateBarChart locale={locale} templates={templateData} />
        </DashboardSection>
      </div>
      {data.wishes_day_statuses.length > 0 ? (
        <DashboardSection title={t(locale, "dashboardMyWishesMonth")}>
          <DashboardDonutChart data={wishesChart} />
        </DashboardSection>
      ) : null}
      <DashboardSection title={t(locale, "dashboardMyPeriods")}>
        <DashboardPeriodCards
          locale={locale}
          periods={data.periods}
          hrefForPeriod={(id) => myPlanningDeepLink(id, shiftGroupId)}
        />
      </DashboardSection>
      <Link
        href={
          data.current_period
            ? myPlanningDeepLink(data.current_period.period_id, shiftGroupId)
            : "/my-planning"
        }
        className="inline-flex rounded-lg bg-ink px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800"
      >
        {t(locale, "dashboardOpenMyPlanning")}
      </Link>
    </div>
  );
}
