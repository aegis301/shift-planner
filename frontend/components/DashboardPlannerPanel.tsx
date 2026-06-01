"use client";

import Link from "next/link";
import {
  DashboardCategoryBarChart,
  DashboardDonutChart,
  DashboardHorizontalBarChart,
} from "@/components/dashboardCharts";
import { DashboardKpiTile, DashboardPeriodCards, DashboardSection } from "@/components/DashboardShared";
import type { PlannerDashboard } from "@/lib/dashboard";
import { fillPercent, planningDeepLink, periodLabel } from "@/lib/dashboard";
import type { Locale } from "@/lib/i18n";
import { t } from "@/lib/i18n";

export function DashboardPlannerPanel({
  locale,
  data,
  shiftGroupId,
}: {
  locale: Locale;
  data: PlannerDashboard;
  shiftGroupId: string;
}) {
  const groupLabel =
    data.shift_group_id == null
      ? t(locale, "allShiftGroupsLabel")
      : locale === "de"
        ? data.shift_group_name_de || data.shift_group_code
        : data.shift_group_name_en || data.shift_group_code;
  const validationChart = data.validation_by_code.map((row) => ({
    name: row.code,
    value: row.count,
  }));
  const workloadChart = data.workload_rows.map((row) => ({
    name: row.name,
    value: row.total,
  }));
  const fill = data.current_period ? fillPercent(data.current_period) : 0;

  return (
    <div className="grid gap-5">
      <p className="text-sm text-slate-600">
        {t(locale, "dashboardPlannerScope")}: <span className="font-semibold text-ink">{groupLabel}</span> ·{" "}
        {data.shift_group_member_count} {t(locale, "dashboardMembers")}
      </p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <DashboardKpiTile label={t(locale, "dashboardFillRate")} value={`${fill}%`} />
        <DashboardKpiTile label={t(locale, "dashboardUnassigned")} value={data.unassigned_slots} />
        <DashboardKpiTile
          label={t(locale, "dashboardWishesProgress")}
          value={`${data.wishes_response_percent}%`}
        />
        <DashboardKpiTile
          label={t(locale, "dashboardWishesResponded")}
          value={`${data.wishes_responded_count}/${data.wishes_total_count}`}
        />
      </div>
      {data.current_period ? (
        <DashboardSection title={t(locale, "dashboardCurrentMonth")}>
          <p className="mb-3 text-sm text-slate-600">
            {periodLabel(data.current_period.year, data.current_period.month)}
          </p>
          <DashboardCategoryBarChart locale={locale} categories={data.current_month_categories} />
        </DashboardSection>
      ) : null}
      <div className="grid gap-5 lg:grid-cols-2">
        <DashboardSection title={t(locale, "dashboardWorkloadPreview")}>
          <DashboardHorizontalBarChart data={workloadChart} />
        </DashboardSection>
        <DashboardSection title={t(locale, "dashboardValidationSummary")}>
          <DashboardDonutChart data={validationChart} />
        </DashboardSection>
      </div>
      <DashboardSection title={t(locale, "dashboardPlanningPipeline")}>
        <DashboardPeriodCards
          locale={locale}
          periods={data.periods}
          hrefForPeriod={(id) => planningDeepLink(id, shiftGroupId)}
        />
      </DashboardSection>
      <Link
        href={data.current_period ? planningDeepLink(data.current_period.period_id, shiftGroupId) : "/planning"}
        className="inline-flex rounded-lg bg-ink px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800"
      >
        {t(locale, "dashboardOpenPlanning")}
      </Link>
    </div>
  );
}
