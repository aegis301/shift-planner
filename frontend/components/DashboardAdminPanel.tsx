"use client";

import Link from "next/link";
import {
  DashboardCategoryBarChart,
  DashboardDonutChart,
  DashboardStackedMonthChart,
} from "@/components/dashboardCharts";
import { DashboardKpiTile, DashboardPeriodCards, DashboardSection } from "@/components/DashboardShared";
import type { AdminDashboard } from "@/lib/dashboard";
import { planningDeepLink, periodLabel } from "@/lib/dashboard";
import type { Locale, TranslationKey } from "@/lib/i18n";
import { t } from "@/lib/i18n";

function statusLabel(locale: Locale, status: string): string {
  const map: Record<string, TranslationKey> = {
    draft: "periodStatusDraft",
    preliminary: "periodStatusPreliminary",
    published: "periodStatusPublished",
  };
  const key = map[status];
  return key ? t(locale, key) : status;
}

export function DashboardAdminPanel({
  locale,
  data,
  shiftGroupId,
}: {
  locale: Locale;
  data: AdminDashboard;
  shiftGroupId: string;
}) {
  const statusChart = data.period_status_counts.map((row) => ({
    name: statusLabel(locale, row.status),
    value: row.count,
  }));
  const staffChart = [
    { name: t(locale, "dashboardStaffLinked"), value: data.staff_snapshot.linked_ok },
    { name: t(locale, "dashboardStaffTeamOnly"), value: data.staff_snapshot.team_member_only },
    { name: t(locale, "dashboardStaffLoginUnlinked"), value: data.staff_snapshot.login_unlinked },
    { name: t(locale, "dashboardStaffLoginOnly"), value: data.staff_snapshot.login_only },
  ].filter((row) => row.value > 0);

  return (
    <div className="grid gap-5">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <DashboardKpiTile label={t(locale, "dashboardKpiTeamMembers")} value={data.kpis.active_team_members} />
        <DashboardKpiTile label={t(locale, "dashboardKpiShiftGroups")} value={data.kpis.active_shift_groups} />
        <DashboardKpiTile label={t(locale, "dashboardKpiTemplates")} value={data.kpis.active_shift_templates} />
        <DashboardKpiTile label={t(locale, "dashboardKpiJoinRequests")} value={data.kpis.pending_join_requests} />
      </div>
      {data.current_period ? (
        <DashboardSection title={t(locale, "dashboardCurrentMonth")}>
          <p className="text-sm text-slate-600">
            {periodLabel(data.current_period.year, data.current_period.month)} — {t(locale, "dashboardFillRate")}{" "}
            {Math.round(
              (100 * data.current_period.assigned_count) / Math.max(1, data.current_period.slot_count)
            )}
            % · {t(locale, "dashboardUnassigned")} {data.current_period.unassigned_count}
          </p>
        </DashboardSection>
      ) : null}
      <div className="grid gap-5 lg:grid-cols-2">
        <DashboardSection title={t(locale, "dashboardPeriodStatusChart")}>
          <DashboardDonutChart data={statusChart} />
        </DashboardSection>
        <DashboardSection title={t(locale, "dashboardStaffSnapshot")}>
          <DashboardDonutChart data={staffChart} />
        </DashboardSection>
      </div>
      <DashboardSection title={t(locale, "dashboardYearDistribution", { year: String(data.year) })}>
        <DashboardStackedMonthChart locale={locale} series={data.year_shift_distribution} />
      </DashboardSection>
      <DashboardSection title={t(locale, "dashboardPlanningPipeline")}>
        <DashboardPeriodCards
          locale={locale}
          periods={data.periods}
          hrefForPeriod={(id) => planningDeepLink(id, shiftGroupId || undefined)}
        />
      </DashboardSection>
      <div className="flex flex-wrap gap-3">
        <Link
          href="/organization/team"
          className="rounded-lg bg-ink px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800"
        >
          {t(locale, "navTeamManagement")}
        </Link>
        <Link
          href="/organization/shifts/groups"
          className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-ink hover:bg-slate-50"
        >
          {t(locale, "navShiftManagement")}
        </Link>
        <Link
          href="/planning"
          className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-ink hover:bg-slate-50"
        >
          {t(locale, "planning")}
        </Link>
      </div>
    </div>
  );
}
