"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Plus, Trash2 } from "lucide-react";
import { Field, inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";
import { ApiError, apiFetch } from "@/lib/api";
import { t, type Locale, type TranslationKey } from "@/lib/i18n";
import {
  activePlanningDayStatusDefinitions,
  labelForPlanningDayStatusCode,
  planningDayStatusLabel,
  planningDayStatusSelectClass,
  planningDayStatusSelectShellClass,
  type PlanningDayStatusDefinition
} from "@/lib/planningDayStatus";

type PatternWeekday = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";
type ConstraintSeverity = "info" | "warning" | "error";
type MemberPatternType = "avoid_time_window" | "allowed_calendar_week_parity" | "recurring_weekday_status";
type TimeWindowAnchorOption = "any_overlap_day" | "slot_start_day";

type AvoidTimeWindowBand = {
  weekdays: PatternWeekday[];
  window_start: string;
  window_end: string;
  match_mode: "overlap";
  anchor: TimeWindowAnchorOption;
};

type AvoidTimeWindowRule = {
  type: "avoid_time_window";
  match_mode: "overlap";
  windows: AvoidTimeWindowBand[];
};

type AllowedCalendarWeekParityRule = {
  type: "allowed_calendar_week_parity";
  parity: "even" | "odd";
  status: string;
};

type RecurringWeekdayStatusRule = {
  type: "recurring_weekday_status";
  weekdays: PatternWeekday[];
  status: string;
};

type MemberPlanningPatternRule = AvoidTimeWindowRule | AllowedCalendarWeekParityRule | RecurringWeekdayStatusRule;

type PlanningPatternRow = {
  serverId?: number;
  label: string;
  is_active: boolean;
  rule: MemberPlanningPatternRule;
  severity: ConstraintSeverity;
  display_order: number;
};

type PlanningPatternRead = PlanningPatternRow & {
  id: number;
  organization_id: number;
  team_member_id: number;
  created_at: string;
  updated_at: string;
};

const WEEKDAYS: PatternWeekday[] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

const WEEKDAY_LABEL_KEYS: Record<PatternWeekday, TranslationKey> = {
  mon: "weekdayMonShort",
  tue: "weekdayTueShort",
  wed: "weekdayWedShort",
  thu: "weekdayThuShort",
  fri: "weekdayFriShort",
  sat: "weekdaySatShort",
  sun: "weekdaySunShort"
};

function avoidBandExpansionKey(rowIndex: number, bandIndex: number): string {
  return `${rowIndex}-${bandIndex}`;
}

function summarizeAvoidBandWeekdays(locale: Locale, weekdays: PatternWeekday[]): string {
  return WEEKDAYS.filter((day) => weekdays.includes(day))
    .map((day) => t(locale, WEEKDAY_LABEL_KEYS[day]))
    .join(", ");
}

function summarizeAvoidBandAnchor(locale: Locale, anchor: TimeWindowAnchorOption): string {
  return anchor === "slot_start_day"
    ? t(locale, "memberPlanningPatternAnchorSummarySlotStart")
    : t(locale, "memberPlanningPatternAnchorSummaryAnyOverlap");
}

function patternCardKey(rowIndex: number): string {
  return String(rowIndex);
}

function patternTypeLabel(locale: Locale, rule: MemberPlanningPatternRule): string {
  if (rule.type === "avoid_time_window") {
    return t(locale, "memberPlanningPatternTypeAvoidTimeWindow");
  }
  if (rule.type === "recurring_weekday_status") {
    return t(locale, "memberPlanningPatternTypeRecurringWeekdayStatus");
  }
  return t(locale, "memberPlanningPatternTypeWeekParity");
}

function defaultDayStatusCode(definitions: PlanningDayStatusDefinition[]): string {
  const active = activePlanningDayStatusDefinitions(definitions);
  return active[0]?.code ?? "frei";
}

function summarizePatternCardDetails(
  locale: Locale,
  row: PlanningPatternRow,
  definitions: PlanningDayStatusDefinition[]
): string {
  const rule = row.rule;
  const activePart = row.is_active
    ? t(locale, "memberPlanningPatternCardSummaryActive")
    : t(locale, "memberPlanningPatternCardSummaryInactive");
  if (rule.type === "avoid_time_window") {
    return `${t(locale, "memberPlanningPatternCardSummaryAvoid", { count: String(rule.windows.length) })} · ${activePart}`;
  }
  if (rule.type === "recurring_weekday_status") {
    const days = summarizeAvoidBandWeekdays(locale, rule.weekdays);
    const status = labelForPlanningDayStatusCode(rule.status, definitions, locale);
    return `${days} · ${status} · ${activePart}`;
  }
  const parity = t(locale, rule.parity === "even" ? "memberPlanningPatternParityEven" : "memberPlanningPatternParityOdd");
  const status = labelForPlanningDayStatusCode(rule.status, definitions, locale);
  const sev = t(
    locale,
    row.severity === "error"
      ? "constraintSeverityError"
      : row.severity === "warning"
        ? "constraintSeverityWarning"
        : "constraintSeverityInfo"
  );
  return `${parity} · ${status} · ${sev} · ${activePart}`;
}

function defaultAvoidBand(weekdays: PatternWeekday[] = ["sat"]): AvoidTimeWindowBand {
  return {
    weekdays,
    window_start: "22:00",
    window_end: "06:00",
    match_mode: "overlap",
    anchor: "any_overlap_day"
  };
}

function normalizePlanningRuleFromApi(
  rule: unknown,
  definitions: PlanningDayStatusDefinition[]
): MemberPlanningPatternRule {
  const fallbackStatus = defaultDayStatusCode(definitions);
  const allowedCodes = new Set(definitions.map((row) => row.code));
  if (rule && typeof rule === "object" && "type" in rule && (rule as { type: string }).type === "avoid_time_window") {
    const r = rule as Record<string, unknown>;
    if (Array.isArray(r.windows) && r.windows.length > 0) {
      return rule as MemberPlanningPatternRule;
    }
    if (Array.isArray(r.weekdays)) {
      return {
        type: "avoid_time_window",
        match_mode: "overlap",
        windows: [
          {
            weekdays: r.weekdays as PatternWeekday[],
            window_start: String(r.window_start ?? "22:00"),
            window_end: String(r.window_end ?? "06:00"),
            match_mode: "overlap",
            anchor: (r.anchor as TimeWindowAnchorOption) || "any_overlap_day"
          }
        ]
      };
    }
  }
  if (rule && typeof rule === "object" && "type" in rule && (rule as { type: string }).type === "allowed_calendar_week_parity") {
    const r = rule as Record<string, unknown>;
    const parity = (r.parity === "odd" ? "odd" : "even") as "even" | "odd";
    const rawStatus = typeof r.status === "string" ? r.status : undefined;
    const status = rawStatus && allowedCodes.has(rawStatus) ? rawStatus : fallbackStatus;
    return { type: "allowed_calendar_week_parity", parity, status };
  }
  return rule as MemberPlanningPatternRule;
}

function defaultPatternRow(type: MemberPatternType, defaultStatus: string): PlanningPatternRow {
  if (type === "allowed_calendar_week_parity") {
    return {
      label: "",
      is_active: true,
      severity: "warning",
      display_order: 0,
      rule: { type: "allowed_calendar_week_parity", parity: "even", status: defaultStatus }
    };
  }
  if (type === "recurring_weekday_status") {
    return {
      label: "",
      is_active: true,
      severity: "info",
      display_order: 0,
      rule: { type: "recurring_weekday_status", weekdays: ["wed"], status: defaultStatus }
    };
  }
  return {
    label: "",
    is_active: true,
    severity: "info",
    display_order: 0,
    rule: {
      type: "avoid_time_window",
      match_mode: "overlap",
      windows: [defaultAvoidBand()]
    }
  };
}

function toEditableRows(
  rows: PlanningPatternRead[],
  definitions: PlanningDayStatusDefinition[]
): PlanningPatternRow[] {
  return rows.map((row, index) => ({
    serverId: row.id,
    label: row.label,
    is_active: row.is_active,
    severity: row.severity,
    display_order: row.display_order ?? index,
    rule: normalizePlanningRuleFromApi(row.rule, definitions)
  }));
}

function defaultLabelForRule(rule: MemberPlanningPatternRule): TranslationKey {
  if (rule.type === "avoid_time_window") {
    return "memberPlanningPatternTypeAvoidTimeWindow";
  }
  if (rule.type === "allowed_calendar_week_parity") {
    return "memberPlanningPatternTypeWeekParity";
  }
  return "memberPlanningPatternTypeRecurringWeekdayStatus";
}

function showsSeveritySelect(rule: MemberPlanningPatternRule): boolean {
  return rule.type === "allowed_calendar_week_parity";
}

function payloadSeverity(rule: MemberPlanningPatternRule, declared: ConstraintSeverity): ConstraintSeverity {
  return showsSeveritySelect(rule) ? declared : "info";
}

function buildPayload(rows: PlanningPatternRow[], locale: Locale) {
  return {
    patterns: rows.map((row, index) => ({
      label: t(locale, defaultLabelForRule(row.rule)),
      is_active: row.is_active,
      severity: payloadSeverity(row.rule, row.severity),
      display_order: index,
      rule: row.rule
    }))
  };
}

export function TeamMemberPlanningPatternsEditor({
  teamMemberId,
  readOnly = false,
  allowErrorSeverity = false
}: {
  teamMemberId: number;
  readOnly?: boolean;
  allowErrorSeverity?: boolean;
}) {
  const { locale } = useLocale();
  const [rows, setRows] = useState<PlanningPatternRow[]>([]);
  const [dayStatusDefinitions, setDayStatusDefinitions] = useState<PlanningDayStatusDefinition[]>([]);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const dayStatuses = activePlanningDayStatusDefinitions(dayStatusDefinitions);
  const defaultStatusCode = defaultDayStatusCode(dayStatusDefinitions);
  const [expandedAvoidBands, setExpandedAvoidBands] = useState<Set<string>>(() => new Set());
  const [collapsedPatternCards, setCollapsedPatternCards] = useState<Set<string>>(() => new Set());
  const rowsRef = useRef<PlanningPatternRow[]>([]);
  const persistTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  rowsRef.current = rows;

  const flushPersist = useCallback(async () => {
    if (readOnly) {
      return;
    }
    const current = rowsRef.current;
    try {
      const saved = await apiFetch<PlanningPatternRead[]>(`/api/v1/team-members/${teamMemberId}/planning-patterns`, {
        method: "PUT",
        body: JSON.stringify(buildPayload(current, locale))
      });
      const next = toEditableRows(saved, dayStatusDefinitions);
      rowsRef.current = next;
      setRows(next);
      setMessage("");
    } catch (e) {
      if (e instanceof ApiError && typeof e.detail === "string") {
        setMessage(e.detail);
      } else {
        setMessage(t(locale, "orgManagementInviteError"));
      }
    }
  }, [teamMemberId, locale, readOnly, dayStatusDefinitions]);

  const flushPersistRef = useRef(flushPersist);
  flushPersistRef.current = flushPersist;

  const schedulePersist = useCallback(() => {
    if (readOnly) {
      return;
    }
    if (persistTimerRef.current) {
      clearTimeout(persistTimerRef.current);
    }
    persistTimerRef.current = setTimeout(() => {
      persistTimerRef.current = null;
      void flushPersist();
    }, 400);
  }, [readOnly, flushPersist]);

  useEffect(() => {
    return () => {
      const hadPending = persistTimerRef.current !== null;
      if (persistTimerRef.current) {
        clearTimeout(persistTimerRef.current);
        persistTimerRef.current = null;
      }
      if (!readOnly && hadPending) {
        void flushPersistRef.current();
      }
    };
  }, [readOnly]);

  const loadPatterns = useCallback(async () => {
    setLoading(true);
    try {
      const next = await apiFetch<PlanningPatternRead[]>(`/api/v1/team-members/${teamMemberId}/planning-patterns`);
      const mapped = toEditableRows(next, dayStatusDefinitions);
      rowsRef.current = mapped;
      setRows(mapped);
    } finally {
      setLoading(false);
    }
  }, [teamMemberId, dayStatusDefinitions]);

  useEffect(() => {
    void apiFetch<PlanningDayStatusDefinition[]>("/api/v1/planning-day-status-definitions?active_only=true")
      .then(setDayStatusDefinitions)
      .catch(() => setDayStatusDefinitions([]));
  }, []);

  useEffect(() => {
    void loadPatterns();
  }, [loadPatterns]);

  function commitRows(next: PlanningPatternRow[]) {
    rowsRef.current = next;
    setRows(next);
    if (!readOnly) {
      schedulePersist();
    }
  }

  function updateRow(index: number, patch: Partial<PlanningPatternRow>) {
    commitRows(rowsRef.current.map((row, rowIndex) => (rowIndex === index ? { ...row, ...patch } : row)));
  }

  function updateRule(index: number, rule: MemberPlanningPatternRule) {
    commitRows(rowsRef.current.map((row, rowIndex) => (rowIndex === index ? { ...row, rule } : row)));
  }

  function toggleRecurringWeekday(index: number, weekday: PatternWeekday) {
    const row = rowsRef.current[index];
    if (!row || row.rule.type !== "recurring_weekday_status") {
      return;
    }
    const rule = row.rule;
    const next = rule.weekdays.includes(weekday)
      ? rule.weekdays.filter((item) => item !== weekday)
      : [...rule.weekdays, weekday];
    updateRule(index, { ...rule, weekdays: next.length ? next : [weekday] });
  }

  function toggleAvoidBandWeekday(rowIndex: number, bandIndex: number, weekday: PatternWeekday) {
    const row = rowsRef.current[rowIndex];
    if (!row || row.rule.type !== "avoid_time_window") {
      return;
    }
    const windows = [...row.rule.windows];
    const band = windows[bandIndex];
    if (!band) {
      return;
    }
    const next = band.weekdays.includes(weekday)
      ? band.weekdays.filter((item) => item !== weekday)
      : [...band.weekdays, weekday];
    windows[bandIndex] = { ...band, weekdays: next.length ? next : [weekday] };
    updateRule(rowIndex, { ...row.rule, windows });
  }

  function addAvoidBand(rowIndex: number) {
    const row = rowsRef.current[rowIndex];
    if (!row || row.rule.type !== "avoid_time_window") {
      return;
    }
    const newBandIndex = row.rule.windows.length;
    updateRule(rowIndex, {
      ...row.rule,
      windows: [...row.rule.windows, defaultAvoidBand(["mon"])]
    });
    setExpandedAvoidBands((prev) => new Set(prev).add(avoidBandExpansionKey(rowIndex, newBandIndex)));
  }

  function removeAvoidBand(rowIndex: number, bandIndex: number) {
    const row = rowsRef.current[rowIndex];
    if (!row || row.rule.type !== "avoid_time_window" || row.rule.windows.length <= 1) {
      return;
    }
    setExpandedAvoidBands((prev) => {
      const next = new Set<string>();
      for (const k of prev) {
        const hyphen = k.indexOf("-");
        const r = Number(k.slice(0, hyphen));
        const b = Number(k.slice(hyphen + 1));
        if (r !== rowIndex) {
          next.add(k);
        } else if (b < bandIndex) {
          next.add(k);
        } else if (b > bandIndex) {
          next.add(avoidBandExpansionKey(r, b - 1));
        }
      }
      return next;
    });
    updateRule(rowIndex, {
      ...row.rule,
      windows: row.rule.windows.filter((_, bi) => bi !== bandIndex)
    });
  }

  const severityOptions: ConstraintSeverity[] = allowErrorSeverity
    ? ["info", "warning", "error"]
    : ["info", "warning"];

  return (
    <section className="grid gap-4">
      <div>
        <h2 className="text-lg font-semibold text-ink">{t(locale, "memberPlanningPatternsTitle")}</h2>
        <p className="mt-1 text-sm text-slate-600">{t(locale, "memberPlanningPatternsHelp")}</p>
      </div>
      {loading ? <p className="text-sm text-slate-600">{t(locale, "planningSessionLoading")}</p> : null}
      <div className="grid gap-3">
        {rows.map((row, index) => {
          const rule = row.rule;
          const cardKey = patternCardKey(index);
          const patternCardCollapsed = collapsedPatternCards.has(cardKey);
          const patternCardPanelId = `pattern-card-body-${index}`;
          return (
            <div key={row.serverId ?? `tmp-${index}`} className="overflow-hidden rounded-lg border border-slate-200 bg-slate-50/60">
              <div className="flex flex-wrap items-center gap-2 p-3 sm:p-4">
                <button
                  type="button"
                  aria-expanded={!patternCardCollapsed}
                  aria-controls={patternCardPanelId}
                  aria-label={
                    patternCardCollapsed
                      ? t(locale, "memberPlanningPatternCardExpand")
                      : t(locale, "memberPlanningPatternCardCollapse")
                  }
                  className="flex min-w-0 flex-1 items-start gap-2 rounded-lg py-1 text-left outline-none ring-ink focus-visible:ring-2"
                  onClick={() =>
                    setCollapsedPatternCards((prev) => {
                      const next = new Set(prev);
                      if (next.has(cardKey)) {
                        next.delete(cardKey);
                      } else {
                        next.add(cardKey);
                      }
                      return next;
                    })
                  }
                >
                  <span className="mt-0.5 shrink-0 text-slate-500" aria-hidden="true">
                    {patternCardCollapsed ? <ChevronRight size={18} /> : <ChevronDown size={18} />}
                  </span>
                  <span className="min-w-0 flex-1 text-sm leading-snug text-slate-800">
                    <span className="font-semibold">{patternTypeLabel(locale, rule)}</span>
                    <span className="text-slate-600"> · {summarizePatternCardDetails(locale, row, dayStatusDefinitions)}</span>
                  </span>
                </button>
                {readOnly ? null : (
                  <button
                    type="button"
                    className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-rose-200 bg-rose-50 text-rose-700"
                    onClick={() => {
                      setExpandedAvoidBands((prev) => {
                        const next = new Set<string>();
                        for (const k of prev) {
                          const hyphen = k.indexOf("-");
                          const r = Number(k.slice(0, hyphen));
                          const b = Number(k.slice(hyphen + 1));
                          if (r < index) {
                            next.add(k);
                          } else if (r > index) {
                            next.add(avoidBandExpansionKey(r - 1, b));
                          }
                        }
                        return next;
                      });
                      setCollapsedPatternCards((prev) => {
                        const next = new Set<string>();
                        for (const k of prev) {
                          const r = Number(k);
                          if (r < index) {
                            next.add(k);
                          } else if (r > index) {
                            next.add(String(r - 1));
                          }
                        }
                        return next;
                      });
                      commitRows(rowsRef.current.filter((_, rowIndex) => rowIndex !== index));
                    }}
                    aria-label={t(locale, "memberPlanningPatternRemove")}
                  >
                    <Trash2 size={16} />
                  </button>
                )}
              </div>
              {patternCardCollapsed ? null : (
                <div id={patternCardPanelId} className="grid gap-3 border-t border-slate-200 px-3 pb-4 pt-3 sm:px-4">
                  <div className="flex flex-wrap items-end gap-3">
                    {showsSeveritySelect(rule) ? (
                      <Field label={t(locale, "severity")}>
                        <select
                          className={inputClass}
                          disabled={readOnly}
                          value={row.severity}
                          onChange={(event) => updateRow(index, { severity: event.target.value as ConstraintSeverity })}
                        >
                          {severityOptions.map((severity) => (
                            <option key={severity} value={severity}>
                              {t(
                                locale,
                                severity === "error"
                                  ? "constraintSeverityError"
                                  : severity === "warning"
                                    ? "constraintSeverityWarning"
                                    : "constraintSeverityInfo"
                              )}
                            </option>
                          ))}
                        </select>
                      </Field>
                    ) : null}
                    <label className="inline-flex items-center gap-2 text-sm font-medium text-slate-700">
                      <input
                        type="checkbox"
                        disabled={readOnly}
                        checked={row.is_active}
                        onChange={(event) => updateRow(index, { is_active: event.target.checked })}
                      />
                      {t(locale, "memberPlanningPatternActive")}
                    </label>
                  </div>
                  <Field label={t(locale, "memberPlanningPatternType")}>
                <select
                  className={inputClass}
                  disabled={readOnly}
                  value={rule.type}
                  onChange={(event) => {
                    const type = event.target.value as MemberPatternType;
                    setExpandedAvoidBands((prev) => {
                      const next = new Set<string>();
                      for (const k of prev) {
                        const hyphen = k.indexOf("-");
                        const r = Number(k.slice(0, hyphen));
                        if (r !== index) {
                          next.add(k);
                        }
                      }
                      return next;
                    });
                    commitRows(
                      rowsRef.current.map((r, rowIndex) =>
                        rowIndex === index ? { ...defaultPatternRow(type, defaultStatusCode), serverId: r.serverId } : r
                      )
                    );
                  }}
                >
                  <option value="avoid_time_window">{t(locale, "memberPlanningPatternTypeAvoidTimeWindow")}</option>
                  <option value="recurring_weekday_status">
                    {t(locale, "memberPlanningPatternTypeRecurringWeekdayStatus")}
                  </option>
                  <option value="allowed_calendar_week_parity">{t(locale, "memberPlanningPatternTypeWeekParity")}</option>
                </select>
              </Field>
              {rule.type === "avoid_time_window" ? (
                <div className="grid gap-3">
                  <p className="text-sm text-slate-600">{t(locale, "memberPlanningPatternAvoidTimeWindowsStackHelp")}</p>
                  {rule.windows.map((band, bandIndex) => {
                    const expandKey = avoidBandExpansionKey(index, bandIndex);
                    const bandExpanded = expandedAvoidBands.has(expandKey);
                    const panelId = `avoid-band-panel-${index}-${bandIndex}`;
                    return (
                      <div
                        key={`${index}-band-${bandIndex}`}
                        className="overflow-hidden rounded-lg border border-slate-200 bg-white/80"
                      >
                        <div className="flex flex-wrap items-center gap-2 p-2 sm:p-3">
                          <button
                            type="button"
                            aria-expanded={bandExpanded}
                            aria-controls={panelId}
                            aria-label={
                              bandExpanded
                                ? t(locale, "memberPlanningPatternTimeWindowCollapse")
                                : t(locale, "memberPlanningPatternTimeWindowExpand")
                            }
                            className="flex min-w-0 flex-1 items-start gap-2 rounded-lg py-1 text-left outline-none ring-ink focus-visible:ring-2"
                            onClick={() =>
                              setExpandedAvoidBands((prev) => {
                                const next = new Set(prev);
                                if (next.has(expandKey)) {
                                  next.delete(expandKey);
                                } else {
                                  next.add(expandKey);
                                }
                                return next;
                              })
                            }
                          >
                            <span className="mt-0.5 shrink-0 text-slate-500" aria-hidden="true">
                              {bandExpanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                            </span>
                            <span className="min-w-0 flex-1 text-sm leading-snug text-slate-800">
                              <span className="font-semibold">
                                {t(locale, "memberPlanningPatternTimeWindowBand", { n: String(bandIndex + 1) })}
                              </span>
                              <span className="text-slate-600">
                                {" "}
                                · {summarizeAvoidBandWeekdays(locale, band.weekdays)}
                                {" "}
                                · {band.window_start}–{band.window_end}
                                {" "}
                                · {summarizeAvoidBandAnchor(locale, band.anchor)}
                              </span>
                            </span>
                          </button>
                          {readOnly || rule.windows.length <= 1 ? null : (
                            <button
                              type="button"
                              className="inline-flex h-10 w-10 shrink-0 items-center justify-center self-center rounded-lg border border-rose-200 bg-rose-50 text-rose-700"
                              onClick={() => removeAvoidBand(index, bandIndex)}
                              aria-label={t(locale, "memberPlanningPatternRemoveTimeWindow")}
                            >
                              <Trash2 size={16} />
                            </button>
                          )}
                        </div>
                        {bandExpanded ? (
                          <div id={panelId} className="grid gap-3 border-t border-slate-200 p-3 pt-3">
                            <div>
                              <p className="mb-2 text-sm font-medium text-slate-700">{t(locale, "memberPlanningPatternWeekdays")}</p>
                              <div className="flex flex-wrap gap-2">
                                {WEEKDAYS.map((weekday) => (
                                  <button
                                    key={weekday}
                                    type="button"
                                    disabled={readOnly}
                                    className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 ${
                                      band.weekdays.includes(weekday)
                                        ? "bg-ink text-white ring-ink"
                                        : "bg-white text-slate-700 ring-slate-200"
                                    }`}
                                    onClick={() => toggleAvoidBandWeekday(index, bandIndex, weekday)}
                                  >
                                    {t(locale, WEEKDAY_LABEL_KEYS[weekday])}
                                  </button>
                                ))}
                              </div>
                            </div>
                            <div className="grid gap-3 sm:grid-cols-2">
                              <Field label={t(locale, "memberPlanningPatternWindowStart")}>
                                <input
                                  className={inputClass}
                                  disabled={readOnly}
                                  type="time"
                                  value={band.window_start}
                                  onChange={(event) => {
                                    const r = rowsRef.current[index];
                                    if (!r || r.rule.type !== "avoid_time_window") {
                                      return;
                                    }
                                    const next = [...r.rule.windows];
                                    next[bandIndex] = { ...band, window_start: event.target.value };
                                    updateRule(index, { ...r.rule, windows: next });
                                  }}
                                />
                              </Field>
                              <Field label={t(locale, "memberPlanningPatternWindowEnd")}>
                                <input
                                  className={inputClass}
                                  disabled={readOnly}
                                  type="time"
                                  value={band.window_end}
                                  onChange={(event) => {
                                    const r = rowsRef.current[index];
                                    if (!r || r.rule.type !== "avoid_time_window") {
                                      return;
                                    }
                                    const next = [...r.rule.windows];
                                    next[bandIndex] = { ...band, window_end: event.target.value };
                                    updateRule(index, { ...r.rule, windows: next });
                                  }}
                                />
                              </Field>
                            </div>
                            <Field label={t(locale, "memberPlanningPatternAnchor")}>
                              <select
                                className={inputClass}
                                disabled={readOnly}
                                value={band.anchor}
                                onChange={(event) => {
                                  const r = rowsRef.current[index];
                                  if (!r || r.rule.type !== "avoid_time_window") {
                                    return;
                                  }
                                  const next = [...r.rule.windows];
                                  next[bandIndex] = { ...band, anchor: event.target.value as TimeWindowAnchorOption };
                                  updateRule(index, { ...r.rule, windows: next });
                                }}
                              >
                                <option value="any_overlap_day">{t(locale, "memberPlanningPatternAnchorAnyOverlap")}</option>
                                <option value="slot_start_day">{t(locale, "memberPlanningPatternAnchorSlotStart")}</option>
                              </select>
                            </Field>
                          </div>
                        ) : null}
                      </div>
                    );
                  })}
                  {readOnly ? null : (
                    <button
                      type="button"
                      className="inline-flex h-9 w-fit items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700"
                      onClick={() => addAvoidBand(index)}
                    >
                      <Plus size={14} />
                      {t(locale, "memberPlanningPatternAddTimeWindow")}
                    </button>
                  )}
                </div>
              ) : null}
              {rule.type === "recurring_weekday_status" ? (
                <div className="grid gap-3">
                  <p className="text-sm text-slate-600">{t(locale, "memberPlanningPatternRecurringWeekdayHelp")}</p>
                  <div>
                    <p className="mb-2 text-sm font-medium text-slate-700">{t(locale, "memberPlanningPatternWeekdays")}</p>
                    <div className="flex flex-wrap gap-2">
                      {WEEKDAYS.map((weekday) => (
                        <button
                          key={weekday}
                          type="button"
                          disabled={readOnly}
                          className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 ${
                            rule.weekdays.includes(weekday)
                              ? "bg-ink text-white ring-ink"
                              : "bg-white text-slate-700 ring-slate-200"
                          }`}
                          onClick={() => toggleRecurringWeekday(index, weekday)}
                        >
                          {t(locale, WEEKDAY_LABEL_KEYS[weekday])}
                        </button>
                      ))}
                    </div>
                  </div>
                  <Field label={t(locale, "memberPlanningPatternMatrixStatus")}>
                    <select
                      className={`${planningDayStatusSelectShellClass} w-full ${planningDayStatusSelectClass(rule.status, dayStatusDefinitions)}`}
                      disabled={readOnly}
                      value={rule.status}
                      onChange={(event) =>
                        updateRule(index, {
                          type: "recurring_weekday_status",
                          weekdays: rule.weekdays,
                          status: event.target.value
                        })
                      }
                    >
                      {dayStatuses.map((status) => (
                        <option key={status.code} value={status.code}>
                          {planningDayStatusLabel(status, locale)}
                        </option>
                      ))}
                    </select>
                  </Field>
                </div>
              ) : null}
              {rule.type === "allowed_calendar_week_parity" ? (
                <div className="grid gap-3">
                  <p className="text-sm text-slate-600">{t(locale, "memberPlanningPatternWeekParityMatrixHelp")}</p>
                  <Field label={t(locale, "memberPlanningPatternWeekParity")}>
                    <select
                      className={inputClass}
                      disabled={readOnly}
                      value={rule.parity}
                      onChange={(event) =>
                        updateRule(index, {
                          type: "allowed_calendar_week_parity",
                          parity: event.target.value as "even" | "odd",
                          status: rule.status
                        })
                      }
                    >
                      <option value="even">{t(locale, "memberPlanningPatternParityEven")}</option>
                      <option value="odd">{t(locale, "memberPlanningPatternParityOdd")}</option>
                    </select>
                  </Field>
                  <Field label={t(locale, "memberPlanningPatternMatrixStatus")}>
                    <select
                      className={`${planningDayStatusSelectShellClass} w-full ${planningDayStatusSelectClass(rule.status, dayStatusDefinitions)}`}
                      disabled={readOnly}
                      value={rule.status}
                      onChange={(event) =>
                        updateRule(index, {
                          type: "allowed_calendar_week_parity",
                          parity: rule.parity,
                          status: event.target.value
                        })
                      }
                    >
                      {dayStatuses.map((status) => (
                        <option key={status.code} value={status.code}>
                          {planningDayStatusLabel(status, locale)}
                        </option>
                      ))}
                    </select>
                  </Field>
                </div>
              ) : null}
                </div>
              )}
            </div>
          );
        })}
      </div>
      {readOnly ? null : (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700"
            onClick={() => commitRows([...rowsRef.current, defaultPatternRow("avoid_time_window", defaultStatusCode)])}
          >
            <Plus size={16} />
            {t(locale, "memberPlanningPatternAdd")}
          </button>
        </div>
      )}
      {message ? <p className="text-sm text-red-600">{message}</p> : null}
    </section>
  );
}
