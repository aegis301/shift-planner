import { apiFetch, API_BASE_URL } from "@/lib/api";

export type Weekday = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";

export type WorkerGroupCategoryRule = {
  category: "bereitschaftsdienst" | "rufdienst" | "spaetdienst" | "other";
  counts_toward_contract: boolean;
  credit_mode: "duration" | "none";
};

export type WorkerGroupStatusMapping = {
  code: string;
  absence_kind: "vacation" | "sick" | "other" | "none";
  consumes_vacation: boolean;
  counts_as_work_day: boolean;
};

export type RegularWeekdayHours = {
  weekday: Weekday;
  starts_at: string;
  ends_at: string;
};

export type WorkerGroup = {
  id: number;
  name: string;
  weekly_hours_at_100: number;
  vacation_days_at_100: number;
  regular_week_pattern: RegularWeekdayHours[];
  category_rules: WorkerGroupCategoryRule[];
  status_mappings: WorkerGroupStatusMapping[];
  display_order: number;
  is_active: boolean;
};

export type EmploymentPeriod = {
  id: number;
  team_member_id: number;
  worker_group_id: number;
  worker_group_name: string | null;
  employment_percentage: number;
  start_date: string;
  end_date: string | null;
};

export type TimeAccountOpening = {
  id: number;
  team_member_id: number;
  as_of_date: string;
  overtime_minutes: number;
  vacation_days_remaining: number;
  sick_days_used_ytd: number;
};

export type TimeEntry = {
  id: number;
  team_member_id: number;
  entry_date: string;
  kind: string;
  source: string;
  all_day: boolean;
  started_at: string | null;
  ended_at: string | null;
  duration_minutes: number;
  counts_toward_contract: boolean;
  shift_template_category: string | null;
  planning_day_status_code: string | null;
  roster_slot_id: number | null;
  comment: string | null;
};

export type TimesheetDayPlan = {
  started_at: string | null;
  ended_at: string | null;
  duration_minutes: number;
  category: string | null;
  roster_slot_id: number | null;
  counts_toward_contract: boolean;
};

export type TimesheetDay = {
  date: string;
  expected_minutes: number;
  worked_contract_minutes: number;
  worked_extra_minutes: number;
  absence_kind: string | null;
  vacation_days: number;
  sick_days: number;
  roster_plan_minutes: number;
  delta_minutes: number;
  entries: TimeEntry[];
  roster_plan: TimesheetDayPlan[];
};

export type Timesheet = {
  team_member_id: number;
  name: string;
  from_date: string;
  to_date: string;
  worker_group_name: string | null;
  employment_percentage: number | null;
  expected_minutes: number;
  worked_contract_minutes: number;
  worked_extra_minutes: number;
  overtime_minutes: number;
  vacation_days: number;
  sick_days: number;
  vacation_days_remaining: number;
  days: TimesheetDay[];
};

export type TimesheetSummary = {
  team_member_id: number;
  name: string;
  worker_group_name: string | null;
  employment_percentage: number | null;
  expected_minutes: number;
  worked_contract_minutes: number;
  worked_extra_minutes: number;
  overtime_minutes: number;
  vacation_days: number;
  sick_days: number;
  vacation_days_remaining: number;
  roster_plan_minutes: number;
};

export function formatHoursFromMinutes(minutes: number): string {
  const hours = minutes / 60;
  return Number.isInteger(hours) ? String(hours) : hours.toFixed(1);
}

export function fetchWorkerGroups(activeOnly = false): Promise<WorkerGroup[]> {
  const q = activeOnly ? "?active_only=true" : "";
  return apiFetch<WorkerGroup[]>(`/api/v1/worker-groups${q}`);
}

export function fetchHoursSummaries(year: number, month: number): Promise<TimesheetSummary[]> {
  return apiFetch<TimesheetSummary[]>(`/api/v1/hours/summaries?year=${year}&month=${month}`);
}

export function fetchTimesheet(teamMemberId: number, year: number, month: number): Promise<Timesheet> {
  return apiFetch<Timesheet>(`/api/v1/hours/members/${teamMemberId}/timesheet?year=${year}&month=${month}`);
}

export function timesheetCsvHref(teamMemberId: number, year: number, month: number): string {
  return `${API_BASE_URL}/api/v1/hours/members/${teamMemberId}/timesheet.csv?year=${year}&month=${month}`;
}
