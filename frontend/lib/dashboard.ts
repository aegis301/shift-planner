import { apiFetch } from "@/lib/api";
import type { Locale } from "@/lib/i18n";

export type DashboardPeriodCard = {
  period_id: number;
  year: number;
  month: number;
  status: string;
  slot_count: number;
  assigned_count: number;
  unassigned_count: number;
  validation_errors: number;
  validation_warnings: number;
};

export type ShiftCategoryCount = { category: string; count: number };

export type ShiftTemplateCount = {
  shift_template_id: number;
  template_code: string | null;
  template_name: string | null;
  count: number;
};

export type MonthCategorySeries = {
  year: number;
  month: number;
  categories: ShiftCategoryCount[];
};

export type MonthTemplateSeries = {
  year: number;
  month: number;
  templates: ShiftTemplateCount[];
};

export type AdminDashboard = {
  year: number;
  shift_group_id: number | null;
  kpis: {
    active_team_members: number;
    active_shift_groups: number;
    active_shift_templates: number;
    pending_join_requests: number;
  };
  staff_snapshot: {
    linked_ok: number;
    team_member_only: number;
    login_unlinked: number;
    linked_wrong_user: number;
    linked_foreign_user: number;
    login_only: number;
  };
  period_status_counts: { status: string; count: number }[];
  periods: DashboardPeriodCard[];
  year_shift_distribution: MonthCategorySeries[];
  current_period: DashboardPeriodCard | null;
};

export type PlannerDashboard = {
  year: number;
  shift_group_id: number | null;
  shift_group_code: string;
  shift_group_name: string;
  shift_group_member_count: number;
  current_period: DashboardPeriodCard | null;
  periods: DashboardPeriodCard[];
  current_month_categories: ShiftCategoryCount[];
  workload_rows: {
    team_member_id: number;
    name: string;
    employment_percentage: number;
    total: number;
    on_call_duty: number;
    standby_duty: number;
    late_duty: number;
    other: number;
    weekend_holiday_shifts: number;
    conflicts: number;
  }[];
  unassigned_slots: number;
  validation_by_code: { code: string; count: number; severity: "warning" | "error" }[];
  wishes_response_percent: number;
  wishes_responded_count: number;
  wishes_total_count: number;
};

export type TeamMemberDashboard = {
  year: number;
  shift_group_id: number | null;
  team_member_id: number;
  periods: DashboardPeriodCard[];
  shifts_by_month: MonthTemplateSeries[];
  current_period: DashboardPeriodCard | null;
  wishes_day_statuses: { status: string; count: number }[];
  my_validation_errors: number;
  my_validation_warnings: number;
  upcoming_slots: {
    slot_date: string;
    template_code: string | null;
    template_name: string | null;
    starts_at: string | null;
    ends_at: string | null;
    category: string | null;
    variant_label: string | null;
    day_class: string | null;
    period_year: number | null;
    period_month: number | null;
  }[];
};

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
