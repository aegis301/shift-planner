"use client";

import { FormEvent, useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { BarChart3, ChevronDown, Download, RefreshCw, Save } from "lucide-react";
import { API_BASE_URL, ApiError, apiFetch } from "@/lib/api";
import {
  formatWorkloadPeriodLabel,
  workloadRowForMember,
  type RosterWorkloadMatrixSlice,
  type RosterWorkloadWarning
} from "@/lib/rosterWorkload";
import { dataTableScrollShellClassName } from "@/lib/dataTableLayout";
import { teamMemberPlanningDisplayName } from "@/lib/teamMemberDisplay";
import { t, type Locale, type TranslationKey } from "@/lib/i18n";
import {
  planningDayStatusBadgeClass,
  planningDayStatusByCode,
  planningDayStatusLabel,
  planningDayStatusSolidClass,
  rosterBlocksForPlanningDayStatusCode,
  type PlanningDayStatusDefinition
} from "@/lib/planningDayStatus";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";

type ShiftIntentKind = "wish" | "no_go";

type RosterMatrixTeamMember = {
  id: number;
  first_name: string;
  last_name: string;
  nickname?: string | null;
  email: string;
  employment_percentage: number;
  planning_preferences?: string | null;
};

type MatrixDay = {
  date: string;
  weekday: string;
};

type PlanningPeriod = {
  id: number;
  year: number;
  month: number;
  status: string;
};

type SlotCategory = "bereitschaftsdienst" | "rufdienst" | "spaetdienst" | "other";
type DayClass = "weekday" | "weekend" | "holiday" | "any";

type RosterSlot = {
  id: number;
  planning_period_id: number;
  shift_template_id: number | null;
  shift_variant_id: number | null;
  slot_date: string;
  position: number;
  label: string | null;
  starts_at: string | null;
  ends_at: string | null;
  day_class: string | null;
  template_code: string | null;
  template_name: string | null;
  variant_label: string | null;
  category: SlotCategory | null;
};

type ShiftTemplateSummary = {
  id: number;
  code: string;
  name: string;
  category: SlotCategory;
  display_order: number;
  is_active: boolean;
};

type RosterSlotAssignment = {
  id: number;
  roster_slot_id: number;
  team_member_id: number;
  manual_override: boolean;
};

type PlanningCell = {
  id: number;
  planning_period_id: number;
  team_member_id: number;
  cell_date: string;
  status: string;
  comment: string | null;
};

type RosterShiftIntent = {
  cell_date: string;
  team_member_id: number;
  shift_template_id: number;
  kind: ShiftIntentKind;
};

type ShiftGroupPlanningStatus = {
  shift_group_id: number;
  status: "draft" | "preliminary" | "published";
  published_at?: string | null;
};

export type RosterMatrix = {
  planning_period: PlanningPeriod;
  shift_group_planning_status?: ShiftGroupPlanningStatus | null;
  team_members: RosterMatrixTeamMember[];
  days: MatrixDay[];
  shift_templates: ShiftTemplateSummary[];
  slots: RosterSlot[];
  assignments: RosterSlotAssignment[];
  planning_cells: PlanningCell[];
  day_status_definitions: PlanningDayStatusDefinition[];
  shift_intents: RosterShiftIntent[];
};

function formatDate(locale: Locale, value: string) {
  return new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-GB", {
    weekday: "short",
    day: "2-digit",
    month: "2-digit"
  }).format(new Date(`${value}T12:00:00`));
}

function teamMemberLabel(member: RosterMatrixTeamMember): string {
  return teamMemberPlanningDisplayName(member);
}

function teamMemberMatchesQuery(member: RosterMatrixTeamMember, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) {
    return true;
  }
  const label = teamMemberLabel(member).toLowerCase();
  const nick = (member.nickname ?? "").trim().toLowerCase();
  return (
    label.includes(q) ||
    nick.includes(q) ||
    member.first_name.toLowerCase().includes(q) ||
    member.last_name.toLowerCase().includes(q) ||
    member.email.toLowerCase().includes(q)
  );
}

