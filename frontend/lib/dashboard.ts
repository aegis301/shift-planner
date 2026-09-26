import { apiFetch } from "@/lib/api";
import type {
  AdminDashboard,
  DashboardPeriodCard,
  MonthCategorySeries,
  MonthTemplateSeries,
  PlannerDashboard,
  ShiftCategoryCount,
  ShiftTemplateCount,
  TeamMemberDashboard
} from "@/lib/api/types";
import type { Locale } from "@/lib/i18n";

export type {
  AdminDashboard,
  DashboardPeriodCard,
  MonthCategorySeries,
  MonthTemplateSeries,
  PlannerDashboard,
  ShiftCategoryCount,
  ShiftTemplateCount,
  TeamMemberDashboard
} from "@/lib/api/types";

export function periodLabel(year: number, month: number): string {
  return `${year}-${String(month).padStart(2, "0")}`;
}

export function formatMonthShort(locale: Locale, year: number, month: number): string {
  return new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-GB", { month: "short" }).format(
    new Date(year, month - 1, 1)
  );
}

export function formatMonthLong(locale: Locale, year: number, month: number): string {
  return new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-GB", {
    month: "long",
    year: "numeric",
  }).format(new Date(year, month - 1, 1));
}

export function monthSeriesForYear(year: number, series: MonthCategorySeries[]): MonthCategorySeries[] {
  const byMonth = new Map(series.map((row) => [row.month, row]));
  return Array.from({ length: 12 }, (_, index) => {
    const month = index + 1;
    return byMonth.get(month) ?? { year, month, categories: [] };
  });
}

export function monthTemplateSeriesForYear(year: number, series: MonthTemplateSeries[]): MonthTemplateSeries[] {
  const byMonth = new Map(series.map((row) => [row.month, row]));
  return Array.from({ length: 12 }, (_, index) => {
    const month = index + 1;
    return byMonth.get(month) ?? { year, month, templates: [] };
  });
}

export function shiftTemplateChartLabel(locale: Locale, row: ShiftTemplateCount): string {
  const name = (row.template_name)?.trim();
  if (name) {
    return row.template_code ? `${name} (${row.template_code})` : name;
  }
  return row.template_code ?? String(row.shift_template_id);
}

export function fillPercent(card: DashboardPeriodCard): number {
  if (card.slot_count === 0) {
    return 0;
  }
  return Math.round((100 * card.assigned_count) / card.slot_count);
}

export function fetchAdminDashboard(params: { year?: number; shiftGroupId?: string }): Promise<AdminDashboard> {
  const search = new URLSearchParams();
  if (params.year != null) {
    search.set("year", String(params.year));
  }
  if (params.shiftGroupId) {
    search.set("shift_group_id", params.shiftGroupId);
  }
  const qs = search.toString();
  return apiFetch<AdminDashboard>(`/api/v1/dashboard/admin${qs ? `?${qs}` : ""}`);
}

export function fetchPlannerDashboard(params: {
  year?: number;
  shiftGroupId?: string;
}): Promise<PlannerDashboard> {
  const search = new URLSearchParams();
  if (params.year != null) {
    search.set("year", String(params.year));
  }
  if (params.shiftGroupId) {
    search.set("shift_group_id", params.shiftGroupId);
  }
  const qs = search.toString();
  return apiFetch<PlannerDashboard>(`/api/v1/dashboard/planner${qs ? `?${qs}` : ""}`);
}

export function fetchTeamMemberDashboard(params: {
  year?: number;
  shiftGroupId?: string;
}): Promise<TeamMemberDashboard> {
  const search = new URLSearchParams();
  if (params.year != null) {
    search.set("year", String(params.year));
  }
  if (params.shiftGroupId) {
    search.set("shift_group_id", params.shiftGroupId);
  }
  const qs = search.toString();
  return apiFetch<TeamMemberDashboard>(`/api/v1/dashboard/team-member${qs ? `?${qs}` : ""}`);
}

export function planningDeepLink(periodId: number, shiftGroupId?: string): string {
  const params = new URLSearchParams();
  params.set("period", String(periodId));
  if (shiftGroupId) {
    params.set("shiftGroup", shiftGroupId);
  }
  return `/planning?${params.toString()}`;
}

export function myPlanningDeepLink(periodId: number, shiftGroupId?: string): string {
  const params = new URLSearchParams();
  params.set("period", String(periodId));
  if (shiftGroupId) {
    params.set("shiftGroup", shiftGroupId);
  }
  return `/my-planning?${params.toString()}`;
}