function formatTimeRange(slot: RosterSlot) {
  if (!slot.starts_at || !slot.ends_at) {
    return "";
  }
  const parseDateAndTime = (value: string): { date: string; time: string } | null => {
    const match = value.match(/(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/);
    if (!match) {
      return null;
    }
    return { date: match[1], time: match[2] };
  };

  const startParts = parseDateAndTime(slot.starts_at);
  const endParts = parseDateAndTime(slot.ends_at);

  if (startParts && endParts) {
    const nextDay = startParts.date !== endParts.date ? " +1" : "";
    return `${startParts.time}-${endParts.time}${nextDay}`;
  }

  const start = new Date(slot.starts_at);
  const end = new Date(slot.ends_at);
  const startText = start.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  const endText = end.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  const nextDay = start.toDateString() !== end.toDateString() ? " +1" : "";
  return `${startText}-${endText}${nextDay}`;
}

function dayClassPillClass(dayClass: string | null): string {
  if (dayClass === "weekday") {
    return "bg-sky-50 text-sky-800 ring-sky-200";
  }
  if (dayClass === "weekend") {
    return "bg-violet-50 text-violet-800 ring-violet-200";
  }
  if (dayClass === "holiday") {
    return "bg-rose-50 text-rose-800 ring-rose-200";
  }
  return "bg-slate-50 text-slate-700 ring-slate-200";
}

function dayClassLabel(locale: Locale, dayClass: string): string {
  const labels: Record<DayClass, TranslationKey> = {
    any: "anyDay",
    weekday: "weekday",
    weekend: "weekend",
    holiday: "holiday"
  };
  return dayClass in labels ? t(locale, labels[dayClass as DayClass]) : dayClass;
}

function dayClassAcronym(dayClass: string): string {
  if (dayClass === "weekday") {
    return "WT";
  }
  if (dayClass === "weekend") {
    return "WE";
  }
  if (dayClass === "holiday") {
    return "FT";
  }
  return dayClass.toUpperCase();
}

function DayClassPill({ dayClass, locale }: { dayClass: string; locale: Locale }) {
  return (
    <span
      title={dayClassLabel(locale, dayClass)}
      className={`inline-flex rounded-full px-1 py-0 text-[0.58rem] font-semibold uppercase ring-1 ${dayClassPillClass(dayClass)}`}
    >
      {dayClassAcronym(dayClass)}
    </span>
  );
}

function categoryLabel(locale: Locale, category: SlotCategory): string {
  if (category === "bereitschaftsdienst") {
    return t(locale, "onCallDutyCategory");
  }
  if (category === "rufdienst") {
    return t(locale, "standbyDutyCategory");
  }
  if (category === "spaetdienst") {
    return t(locale, "lateDutyCategory");
  }
  return t(locale, "other");
}

function buildTemplateColumns(matrix: RosterMatrix, locale: Locale): ShiftTemplateSummary[] {
  const usedTemplateIds = new Set<number>();
  for (const slot of matrix.slots) {
    if (slot.shift_template_id !== null) {
      usedTemplateIds.add(slot.shift_template_id);
    }
  }

  const shiftTemplates = matrix.shift_templates ?? [];
  const templatesById = new Map(shiftTemplates.map((template) => [template.id, template]));
  const ordered: ShiftTemplateSummary[] = [...shiftTemplates]
    .filter((template) => usedTemplateIds.has(template.id))
    .sort((a, b) => a.display_order - b.display_order || a.name.localeCompare(b.name) || a.code.localeCompare(b.code));

  const missingIds = [...usedTemplateIds].filter((id) => !templatesById.has(id));
  for (const id of missingIds.sort((a, b) => a - b)) {
    const sample = matrix.slots.find((slot) => slot.shift_template_id === id);
    ordered.push({
      id,
      code: sample?.template_code ?? String(id),
      name: sample?.template_name ?? String(id),
      category: sample?.category ?? "other",
      display_order: 0,
      is_active: true
    });
  }

  if (matrix.slots.some((slot) => slot.shift_template_id === null)) {
    ordered.push({
      id: -1,
      code: "?",
      name: t(locale, "unknownShiftTemplate"),
      category: "other",
      display_order: 9999,
      is_active: true
    });
  }

  return ordered;
}

function dayClassForDate(slots: RosterSlot[]): string | null {
  for (const slot of slots) {
    if (slot.day_class) {
      return slot.day_class;
    }
  }
  return null;
}

function slotsForTemplateDay(slotsByDay: Map<string, RosterSlot[]>, dayDate: string, templateId: number): RosterSlot[] {
  return (slotsByDay.get(dayDate) ?? []).filter((slot) => (slot.shift_template_id ?? -1) === templateId);
}

function slotDiscriminator(slot: RosterSlot, needsDiscriminator: boolean): string {
  if (slot.variant_label) {
    return slot.variant_label;
  }
  if (slot.position > 1) {
    return `#${slot.position}`;
  }
  if (needsDiscriminator) {
    return `#${slot.id}`;
  }
  return "";
}

export function RosterMatrixEditor({
  periodId: controlledPeriodId,
  compact = false,
  reloadToken = 0,
  shiftGroupId,
  versionId,
  readOnly = false,
  duplicateMemberDayKeys,
  validationWarnings = [],
  onMatrixChange,
  highlightTeamMemberId,
}: {
  periodId?: string;
  compact?: boolean;
  reloadToken?: number;
  shiftGroupId?: string;
  versionId?: number;
  readOnly?: boolean;
  duplicateMemberDayKeys?: ReadonlySet<string>;
  validationWarnings?: RosterWorkloadWarning[];
  onMatrixChange?: (matrix: RosterMatrix) => void | Promise<void>;
  highlightTeamMemberId?: number;
} = {}) {
  const { locale } = useLocale();
  const currentDate = new Date();
  const [periodId, setPeriodId] = useState("1");
  const [newYear, setNewYear] = useState(String(currentDate.getFullYear()));
  const [newMonth, setNewMonth] = useState(String(currentDate.getMonth() + 1));
  const [matrix, setMatrix] = useState<RosterMatrix | null>(null);
  const [message, setMessage] = useState("");
  const [savingAssignments, setSavingAssignments] = useState(0);

  const groupQuery = useMemo(() => {
    const params = new URLSearchParams();
    if (shiftGroupId) {
      params.set("shift_group_id", shiftGroupId);
    }
    if (readOnly) {
      params.set("team_member_portal", "true");
    }
    const qs = params.toString();
    return qs ? `?${qs}` : "";
  }, [readOnly, shiftGroupId]);

  const slotsByDay = useMemo(() => {
    const map = new Map<string, RosterSlot[]>();
    matrix?.slots.forEach((slot) => {
      const daySlots = map.get(slot.slot_date) ?? [];
      daySlots.push(slot);
      daySlots.sort((a, b) => (a.starts_at ?? "").localeCompare(b.starts_at ?? "") || a.position - b.position);
      map.set(slot.slot_date, daySlots);
    });
    return map;
  }, [matrix]);

  const assignmentMap = useMemo(() => {
    const map = new Map<number, RosterSlotAssignment>();
    matrix?.assignments.forEach((assignment) => map.set(assignment.roster_slot_id, assignment));
    return map;
  }, [matrix]);

  const planningCellMap = useMemo(() => {
    const map = new Map<string, PlanningCell>();
    matrix?.planning_cells.forEach((cell) => map.set(`${cell.cell_date}:${cell.team_member_id}`, cell));
    return map;
  }, [matrix]);

  const intentMap = useMemo(() => {
    const map = new Map<string, ShiftIntentKind>();
    matrix?.shift_intents?.forEach((row) => {
      map.set(`${row.cell_date}:${row.team_member_id}:${row.shift_template_id}`, row.kind);
    });
    return map;
  }, [matrix]);

  const templateColumns = useMemo(() => (matrix ? buildTemplateColumns(matrix, locale) : []), [matrix, locale]);

  const activePeriodId = controlledPeriodId ?? periodId;

  const publishMatrix = useCallback(
    async (next: RosterMatrix) => {
      const normalized: RosterMatrix = { ...next, shift_intents: next.shift_intents ?? [] };
      setMatrix(normalized);
      await onMatrixChange?.(normalized);
    },
    [onMatrixChange]
  );

  const loadRosterById = useCallback(async (nextPeriodId: string) => {
    const next = await apiFetch<RosterMatrix>(
      versionId
        ? `/api/v1/planning-periods/${nextPeriodId}/versions/${versionId}/roster-matrix`
        : `/api/v1/roster-matrix/${nextPeriodId}${groupQuery}`
    );
    await publishMatrix(next);
  }, [publishMatrix, groupQuery, versionId]);

  const loadRoster = useCallback(async () => {
    await loadRosterById(activePeriodId);
  }, [activePeriodId, loadRosterById]);

  useEffect(() => {
    if (controlledPeriodId) {
      void loadRosterById(controlledPeriodId);
      return;
    }

    async function loadLatestPeriod() {
      const periods = await apiFetch<PlanningPeriod[]>("/api/v1/planning-periods");
      const latest = periods[0];
      if (!latest) {
        return;
      }
      const nextPeriodId = String(latest.id);
      setPeriodId(nextPeriodId);
      await loadRosterById(nextPeriodId);
    }

    void loadLatestPeriod();
  }, [controlledPeriodId, loadRosterById, reloadToken, groupQuery]);

  async function createAndLoadPeriod(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const period = await apiFetch<PlanningPeriod>("/api/v1/planning-periods", {
      method: "POST",
      body: JSON.stringify({ year: Number(newYear), month: Number(newMonth) })
    });
    const nextPeriodId = String(period.id);
    setPeriodId(nextPeriodId);
    await loadRosterById(nextPeriodId);
    setMessage(`${t(locale, "saved")}: ${t(locale, "periodId")} ${nextPeriodId}`);
  }

  async function manualSave() {
    await loadRoster();
    setMessage(t(locale, "saved"));
  }

  async function saveAssignment(rosterSlotId: number, memberId: number | "", manualOverride = false): Promise<boolean> {
    if (readOnly) {
      return false;
    }
    setSavingAssignments((count) => count + 1);
    try {
      if (!memberId) {
        await apiFetch(`/api/v1/roster-matrix/assignments/clear?shift_group_id=${shiftGroupId ?? ""}`, {
          method: "POST",
          body: JSON.stringify({ roster_slot_id: rosterSlotId })
        });
        if (matrix) {
          await publishMatrix({
            ...matrix,
            assignments: matrix.assignments.filter((assignment) => assignment.roster_slot_id !== rosterSlotId)
          });
        }
      } else {
        const saved = await apiFetch<RosterSlotAssignment>(
          `/api/v1/roster-matrix/assignments?shift_group_id=${shiftGroupId ?? ""}`,
          {
          method: "PUT",
          body: JSON.stringify({
            roster_slot_id: rosterSlotId,
            team_member_id: memberId,
            comment: null,
            manual_override: manualOverride
          })
        }
        );
        if (matrix) {
          await publishMatrix({
            ...matrix,
            assignments: [
              ...matrix.assignments.filter((assignment) => assignment.roster_slot_id !== rosterSlotId),
              saved
            ]
          });
        }
      }
      setMessage(t(locale, "autosaved"));
      return true;
    } catch (error) {
      if (error instanceof ApiError) {
        setMessage(error.message);
      }
      return false;
    } finally {
      setSavingAssignments((count) => Math.max(0, count - 1));
    }
  }

  return (
    <div className="grid gap-5">
      {!compact ? (
        <Card>
          <div className="grid gap-5">
            <div>
              <h1 className="text-2xl font-semibold text-ink">{t(locale, "finalRosterMatrix")}</h1>
              <p className="mt-2 max-w-3xl text-sm text-slate-600">{t(locale, "finalRosterHelp")}</p>
            </div>
            <form className="flex flex-wrap items-end gap-2 rounded-lg bg-slate-50 p-3 ring-1 ring-slate-200" onSubmit={createAndLoadPeriod}>
              <Field label={t(locale, "year")}>
                <input className={`${inputClass} w-28`} value={newYear} onChange={(event) => setNewYear(event.target.value)} type="number" min="2020" max="2100" />
              </Field>
              <Field label={t(locale, "month")}>
                <input className={`${inputClass} w-24`} value={newMonth} onChange={(event) => setNewMonth(event.target.value)} type="number" min="1" max="12" />
              </Field>
              <button className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-mint px-4 text-sm font-semibold text-ink">
                <Save size={17} />
                {t(locale, "createAndLoadPeriod")}
              </button>
            </form>
            <div className="flex flex-wrap items-end gap-2">
              <label className="grid gap-1 text-sm font-medium text-slate-700">
                {t(locale, "periodId")}
                <input className={`${inputClass} w-24`} value={periodId} onChange={(event) => setPeriodId(event.target.value)} />
              </label>
              <button
                className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white"
                onClick={loadRoster}
                type="button"
              >
                <RefreshCw size={17} />
                {t(locale, "loadRoster")}
              </button>
              <button
                className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-mint px-4 text-sm font-semibold text-ink"
                onClick={manualSave}
                title={t(locale, "saveNowHint")}
                type="button"
              >
                <Save size={17} />
                {t(locale, "saveNow")}
              </button>
              <a
                className="inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700"
                href={`${API_BASE_URL}/api/v1/exports/roster-matrix/${activePeriodId}.csv${groupQuery}`}
              >
                <Download size={17} />
                {t(locale, "rosterCsvExport")}
              </a>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-3 text-sm">
            {savingAssignments > 0 ? <p className="text-slate-600">{t(locale, "saving")}</p> : null}
            {message ? <p className="text-emerald-700">{message}</p> : null}
          </div>
        </Card>
      ) : (
        <div className="flex flex-wrap gap-3 text-sm">
          {savingAssignments > 0 ? <p className="text-slate-600">{t(locale, "saving")}</p> : null}
          {message ? <p className="text-emerald-700">{message}</p> : null}
        </div>
      )}

      {matrix ? (
        matrix.slots.length > 0 ? (
          <>
            <DesktopRosterMatrix
              matrix={matrix}
              workloadMatrix={matrix}
              workloadWarnings={validationWarnings}
              planningPeriodLabel={formatWorkloadPeriodLabel(matrix.planning_period)}
              slotsByDay={slotsByDay}
              assignmentMap={assignmentMap}
              planningCellMap={planningCellMap}
              intentMap={intentMap}
              onSave={saveAssignment}
              locale={locale}
              dense={compact}
              templateColumns={templateColumns}
              readOnly={readOnly}
              duplicateMemberDayKeys={duplicateMemberDayKeys}
              highlightTeamMemberId={highlightTeamMemberId}
            />
            <MobileRosterMatrix
              matrix={matrix}
              workloadMatrix={matrix}
              workloadWarnings={validationWarnings}
              planningPeriodLabel={formatWorkloadPeriodLabel(matrix.planning_period)}
              slotsByDay={slotsByDay}
              assignmentMap={assignmentMap}
              planningCellMap={planningCellMap}
              intentMap={intentMap}
              onSave={saveAssignment}
              locale={locale}
              dense={compact}
              templateColumns={templateColumns}
              readOnly={readOnly}
              duplicateMemberDayKeys={duplicateMemberDayKeys}
              highlightTeamMemberId={highlightTeamMemberId}
            />
          </>
        ) : (
          <Card>
            <p className="text-sm text-slate-500">{t(locale, "noShiftTemplatesForRoster")}</p>
          </Card>
        )
      ) : (
        <Card>
          <p className="text-sm text-slate-500">{t(locale, "noData")}</p>
        </Card>
      )}
    </div>
  );
}

function DesktopRosterMatrix({
  matrix,
  workloadMatrix,
  workloadWarnings,
  planningPeriodLabel,
  slotsByDay,
  assignmentMap,
  planningCellMap,
  intentMap,
  onSave,
  locale,
  dense,
  templateColumns,
  readOnly,
  duplicateMemberDayKeys,
  highlightTeamMemberId,
}: {
  matrix: RosterMatrix;
  workloadMatrix: RosterWorkloadMatrixSlice;
  workloadWarnings: RosterWorkloadWarning[];
  planningPeriodLabel: string;
  slotsByDay: Map<string, RosterSlot[]>;
  assignmentMap: Map<number, RosterSlotAssignment>;
  planningCellMap: Map<string, PlanningCell>;
  intentMap: Map<string, ShiftIntentKind>;
  onSave: (rosterSlotId: number, memberId: number | "", manualOverride?: boolean) => Promise<boolean>;
  locale: Locale;
  dense: boolean;
  templateColumns: ShiftTemplateSummary[];
  readOnly: boolean;
  duplicateMemberDayKeys?: ReadonlySet<string>;
  highlightTeamMemberId?: number;
}) {
  if (dense) {
    return (
      <div className={`hidden ${dataTableScrollShellClassName} rounded-lg border border-slate-200 bg-white shadow-soft lg:block`}>
        <table className="min-w-max border-separate border-spacing-0 text-sm">
          <thead>
            <tr>
              <th className="sticky left-0 top-0 z-30 min-w-[10.5rem] border-b border-r border-slate-200 bg-white p-3 text-left font-semibold text-slate-700">
                {t(locale, "date")}
              </th>
              {templateColumns.map((template) => (
                <th key={template.id} className="sticky top-0 z-20 min-w-[11rem] border-b border-slate-200 bg-white p-2 text-left align-bottom">
                  <div className="grid gap-1">
                    <p className="text-xs font-semibold text-ink">
                      {template.name}
                    </p>
                    <div className="flex flex-wrap items-center gap-1">
                      <span className="rounded-md bg-ink px-2 py-0.5 font-mono text-[0.65rem] font-semibold text-white">{template.code}</span>
                      <span className="rounded-full bg-slate-50 px-2 py-0.5 text-[0.65rem] font-semibold text-slate-700 ring-1 ring-slate-200">
                        {categoryLabel(locale, template.category)}
                      </span>
                    </div>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.days.map((day) => {
              const daySlots = slotsByDay.get(day.date) ?? [];
              const dayClass = dayClassForDate(daySlots);
              return (
                <tr key={day.date}>
                  <td className="sticky left-0 z-10 border-r border-slate-200 bg-white p-3 align-top">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <div className="font-medium text-slate-800">{formatDate(locale, day.date)}</div>
                      {dayClass ? <DayClassPill dayClass={dayClass} locale={locale} /> : null}
                    </div>
                  </td>
                  {templateColumns.map((template) => {
                    const cellSlots = slotsForTemplateDay(slotsByDay, day.date, template.id);
                    return (
                      <td key={`${day.date}-${template.id}`} className="border-b border-slate-100 p-2 align-top">
                        {cellSlots.length ? (
                          <div className="grid gap-2">
                            {cellSlots.map((slot) => {
                              return (
                              <div key={slot.id} className="grid">
                                <RosterCell
                                  slot={slot}
                                  members={matrix.team_members}
                                  assignment={assignmentMap.get(slot.id)}
                                  planningCellMap={planningCellMap}
                                  intentMap={intentMap}
                                  onSave={onSave}
                                  locale={locale}
                                  readOnly={readOnly}
                                  duplicateMemberDayKeys={duplicateMemberDayKeys}
                                  workloadMatrix={workloadMatrix}
                                  workloadWarnings={workloadWarnings}
                                  planningPeriodLabel={planningPeriodLabel}
                                  dayStatusDefinitions={matrix.day_status_definitions ?? []}
                                  highlightTeamMemberId={highlightTeamMemberId}
                                />
                              </div>
                            );
                            })}
                          </div>
                        ) : (
                          <p className="px-1 py-6 text-center text-xs text-slate-400">{t(locale, "emptyValue")}</p>
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className={`hidden ${dataTableScrollShellClassName} rounded-lg border border-slate-200 bg-white shadow-soft lg:block`}>
      <table className="min-w-full border-separate border-spacing-0 text-sm">
        <thead>
          <tr>
            <th className="sticky left-0 top-0 z-20 border-b border-r border-slate-200 bg-white p-3 text-left font-semibold text-slate-700">
              {t(locale, "date")}
            </th>
            <th className="sticky top-0 z-10 min-w-[44rem] border-b border-slate-200 bg-white p-3 text-left font-semibold text-slate-700">
              {t(locale, "generatedSlots")}
            </th>
          </tr>
        </thead>
        <tbody>
          {matrix.days.map((day) => (
            <tr key={day.date}>
              <td className="sticky left-0 z-10 border-r border-slate-200 bg-white p-3 font-medium text-slate-700">
                {formatDate(locale, day.date)}
              </td>
              <td className="border-b border-slate-100 p-2 align-top">
                <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
                  {(slotsByDay.get(day.date) ?? []).map((slot) => (
                    <div key={slot.id} className="grid gap-2 rounded-lg border border-slate-200 bg-slate-50/60 p-2">
                      <SlotHeader slot={slot} locale={locale} />
                      <RosterCell
                        slot={slot}
                        members={matrix.team_members}
                        assignment={assignmentMap.get(slot.id)}
                        planningCellMap={planningCellMap}
                        intentMap={intentMap}
                        onSave={onSave}
                        locale={locale}
                        readOnly={readOnly}
                        duplicateMemberDayKeys={duplicateMemberDayKeys}
                        workloadMatrix={workloadMatrix}
                        workloadWarnings={workloadWarnings}
                        planningPeriodLabel={planningPeriodLabel}
                        dayStatusDefinitions={matrix.day_status_definitions ?? []}
                        highlightTeamMemberId={highlightTeamMemberId}
                      />
                    </div>
                  ))}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MobileRosterMatrix({
  matrix,
  workloadMatrix,
  workloadWarnings,
  planningPeriodLabel,
  slotsByDay,
  assignmentMap,
  planningCellMap,
  intentMap,
  onSave,
  locale,
  dense,
  templateColumns,
  readOnly,
  duplicateMemberDayKeys,
  highlightTeamMemberId,
}: {
  matrix: RosterMatrix;
  workloadMatrix: RosterWorkloadMatrixSlice;
  workloadWarnings: RosterWorkloadWarning[];
  planningPeriodLabel: string;
  slotsByDay: Map<string, RosterSlot[]>;
  assignmentMap: Map<number, RosterSlotAssignment>;
  planningCellMap: Map<string, PlanningCell>;
  intentMap: Map<string, ShiftIntentKind>;
  onSave: (rosterSlotId: number, memberId: number | "", manualOverride?: boolean) => Promise<boolean>;
  locale: Locale;
  dense: boolean;
  templateColumns: ShiftTemplateSummary[];
  readOnly: boolean;
  duplicateMemberDayKeys?: ReadonlySet<string>;
  highlightTeamMemberId?: number;
}) {
  if (dense) {
    return (
      <div className="grid gap-3 lg:hidden">
        {matrix.days.map((day) => {
          const daySlots = slotsByDay.get(day.date) ?? [];
          const dayClass = dayClassForDate(daySlots);
          return (
            <Card key={day.date}>
              <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
                <h2 className="text-base font-semibold text-ink">{formatDate(locale, day.date)}</h2>
                {dayClass ? <DayClassPill dayClass={dayClass} locale={locale} /> : null}
              </div>
              <div className={`-mx-1 ${dataTableScrollShellClassName}`}>
                <table className="min-w-max w-full border-separate border-spacing-0 text-sm">
                  <thead>
                    <tr>
                      {templateColumns.map((template) => (
                        <th key={template.id} className="sticky top-0 z-10 min-w-[10.5rem] border-b border-slate-200 bg-white px-2 pb-2 text-left align-bottom shadow-[0_1px_0_0_rgb(226_232_240)]">
                          <div className="grid gap-1">
                            <p className="text-xs font-semibold text-ink">
                              {template.name}
                            </p>
                            <div className="flex flex-wrap items-center gap-1">
                              <span className="rounded-md bg-ink px-2 py-0.5 font-mono text-[0.65rem] font-semibold text-white">{template.code}</span>
                              <span className="rounded-full bg-slate-50 px-2 py-0.5 text-[0.65rem] font-semibold text-slate-700 ring-1 ring-slate-200">
                                {categoryLabel(locale, template.category)}
                              </span>
                            </div>
                          </div>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      {templateColumns.map((template) => {
                        const cellSlots = slotsForTemplateDay(slotsByDay, day.date, template.id);
                        return (
                          <td key={`${day.date}-${template.id}`} className="border-b border-slate-100 px-2 py-2 align-top">
                            {cellSlots.length ? (
                              <div className="grid gap-2">
                                {cellSlots.map((slot) => {
                                  return (
                                  <div key={slot.id} className="grid">
                                    <RosterCell
                                      slot={slot}
                                      members={matrix.team_members}
                                      assignment={assignmentMap.get(slot.id)}
                                      planningCellMap={planningCellMap}
                                      intentMap={intentMap}
                                      onSave={onSave}
                                      locale={locale}
                                      readOnly={readOnly}
                                      duplicateMemberDayKeys={duplicateMemberDayKeys}
                                      workloadMatrix={workloadMatrix}
                                      workloadWarnings={workloadWarnings}
                                      planningPeriodLabel={planningPeriodLabel}
                                      dayStatusDefinitions={matrix.day_status_definitions ?? []}
                                      highlightTeamMemberId={highlightTeamMemberId}
                                    />
                                  </div>
                                );
                                })}
                              </div>
                            ) : (
                              <p className="py-6 text-center text-xs text-slate-400">{t(locale, "emptyValue")}</p>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  </tbody>
                </table>
              </div>
            </Card>
          );
        })}
      </div>
    );
  }

  return (
    <div className="grid gap-4 lg:hidden">
      {matrix.days.map((day) => (
        <Card key={day.date}>
          <h2 className="mb-3 text-base font-semibold text-ink">{formatDate(locale, day.date)}</h2>
          <div className="grid gap-3">
            {(slotsByDay.get(day.date) ?? []).map((slot) => (
                <div key={slot.id} className="grid gap-2 rounded-lg border border-slate-200 p-3">
                  <SlotHeader slot={slot} locale={locale} />
                    <RosterCell
                      slot={slot}
                      members={matrix.team_members}
                      assignment={assignmentMap.get(slot.id)}
                      planningCellMap={planningCellMap}
                      intentMap={intentMap}
                      onSave={onSave}
                      locale={locale}
                      readOnly={readOnly}
                      duplicateMemberDayKeys={duplicateMemberDayKeys}
                      workloadMatrix={workloadMatrix}
                      workloadWarnings={workloadWarnings}
                      planningPeriodLabel={planningPeriodLabel}
                      dayStatusDefinitions={matrix.day_status_definitions ?? []}
                      highlightTeamMemberId={highlightTeamMemberId}
                    />
                </div>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}

function SlotHeader({ slot, locale }: { slot: RosterSlot; locale: Locale }) {
  const label = slot.template_name;
  return (
    <div className="flex flex-wrap items-start justify-between gap-2">
      <div>
        <p className="text-sm font-semibold text-slate-800">{label || slot.label || t(locale, "generatedSlots")}</p>
        <p className="text-xs text-slate-500">{formatTimeRange(slot)}{slot.variant_label ? ` · ${slot.variant_label}` : ""}</p>
      </div>
      {slot.day_class ? (
        <DayClassPill dayClass={slot.day_class} locale={locale} />
      ) : null}
    </div>
  );
}

function RosterCell({
  slot,
  members,
  assignment,
  planningCellMap,
  intentMap,
  onSave,
  locale,
  readOnly = false,
  duplicateMemberDayKeys,
  workloadMatrix,
  workloadWarnings,
  planningPeriodLabel,
  dayStatusDefinitions,
  highlightTeamMemberId,
}: {
  slot: RosterSlot;
  members: RosterMatrixTeamMember[];
  assignment?: RosterSlotAssignment;
  planningCellMap: Map<string, PlanningCell>;
  intentMap: Map<string, ShiftIntentKind>;
  onSave: (rosterSlotId: number, memberId: number | "", manualOverride?: boolean) => Promise<boolean>;
  locale: Locale;
  readOnly?: boolean;
  duplicateMemberDayKeys?: ReadonlySet<string>;
  workloadMatrix: RosterWorkloadMatrixSlice;
  workloadWarnings: RosterWorkloadWarning[];
  planningPeriodLabel: string;
  dayStatusDefinitions: PlanningDayStatusDefinition[];
  highlightTeamMemberId?: number;
}) {
  const [memberId, setMemberId] = useState<number | "">(assignment?.team_member_id ?? "");
  const [open, setOpen] = useState(false);
  const [workloadModalMemberId, setWorkloadModalMemberId] = useState<number | null>(null);
  const [pickerFilter, setPickerFilter] = useState("");
  const [manualOverride, setManualOverride] = useState(() => assignment?.manual_override === true);
  const [menuBox, setMenuBox] = useState<{ top: number; left: number; width: number } | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const workloadDialogTitleId = useId();
  const templateId = slot.shift_template_id;

  const workloadModalRow =
    workloadModalMemberId != null
      ? workloadRowForMember(workloadMatrix, workloadWarnings, workloadModalMemberId)
      : null;

  const filteredMembers = useMemo(
    () => members.filter((m) => teamMemberMatchesQuery(m, pickerFilter)),
    [members, pickerFilter]
  );

  const templateAssignmentCountByMemberId = useMemo(() => {
    const slotsById = new Map(workloadMatrix.slots.map((s) => [s.id, s]));
    const map = new Map<number, number>();
    const targetTemplateId = slot.shift_template_id;
    for (const row of workloadMatrix.assignments) {
      const assignedSlot = slotsById.get(row.roster_slot_id);
      if (!assignedSlot) {
        continue;
      }
      const sameTemplate =
        targetTemplateId != null
          ? assignedSlot.shift_template_id === targetTemplateId
          : assignedSlot.shift_template_id == null && assignedSlot.category === slot.category;
      if (!sameTemplate) {
        continue;
      }
      map.set(row.team_member_id, (map.get(row.team_member_id) ?? 0) + 1);
    }
    return map;
  }, [workloadMatrix.assignments, workloadMatrix.slots, slot.shift_template_id, slot.category]);

  const planningCell = memberId ? planningCellMap.get(`${slot.slot_date}:${memberId}`) : undefined;
  const hasDayComment = Boolean(planningCell?.comment?.trim());
  const status = planningCell?.status;
  const statusRow = status ? planningDayStatusByCode(dayStatusDefinitions).get(status) : undefined;
  const meta = statusRow
    ? { color: planningDayStatusBadgeClass(statusRow.color_preset), label: planningDayStatusLabel(statusRow, locale) }
    : undefined;
  const hasUnavailableDay = status ? rosterBlocksForPlanningDayStatusCode(status, dayStatusDefinitions) : false;
  const selectedMember = members.find((member) => member.id === memberId);
  const selectedNoGo =
    memberId && templateId
      ? intentMap.get(`${slot.slot_date}:${memberId}:${templateId}`) === "no_go"
      : false;
  const highlightNoGo = selectedNoGo && !manualOverride;
  const assigneeId = assignment?.team_member_id ?? null;
  const duplicateSameDay =
    assigneeId != null && Boolean(duplicateMemberDayKeys?.has(`${assigneeId}:${slot.slot_date}`));
  const warnUnavailable = hasUnavailableDay || highlightNoGo;
  const isMyAssignment = highlightTeamMemberId != null && assigneeId === highlightTeamMemberId;
  const highlightMine = isMyAssignment && !warnUnavailable && !duplicateSameDay;

  const syncMenuPosition = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger) {
      return;
    }
    const viewportPadding = 8;
    const gap = 4;
    const estimatedMenuHeight = Math.min(280, Math.max(140, menuRef.current?.offsetHeight ?? 220));
    const rect = trigger.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom - gap - viewportPadding;
    const spaceAbove = rect.top - gap - viewportPadding;
    const shouldOpenUp = spaceBelow < estimatedMenuHeight && spaceAbove > spaceBelow;
    const idealTop = shouldOpenUp ? rect.top - estimatedMenuHeight - gap : rect.bottom + gap;
    const top = Math.max(
      viewportPadding,
      Math.min(idealTop, window.innerHeight - estimatedMenuHeight - viewportPadding)
    );
    setMenuBox({
      top,
      left: rect.left,
      width: Math.max(rect.width, 200)
    });
  }, []);

  useEffect(() => {
    setMemberId(assignment?.team_member_id ?? "");
    setManualOverride(assignment?.manual_override === true);
  }, [assignment?.team_member_id, assignment?.manual_override]);

  useEffect(() => {
    if (open) {
      setPickerFilter("");
    }
  }, [open]);

  useLayoutEffect(() => {
    if (!open) {
      setMenuBox(null);
      return;
    }
    syncMenuPosition();
    const frame = window.requestAnimationFrame(() => {
      syncMenuPosition();
    });
    function onReposition() {
      syncMenuPosition();
    }
    window.addEventListener("scroll", onReposition, true);
    window.addEventListener("resize", onReposition);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onReposition, true);
      window.removeEventListener("resize", onReposition);
    };
  }, [open, syncMenuPosition]);

  useEffect(() => {
    if (workloadModalMemberId == null) {
      return;
    }
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setWorkloadModalMemberId(null);
      }
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [workloadModalMemberId]);

  useEffect(() => {
    if (!open) {
      return;
    }
    function handlePointer(event: MouseEvent) {
      const target = event.target as Node;
      if (rootRef.current?.contains(target) || menuRef.current?.contains(target)) {
        return;
      }
      setOpen(false);
    }
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handlePointer);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handlePointer);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  const menuPortal =
    open && menuBox && typeof document !== "undefined"
      ? createPortal(
          <div
            ref={menuRef}
            className="fixed z-[500] flex max-h-[min(50vh,280px)] flex-col overflow-hidden rounded-lg border border-slate-200 bg-white py-0 shadow-xl ring-1 ring-slate-900/10"
            style={{ top: menuBox.top, left: menuBox.left, width: menuBox.width }}
            role="presentation"
          >
            <div className="shrink-0 border-b border-slate-200 p-2">
              <input
                type="search"
                className={`${inputClass} h-9 text-xs`}
                placeholder={t(locale, "searchTeamMembersPlaceholder")}
                value={pickerFilter}
                onChange={(event) => setPickerFilter(event.target.value)}
                onKeyDown={(event) => event.stopPropagation()}
                autoComplete="off"
                autoFocus
                aria-label={t(locale, "searchTeamMembersPlaceholder")}
              />
            </div>
            <ul className="min-h-0 flex-1 list-none overflow-y-auto py-1" role="listbox">
              <li role="none">
                <button
                  type="button"
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-slate-600 hover:bg-slate-50"
                  onClick={async () => {
                    const previous = memberId;
                    setMemberId("");
                    setOpen(false);
                    const ok = await onSave(slot.id, "");
                    if (!ok) {
                      setMemberId(previous);
                    }
                  }}
                >
                  {t(locale, "emptyValue")}
                </button>
              </li>
              {filteredMembers.length === 0 && pickerFilter.trim() ? (
                <li className="px-3 py-2 text-xs text-slate-500" role="presentation">
                  {t(locale, "noTeamMemberMatches")}
                </li>
              ) : null}
              {filteredMembers.map((member) => {
                const cell = planningCellMap.get(`${slot.slot_date}:${member.id}`);
                const st = cell?.status;
                const stRow = st ? planningDayStatusByCode(dayStatusDefinitions).get(st) : undefined;
                const dotClass = stRow ? planningDayStatusSolidClass(stRow.color_preset) : "bg-slate-300";
                const intentKey = templateId ? `${slot.slot_date}:${member.id}:${templateId}` : "";
                const intentKind = intentKey ? intentMap.get(intentKey) : undefined;
                const assignedThisTemplate = templateAssignmentCountByMemberId.get(member.id) ?? 0;
                return (
                  <li key={member.id} className="flex items-stretch" role="none">
                    <button
                      type="button"
                      className="flex min-w-0 flex-1 items-center gap-2 px-3 py-2 text-left text-xs hover:bg-slate-50"
                      onClick={async () => {
                        const previous = memberId;
                        setMemberId(member.id);
                        setOpen(false);
                        const ok = await onSave(slot.id, member.id, manualOverride);
                        if (!ok) {
                          setMemberId(previous);
                        }
                      }}
                    >
                      <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${dotClass}`} aria-hidden />
                      <span className="min-w-0 flex-1 truncate font-medium text-slate-800">{teamMemberLabel(member)}</span>
                      <span
                        className="shrink-0 rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[0.65rem] font-semibold tabular-nums text-slate-700 ring-1 ring-slate-200/80"
                        title={t(locale, "rosterPickerMonthAssignmentsTitle", { count: String(assignedThisTemplate) })}
                      >
                        {assignedThisTemplate}
                      </span>
                      {intentKind === "wish" ? (
                        <span className="shrink-0 rounded-md bg-sky-100 px-1.5 py-0.5 text-[0.65rem] font-semibold text-sky-900">
                          {t(locale, "wishShort")}
                        </span>
                      ) : null}
                      {intentKind === "no_go" ? (
                        <span className="shrink-0 rounded-md bg-rose-100 px-1.5 py-0.5 text-[0.65rem] font-semibold text-rose-900">
                          {t(locale, "noGoShort")}
                        </span>
                      ) : null}
                    </button>
                    <button
                      type="button"
                      className="flex shrink-0 items-center justify-center border-l border-slate-100 px-2 text-slate-500 hover:bg-slate-50 hover:text-ink"
                      aria-label={t(locale, "rosterMemberWorkloadStatsAria")}
                      onClick={(event) => {
                        event.preventDefault();
                        event.stopPropagation();
                        setOpen(false);
                        setWorkloadModalMemberId(member.id);
                      }}
                    >
                      <BarChart3 className="h-3.5 w-3.5" strokeWidth={2} aria-hidden />
                    </button>
                  </li>
                );
              })}
            </ul>
            <div className="shrink-0 border-t border-slate-100 bg-slate-50/95 px-2 py-1.5">
              <label className="flex cursor-pointer items-center gap-2 text-[0.62rem] leading-tight text-slate-500">
                <input
                  type="checkbox"
                  className="h-3 w-3 shrink-0 rounded border-slate-300"
                  checked={manualOverride}
                  onChange={(event) => setManualOverride(event.target.checked)}
                />
                <span title={t(locale, "manualOverride")}>{t(locale, "manualOverrideAbbr")}</span>
              </label>
            </div>
          </div>,
          document.body
        )
      : null;

  const statsModalPortal =
    workloadModalMemberId != null && workloadModalRow && typeof document !== "undefined"
      ? createPortal(
          <div
            className="fixed inset-0 z-[600] flex items-end justify-center bg-slate-900/40 p-4 sm:items-center sm:p-6"
            role="presentation"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) {
                setWorkloadModalMemberId(null);
              }
            }}
          >
            <div
              className="max-h-[min(90dvh,32rem)] w-full max-w-md overflow-y-auto rounded-xl border border-slate-200 bg-white shadow-2xl ring-1 ring-slate-900/10"
              role="dialog"
              aria-modal="true"
              aria-labelledby={workloadDialogTitleId}
              onMouseDown={(event) => event.stopPropagation()}
            >
              <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-4 py-3 sm:px-5">
                <div className="min-w-0">
                  <h2 id={workloadDialogTitleId} className="text-base font-semibold text-ink">
                    {t(locale, "rosterMemberWorkloadModalTitle", { name: workloadModalRow.name })}
                  </h2>
                  <p className="mt-0.5 text-xs text-slate-600">
                    {t(locale, "rosterMemberWorkloadModalSubtitle", { period: planningPeriodLabel })}
                  </p>
                </div>
                <button
                  type="button"
                  className="shrink-0 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                  onClick={() => setWorkloadModalMemberId(null)}
                >
                  {t(locale, "close")}
                </button>
              </div>
              <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-2 px-4 py-4 text-sm sm:px-5">
                <dt className="text-slate-600">{t(locale, "employment")}</dt>
                <dd className="text-right font-medium tabular-nums text-ink">{workloadModalRow.employmentPercentage}%</dd>
                <dt className="text-slate-600">{t(locale, "totalShifts")}</dt>
                <dd className="text-right font-medium tabular-nums text-ink">{workloadModalRow.total}</dd>
                <dt className="text-slate-600">{t(locale, "onCallDutyCategory")}</dt>
                <dd className="text-right font-medium tabular-nums text-ink">{workloadModalRow.onCallDuty}</dd>
                <dt className="text-slate-600">{t(locale, "standbyDutyCategory")}</dt>
                <dd className="text-right font-medium tabular-nums text-ink">{workloadModalRow.standbyDuty}</dd>
                <dt className="text-slate-600">{t(locale, "lateDutyCategory")}</dt>
                <dd className="text-right font-medium tabular-nums text-ink">{workloadModalRow.lateDuty}</dd>
                <dt className="text-slate-600">{t(locale, "other")}</dt>
                <dd className="text-right font-medium tabular-nums text-ink">{workloadModalRow.other}</dd>
                <dt className="text-slate-600">{t(locale, "workloadWeekendHolidayShifts")}</dt>
                <dd className="text-right font-medium tabular-nums text-ink">{workloadModalRow.weekendHolidayShifts}</dd>
                <dt className="text-slate-600">{t(locale, "conflicts")}</dt>
                <dd
                  className={
                    workloadModalRow.conflicts ? "text-right font-semibold tabular-nums text-rose-700" : "text-right font-medium tabular-nums text-ink"
                  }
                >
                  {workloadModalRow.conflicts}
                </dd>
              </dl>
            </div>
          </div>,
          document.body
        )
      : null;

  return (
    <div
      ref={rootRef}
      className={`relative grid gap-1 rounded-lg p-0.5 ${
        warnUnavailable
          ? "bg-rose-50 ring-2 ring-rose-300"
          : duplicateSameDay
            ? "bg-amber-50/80 ring-2 ring-amber-400"
            : highlightMine
              ? "bg-emerald-50/40 ring-2 ring-emerald-500"
              : ""
      }`}
      title={highlightMine ? t(locale, "rosterMyAssignmentHighlight") : undefined}
      aria-label={highlightMine ? t(locale, "rosterMyAssignmentHighlight") : undefined}
    >
      <button
        ref={triggerRef}
        type="button"
        aria-expanded={open}
        aria-haspopup="listbox"
        disabled={readOnly}
        className={`relative flex min-h-[2.25rem] w-full items-center justify-between gap-1.5 rounded-lg border bg-white px-1.5 py-1.5 pr-6.5 text-left text-xs font-medium disabled:cursor-default disabled:opacity-90 ${
          warnUnavailable ? "border-rose-300 text-rose-950" : duplicateSameDay ? "border-amber-400 text-amber-950" : "border-slate-200"
        }`}
        onClick={() => {
          if (!readOnly) {
            setOpen((value) => !value);
          }
        }}
      >
        <span className="flex min-w-0 flex-1 items-center gap-1.5">
          {memberId && statusRow ? (
            <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${planningDayStatusSolidClass(statusRow.color_preset)}`} aria-hidden />
          ) : (
            <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-slate-300" aria-hidden />
          )}
          <span className="truncate">{selectedMember ? teamMemberLabel(selectedMember) : t(locale, "emptyValue")}</span>
        </span>
        {manualOverride ? (
          <span
            className="pointer-events-none absolute right-7 top-1/2 h-1.5 w-1.5 -translate-y-1/2 rounded-full bg-amber-500 ring-2 ring-white"
            title={t(locale, "manualOverride")}
            aria-hidden
          />
        ) : null}
        <ChevronDown className={`pointer-events-none absolute right-2 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500 transition ${open ? "rotate-180" : ""}`} aria-hidden />
      </button>
      {menuPortal}
      {statsModalPortal}
      {meta || duplicateSameDay || hasDayComment ? (
        <div className="flex flex-wrap items-center gap-1">
          {hasUnavailableDay ? <span className="text-xs font-semibold text-rose-700">{t(locale, "conflict")}</span> : null}
          {highlightNoGo ? <span className="text-xs font-semibold text-rose-700">{t(locale, "noGoShort")}</span> : null}
          {duplicateSameDay ? (
            <span className="text-xs font-semibold text-amber-900">{t(locale, "rosterDuplicateDayInline")}</span>
          ) : null}
          {hasDayComment ? <span className="text-xs font-semibold text-sky-800">{t(locale, "dayCommentMarker")}</span> : null}
          {meta ? (
            <span className={`inline-flex w-fit rounded-full px-2 py-1 text-xs font-semibold ring-1 ${meta.color}`}>
              {meta.label}
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
