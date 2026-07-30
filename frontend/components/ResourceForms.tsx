"use client";

import { FormEvent, ReactNode, useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { AlertTriangle, Info, MoreVertical, Plus, RefreshCw, Save, Trash2, X } from "lucide-react";
import { ApiError, apiFetch } from "@/lib/api";
import {
  defaultPropertyRequirementExpr,
  TeamMemberPropertyRequirementConstraintEditor,
  type PropertyDefinitionBrief,
  type PropertyRequirementExpr
} from "@/components/TeamMemberPropertyRequirementConstraintEditor";
import { t, type Locale, type TranslationKey } from "@/lib/i18n";
import { Card, Field, inputClass } from "@/components/Card";
import { TeamMemberPlanningPatternsEditor } from "@/components/TeamMemberPlanningPatternsEditor";
import { TeamMemberPropertyValuesEditor } from "@/components/TeamMemberPropertyValuesEditor";
import { useLocale } from "@/components/LocaleProvider";

type AnyRecord = Record<string, unknown>;

function shiftTemplateConflictMessage(locale: Locale, error: unknown): string | null {
  if (!(error instanceof ApiError) || error.status !== 409) {
    return null;
  }
  const detail = error.detail;
  if (
    detail &&
    typeof detail === "object" &&
    !Array.isArray(detail) &&
    (detail as { code?: string }).code === "SHIFT_TEMPLATE_CODE_TAKEN"
  ) {
    const code = String((detail as { value?: string }).value ?? "");
    return t(locale, "shiftTemplateCodeTaken", { code });
  }
  return null;
}

function apiFailureUserMessage(locale: Locale, error: unknown): string {
  const conflict = shiftTemplateConflictMessage(locale, error);
  if (conflict) {
    return conflict;
  }
  if (error instanceof ApiError) {
    return t(locale, "apiRequestFailed", { status: String(error.status) });
  }
  return t(locale, "apiUnavailable");
}
type ShiftTemplateCategory = "bereitschaftsdienst" | "rufdienst" | "spaetdienst" | "other";
type DayClass = "any" | "weekday" | "weekend" | "holiday";
type WeekdayCode = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";
type ConstraintSeverity = "info" | "warning" | "error";
type ShiftConstraintType =
  | "no_additional_same_day"
  | "min_rest_hours"
  | "no_cross_day_into_unavailable_day"
  | "unavailable_overlap_policy"
  | "max_assignments_per_month"
  | "requires_coupled_shift"
  | "team_member_property_requirement";
type UnavailableOverlapPolicyMode = "inherit" | "allow" | "warn" | "block";
type ShiftConstraintRecord = {
  constraintInstanceId: string;
  type: ShiftConstraintType;
  severity: ConstraintSeverity;
  min_rest_hours?: number | null;
  max_assignments_per_month?: number | null;
  paired_shift_variant_id?: number | null;
  partner_day_offset?: number;
  unavailable_overlap_mode?: UnavailableOverlapPolicyMode;
  property_requirement?: PropertyRequirementExpr;
};

type ShiftVariantRecord = {
  id: number;
  label: string;
  start_day_class: DayClass;
  end_day_class: DayClass | null;
  start_weekdays?: WeekdayCode[] | null;
  end_weekdays?: WeekdayCode[] | null;
  include_holidays?: boolean;
  starts_at: string;
  ends_at: string;
  end_day_offset: number;
  required_count: number;
  constraints?: ShiftConstraintRecord[];
  is_active: boolean;
};

type VariantApplicabilityState = {
  start_day_class: DayClass;
  end_day_class: DayClass | null;
  start_limit_weekdays: boolean;
  start_weekdays: WeekdayCode[];
  end_limit_weekdays: boolean;
  end_weekdays: WeekdayCode[];
  include_holidays: boolean;
};

type PendingVariantDraft = {
  uid: string;
  label: string;
  start_day_class: DayClass;
  end_day_class: "" | DayClass;
  start_limit_weekdays: boolean;
  start_weekdays: WeekdayCode[];
  end_limit_weekdays: boolean;
  end_weekdays: WeekdayCode[];
  include_holidays: boolean;
  starts_at: string;
  ends_at: string;
  required_count: number;
  constraints: ShiftConstraintRecord[];
  is_active: boolean;
};

type ShiftTemplateRecord = {
  id: number;
  code: string;
  name: string;
  category: ShiftTemplateCategory;
  display_order: number;
  is_active: boolean;
  constraints?: ShiftConstraintRecord[];
  variants?: ShiftVariantRecord[];
};

export type TeamMemberRecord = {
  id: number;
  first_name: string;
  last_name: string;
  nickname?: string | null;
  email: string;
  employment_percentage: number;
  notes: string | null;
  planning_preferences?: string | null;
  is_active: boolean;
  created_at: string;
  shift_group_ids?: number[];
  user_id?: number | null;
};

type ShiftGroupOption = { id: number; code: string; name: string };

const SHIFT_TEMPLATE_CATEGORIES: { value: ShiftTemplateCategory; label: TranslationKey }[] = [
  { value: "bereitschaftsdienst", label: "onCallDutyCategory" },
  { value: "rufdienst", label: "standbyDutyCategory" },
  { value: "spaetdienst", label: "lateDutyCategory" },
  { value: "other", label: "other" }
];

const FIELD_LABEL_MAP: Partial<Record<string, TranslationKey>> = {
  id: "id",
  first_name: "firstName",
  last_name: "lastName",
  nickname: "nickname",
  email: "email",
  employment_percentage: "employment",
  notes: "notes",
  planning_preferences: "planningPreferencesField",
  is_active: "isActive",
  created_at: "createdAt",
  code: "code",
  name: "name",
  starts_at: "start",
  ends_at: "end",
  category: "category",
  team_member_id: "teamMemberId",
  planning_period_id: "planningPeriodId",
  note: "note",
  manual_override: "manualOverride",
  user_id: "linkedUserId",
  message: "validationMessage",
  severity: "severity",
  date: "date",
  details: "details",
  status: "status"
};

const FIELD_PRIORITY = [
  "id",
  "name",
  "message",
  "code",
  "email",
  "severity",
  "request_type",
  "category",
  "employment_percentage",
  "is_active"
];

function sortedRowKeys(keys: string[]): string[] {
  const set = new Set(keys);
  const primary = FIELD_PRIORITY.filter((k) => set.has(k));
  const rest = keys.filter((k) => !FIELD_PRIORITY.includes(k)).sort((a, b) => a.localeCompare(b));
  return [...primary, ...rest];
}

function fieldLabel(locale: Locale, key: string): string {
  const mapped = FIELD_LABEL_MAP[key];
  return mapped ? t(locale, mapped) : key;
}

function formatScalar(locale: Locale, value: unknown): string {
  if (value === null || value === undefined) {
    return t(locale, "emptyValue");
  }
  if (value === "") {
    return t(locale, "emptyValue");
  }
  if (typeof value === "boolean") {
    return value ? t(locale, "yes") : t(locale, "no");
  }
  if (typeof value === "number") {
    return String(value);
  }
  if (typeof value === "string") {
    if (/^\d{4}-\d{2}-\d{2}T/.test(value)) {
      return new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-GB", {
        dateStyle: "medium",
        timeStyle: "short"
      }).format(new Date(value));
    }
    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
      return new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-GB", { dateStyle: "medium" }).format(new Date(`${value}T12:00:00`));
    }
    if (/^\d{2}:\d{2}(:\d{2})?$/.test(value)) {
      return value.slice(0, 5);
    }
    return value;
  }
  return JSON.stringify(value);
}

function formatFieldValue(locale: Locale, value: unknown): ReactNode {
  if (value !== null && typeof value === "object") {
    const text = JSON.stringify(value, null, 2);
    return (
      <pre className="mt-0.5 max-h-36 overflow-auto whitespace-pre-wrap break-words rounded-md bg-slate-100/90 p-2 font-mono text-xs text-slate-700 ring-1 ring-slate-200/80">
        {text}
      </pre>
    );
  }
  return <span className="text-sm font-medium text-ink">{formatScalar(locale, value)}</span>;
}

function cardTitle(row: AnyRecord, locale: Locale): string {
  if (typeof row.name === "string" && row.name.trim()) {
    return row.name;
  }
  if (typeof row.message === "string" && row.message.trim()) {
    return row.message;
  }
  if (typeof row.code === "string" && row.code.trim()) {
    return row.code;
  }
  return `${t(locale, "id")} ${formatScalar(locale, row.id)}`;
}

function RecordCard({ row }: { row: AnyRecord }) {
  const { locale } = useLocale();
  const keysAll = Object.keys(row);
  const detailBlock = row.details;
  const keys = sortedRowKeys(keysAll.filter((k) => k !== "details"));
  const hasDetails =
    detailBlock !== null &&
    detailBlock !== undefined &&
    typeof detailBlock === "object" &&
    !Array.isArray(detailBlock) &&
    Object.keys(detailBlock as object).length > 0;

  return (
    <article className="overflow-hidden rounded-xl border border-slate-200/90 bg-white shadow-soft ring-1 ring-slate-100/80">
      <div className="border-b border-mint/25 bg-gradient-to-r from-mint/10 via-white to-sky-50/40 px-4 py-3">
        <h2 className="truncate text-sm font-semibold text-ink">{cardTitle(row, locale)}</h2>
      </div>
      <div className="p-4">
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
          {keys.map((key) => (
            <div key={key} className="min-w-0">
              <dt className="text-[0.65rem] font-semibold uppercase tracking-wide text-slate-500">{fieldLabel(locale, key)}</dt>
              <dd className="mt-1 min-w-0">{formatFieldValue(locale, row[key])}</dd>
            </div>
          ))}
        </dl>
        {hasDetails ? (
          <div className="mt-4 border-t border-slate-100 pt-4">
            <p className="mb-2 text-[0.65rem] font-semibold uppercase tracking-wide text-slate-500">{t(locale, "details")}</p>
            {formatFieldValue(locale, detailBlock)}
          </div>
        ) : null}
      </div>
    </article>
  );
}

function DataList({ rows }: { rows: AnyRecord[] }) {
  const { locale } = useLocale();
  if (!rows.length) {
    return <p className="text-sm text-slate-500">{t(locale, "noData")}</p>;
  }
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {rows.map((row, index) => (
        <RecordCard key={String(row.id ?? index)} row={row} />
      ))}
    </div>
  );
}

function isShiftTemplateRecord(row: AnyRecord): row is ShiftTemplateRecord {
  return (
    typeof row.id === "number" &&
    typeof row.code === "string" &&
    typeof row.name === "string" &&
    typeof row.category === "string" &&
    Array.isArray(row.variants)
  );
}

export function isTeamMemberRecord(row: unknown): row is TeamMemberRecord {
  if (typeof row !== "object" || row === null) return false;
  const r = row as AnyRecord;
  return (
    typeof r.id === "number" &&
    typeof r.first_name === "string" &&
    typeof r.last_name === "string" &&
    typeof r.email === "string" &&
    typeof r.employment_percentage === "number"
  );
}

export function teamMemberLabel(record: { first_name: string; last_name: string }): string {
  return `${record.first_name} ${record.last_name}`.trim();
}

function categoryLabel(locale: Locale, category: string): string {
  const match = SHIFT_TEMPLATE_CATEGORIES.find((entry) => entry.value === category);
  return match ? t(locale, match.label) : category;
}

function dayClassLabel(locale: Locale, dayClass: DayClass | null): string {
  if (!dayClass) {
    return t(locale, "emptyValue");
  }
  const labels: Record<DayClass, TranslationKey> = {
    any: "anyDay",
    weekday: "weekday",
    weekend: "weekend",
    holiday: "holiday"
  };
  return t(locale, labels[dayClass]);
}

function dayClassPillClass(dayClass: DayClass | null): string {
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

function DayClassPill({ dayClass }: { dayClass: DayClass | null }) {
  const { locale } = useLocale();
  return (
    <span className={`inline-flex rounded-full px-2 py-1 text-xs font-semibold ring-1 ${dayClassPillClass(dayClass)}`}>
      {dayClassLabel(locale, dayClass)}
    </span>
  );
}

function formatVariantTime(variant: ShiftVariantRecord): string {
  const suffix = variant.end_day_offset > 0 ? ` +${variant.end_day_offset}` : "";
  return `${formatScalar("de", variant.starts_at)}-${formatScalar("de", variant.ends_at)}${suffix}`;
}

function inferEndDayOffset(startsAt: FormDataEntryValue | null, endsAt: FormDataEntryValue | null): number {
  const start = String(startsAt ?? "");
  const end = String(endsAt ?? "");
  return start && end && end <= start ? 1 : 0;
}

function dayClassOptions(locale: Locale) {
  return ([
    ["any", "anyDay"],
    ["weekday", "weekday"],
    ["weekend", "weekend"],
    ["holiday", "holiday"]
  ] as const).map(([value, label]) => (
    <option key={value} value={value}>{t(locale, label)}</option>
  ));
}

const WEEKDAY_CODES: WeekdayCode[] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

const WEEKDAY_LABEL_KEYS: Record<WeekdayCode, TranslationKey> = {
  mon: "weekdayMonShort",
  tue: "weekdayTueShort",
  wed: "weekdayWedShort",
  thu: "weekdayThuShort",
  fri: "weekdayFriShort",
  sat: "weekdaySatShort",
  sun: "weekdaySunShort"
};

const WEEKDAY_PRESETS: Array<{ labelKey: TranslationKey; weekdays: WeekdayCode[] }> = [
  { labelKey: "shiftVariantWeekdayPresetMonThu", weekdays: ["mon", "tue", "wed", "thu"] },
  { labelKey: "shiftVariantWeekdayPresetMonFri", weekdays: ["mon", "tue", "wed", "thu", "fri"] },
  { labelKey: "shiftVariantWeekdayPresetSatSun", weekdays: ["sat", "sun"] }
];

function summarizeWeekdayCodes(locale: Locale, weekdays: WeekdayCode[]): string {
  return WEEKDAY_CODES.filter((day) => weekdays.includes(day))
    .map((day) => t(locale, WEEKDAY_LABEL_KEYS[day]))
    .join(", ");
}

function applicabilityStateFromVariant(variant: ShiftVariantRecord): VariantApplicabilityState {
  return {
    start_day_class: variant.start_day_class,
    end_day_class: variant.end_day_class,
    start_limit_weekdays: Boolean(variant.start_weekdays?.length),
    start_weekdays: variant.start_weekdays ?? [],
    end_limit_weekdays: Boolean(variant.end_weekdays?.length),
    end_weekdays: variant.end_weekdays ?? [],
    include_holidays: variant.include_holidays ?? false
  };
}

function applicabilityPayload(state: VariantApplicabilityState) {
  const usesCustom = state.start_limit_weekdays || state.end_limit_weekdays;
  return {
    start_day_class: state.start_limit_weekdays ? "any" : state.start_day_class,
    end_day_class: state.end_limit_weekdays ? null : state.end_day_class,
    start_weekdays: state.start_limit_weekdays && state.start_weekdays.length ? state.start_weekdays : null,
    end_weekdays: state.end_limit_weekdays && state.end_weekdays.length ? state.end_weekdays : null,
    include_holidays: usesCustom && state.include_holidays
  };
}

function pendingApplicabilityPayload(variant: PendingVariantDraft) {
  return applicabilityPayload({
    start_day_class: variant.start_day_class,
    end_day_class: variant.end_day_class || null,
    start_limit_weekdays: variant.start_limit_weekdays,
    start_weekdays: variant.start_weekdays,
    end_limit_weekdays: variant.end_limit_weekdays,
    end_weekdays: variant.end_weekdays,
    include_holidays: variant.include_holidays
  });
}

function defaultWeekdaySelection(): WeekdayCode[] {
  return ["mon", "tue", "wed", "thu", "fri"];
}

function toggleWeekdaySelection(current: WeekdayCode[], weekday: WeekdayCode): WeekdayCode[] {
  const next = current.includes(weekday) ? current.filter((item) => item !== weekday) : [...current, weekday];
  return next.length ? next : [weekday];
}

function InlineInfoHint({
  hintKey,
  align = "left"
}: {
  hintKey: TranslationKey;
  align?: "left" | "right";
}) {
  const { locale } = useLocale();
  const hintId = useId();
  const [open, setOpen] = useState(false);

  return (
    <div className="relative inline-flex shrink-0">
      <button
        type="button"
        className={`inline-flex h-7 w-7 items-center justify-center rounded-lg border text-slate-600 outline-none ring-mint/20 transition focus:ring-4 ${
          open
            ? "border-slate-300 bg-slate-50 text-slate-800 ring-1 ring-slate-200"
            : "border-slate-200 bg-white hover:bg-slate-50"
        }`}
        aria-expanded={open}
        aria-controls={hintId}
        aria-label={t(locale, "shiftVariantInfoButton")}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          setOpen((value) => !value);
        }}
      >
        <Info size={14} strokeWidth={2} aria-hidden />
      </button>
      {open ? (
        <div
          id={hintId}
          role="region"
          aria-label={t(locale, hintKey)}
          className={`absolute top-full z-30 mt-1 min-w-[14rem] max-w-[min(20rem,calc(100vw-2rem))] rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-xs leading-relaxed text-slate-700 shadow-soft ring-1 ring-slate-100 ${
            align === "right" ? "right-0" : "left-0"
          }`}
        >
          {t(locale, hintKey)}
        </div>
      ) : null}
    </div>
  );
}

function VariantApplicabilitySideEditor({
  side,
  dayClass,
  onDayClassChange,
  limitWeekdays,
  onLimitWeekdaysChange,
  weekdays,
  onWeekdaysChange
}: {
  side: "start" | "end";
  dayClass: DayClass | null;
  onDayClassChange: (next: DayClass | null) => void;
  limitWeekdays: boolean;
  onLimitWeekdaysChange: (next: boolean) => void;
  weekdays: WeekdayCode[];
  onWeekdaysChange: (next: WeekdayCode[]) => void;
}) {
  const { locale } = useLocale();
  const sideLabel = side === "start" ? t(locale, "startDayClass") : t(locale, "endDayClass");
  const dayClassHintKey: TranslationKey =
    side === "start" ? "shiftVariantStartDayClassHint" : "shiftVariantEndDayClassHint";

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1">
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{sideLabel}</div>
        {!limitWeekdays ? <InlineInfoHint hintKey={dayClassHintKey} /> : null}
      </div>
      {!limitWeekdays ? (
        <select
          className={`${inputClass} w-full max-w-xs`}
          value={dayClass ?? ""}
          onChange={(event) => onDayClassChange(event.target.value ? (event.target.value as DayClass) : null)}
        >
          {side === "end" ? <option value="">{t(locale, "emptyValue")}</option> : null}
          {dayClassOptions(locale)}
        </select>
      ) : null}
      <label className="flex items-start gap-2 text-sm font-medium text-slate-700">
        <input
          className="mt-0.5"
          type="checkbox"
          checked={limitWeekdays}
          onChange={(event) => {
            const enabled = event.target.checked;
            onLimitWeekdaysChange(enabled);
            if (enabled && !weekdays.length) {
              onWeekdaysChange(defaultWeekdaySelection());
            }
          }}
        />
        <span className="flex flex-wrap items-center gap-1">
          {t(locale, "shiftVariantLimitToSpecificDays")}
          <InlineInfoHint hintKey="shiftVariantLimitWeekdaysHint" />
        </span>
      </label>
      {limitWeekdays ? (
        <div className="space-y-2">
          <div className="flex items-center gap-1">
            <span className="text-xs font-medium text-slate-600">{t(locale, "shiftVariantWeekdaySelectionLabel")}</span>
            <InlineInfoHint hintKey="shiftVariantWeekdaySelectionHint" />
          </div>
          <div className="flex flex-wrap gap-1.5">
            {WEEKDAY_CODES.map((weekday) => (
              <button
                key={weekday}
                type="button"
                className={`inline-flex h-9 min-w-9 items-center justify-center rounded-lg px-2 text-sm font-semibold ring-1 ${
                  weekdays.includes(weekday)
                    ? "bg-sky-600 text-white ring-sky-600"
                    : "bg-white text-slate-700 ring-slate-200"
                }`}
                onClick={() => onWeekdaysChange(toggleWeekdaySelection(weekdays, weekday))}
              >
                {t(locale, WEEKDAY_LABEL_KEYS[weekday])}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            {WEEKDAY_PRESETS.map((preset) => (
              <button
                key={preset.labelKey}
                type="button"
                className="inline-flex h-8 items-center rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-semibold text-slate-700"
                onClick={() => onWeekdaysChange([...preset.weekdays])}
              >
                {t(locale, preset.labelKey)}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function VariantApplicabilityEditor({
  value,
  onChange
}: {
  value: VariantApplicabilityState;
  onChange: (next: VariantApplicabilityState) => void;
}) {
  const { locale } = useLocale();
  const usesCustom = value.start_limit_weekdays || value.end_limit_weekdays;

  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex items-center gap-1 border-b border-slate-100 pb-2">
        <span className="text-sm font-semibold text-slate-700">{t(locale, "applicability")}</span>
        <InlineInfoHint hintKey="shiftVariantApplicabilityHint" />
      </div>
      <VariantApplicabilitySideEditor
        side="start"
        dayClass={value.start_day_class}
        onDayClassChange={(next) => onChange({ ...value, start_day_class: next ?? "any" })}
        limitWeekdays={value.start_limit_weekdays}
        onLimitWeekdaysChange={(next) => onChange({ ...value, start_limit_weekdays: next })}
        weekdays={value.start_weekdays}
        onWeekdaysChange={(next) => onChange({ ...value, start_weekdays: next })}
      />
      <details className="rounded-lg border border-slate-100 bg-slate-50 p-3">
        <summary className="flex cursor-pointer list-none items-center gap-1 text-sm font-semibold text-slate-700 [&::-webkit-details-marker]:hidden">
          <span>{t(locale, "shiftVariantEndApplicability")}</span>
          <InlineInfoHint hintKey="shiftVariantEndApplicabilityHint" align="right" />
        </summary>
        <div className="mt-3">
          <VariantApplicabilitySideEditor
            side="end"
            dayClass={value.end_day_class}
            onDayClassChange={(next) => onChange({ ...value, end_day_class: next })}
            limitWeekdays={value.end_limit_weekdays}
            onLimitWeekdaysChange={(next) => onChange({ ...value, end_limit_weekdays: next })}
            weekdays={value.end_weekdays}
            onWeekdaysChange={(next) => onChange({ ...value, end_weekdays: next })}
          />
        </div>
      </details>
      {usesCustom ? (
        <label className="flex items-start gap-2 text-sm font-medium text-slate-700">
          <input
            className="mt-1"
            type="checkbox"
            checked={value.include_holidays}
            onChange={(event) => onChange({ ...value, include_holidays: event.target.checked })}
          />
          <span className="flex flex-wrap items-center gap-1">
            {t(locale, "shiftVariantIncludeHolidays")}
            <InlineInfoHint hintKey="shiftVariantIncludeHolidaysHint" />
          </span>
        </label>
      ) : null}
    </div>
  );
}

function VariantApplicabilitySummary({ variant }: { variant: ShiftVariantRecord }) {
  const { locale } = useLocale();
  const startSummary = variant.start_weekdays?.length
    ? summarizeWeekdayCodes(locale, variant.start_weekdays)
    : null;
  const endSummary = variant.end_weekdays?.length ? summarizeWeekdayCodes(locale, variant.end_weekdays) : null;

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {startSummary ? (
        <span className="inline-flex rounded-full bg-sky-50 px-2 py-1 text-xs font-semibold text-sky-800 ring-1 ring-sky-200">
          {startSummary}
        </span>
      ) : (
        <DayClassPill dayClass={variant.start_day_class} />
      )}
      {endSummary || variant.end_day_class ? (
        <>
          <span className="text-xs text-slate-400">-&gt;</span>
          {endSummary ? (
            <span className="inline-flex rounded-full bg-violet-50 px-2 py-1 text-xs font-semibold text-violet-800 ring-1 ring-violet-200">
              {endSummary}
            </span>
          ) : (
            <DayClassPill dayClass={variant.end_day_class} />
          )}
        </>
      ) : null}
      {variant.include_holidays && (variant.start_weekdays?.length || variant.end_weekdays?.length) ? (
        <span className="inline-flex rounded-full bg-rose-50 px-2 py-1 text-xs font-semibold text-rose-800 ring-1 ring-rose-200">
          {t(locale, "holiday")}
        </span>
      ) : null}
    </div>
  );
}

function categoryOptions(locale: Locale) {
  return SHIFT_TEMPLATE_CATEGORIES.map((category) => (
    <option key={category.value} value={category.value}>{t(locale, category.label)}</option>
  ));
}

const SHIFT_CONSTRAINT_OPTIONS: { type: ShiftConstraintType; label: TranslationKey }[] = [
  { type: "no_additional_same_day", label: "constraintNoAdditionalSameDay" },
  { type: "min_rest_hours", label: "constraintMinRestHours" },
  { type: "unavailable_overlap_policy", label: "constraintUnavailableOverlapPolicy" },
  { type: "max_assignments_per_month", label: "constraintMaxAssignmentsPerMonth" },
  { type: "requires_coupled_shift", label: "constraintRequiresCoupledShift" },
  { type: "team_member_property_requirement", label: "constraintTeamMemberPropertyRequirement" }
];

function newConstraintInstanceId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `c_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function parsePropertyRequirement(raw: unknown): PropertyRequirementExpr | null {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const row = raw as AnyRecord;
  const kind = row.kind;
  if (kind === "atom") {
    const id = typeof row.property_definition_id === "number" ? row.property_definition_id : Number(row.property_definition_id);
    if (!Number.isFinite(id) || id < 1) {
      return null;
    }
    return {
      kind: "atom",
      property_definition_id: id,
      op: typeof row.op === "string" && row.op ? row.op : "eq",
      value: row.value
    };
  }
  if (kind === "all" || kind === "any") {
    const itemsRaw = row.items;
    if (!Array.isArray(itemsRaw)) {
      return null;
    }
    const items: PropertyRequirementExpr[] = [];
    for (const item of itemsRaw) {
      const parsed = parsePropertyRequirement(item);
      if (parsed) {
        items.push(parsed);
      }
    }
    if (!items.length) {
      return null;
    }
    return { kind, items };
  }
  return null;
}

function flattenVariantOptions(
  templates: ShiftTemplateRecord[],
  excludeVariantId: number | null | undefined
): { id: number; label: string }[] {
  const out: { id: number; label: string }[] = [];
  for (const tm of templates) {
    for (const v of tm.variants ?? []) {
      if (excludeVariantId != null && v.id === excludeVariantId) {
        continue;
      }
      out.push({ id: v.id, label: `${tm.code} · ${v.label}` });
    }
  }
  return out;
}

function constraintSeverityFromApiRow(row: AnyRecord): ConstraintSeverity {
  const s = row.severity;
  if (s === "info" || s === "warning" || s === "error") {
    return s;
  }
  if (row.enforcement === "block") {
    return "error";
  }
  return "warning";
}

function parseShiftConstraintList(raw: unknown): ShiftConstraintRecord[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  const out: ShiftConstraintRecord[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const row = item as AnyRecord;
    const type = row.type;
    if (
      type !== "no_additional_same_day" &&
      type !== "min_rest_hours" &&
      type !== "no_cross_day_into_unavailable_day" &&
      type !== "unavailable_overlap_policy" &&
      type !== "max_assignments_per_month" &&
      type !== "requires_coupled_shift" &&
      type !== "team_member_property_requirement"
    ) {
      continue;
    }
    const severity = constraintSeverityFromApiRow(row);
    const constraintInstanceId = newConstraintInstanceId();
    if (type === "unavailable_overlap_policy") {
      const modeRaw = row.unavailable_overlap_mode;
      const mode: UnavailableOverlapPolicyMode =
        modeRaw === "allow" || modeRaw === "warn" || modeRaw === "block" || modeRaw === "inherit"
          ? modeRaw
          : "block";
      out.push({ constraintInstanceId, type, severity, unavailable_overlap_mode: mode });
      continue;
    }
    if (type === "no_cross_day_into_unavailable_day") {
      const mode: UnavailableOverlapPolicyMode =
        severity === "error" ? "block" : severity === "warning" ? "warn" : "allow";
      out.push({
        constraintInstanceId,
        type: "unavailable_overlap_policy",
        severity,
        unavailable_overlap_mode: mode
      });
      continue;
    }
    if (type === "min_rest_hours") {
      const minRest = typeof row.min_rest_hours === "number" ? row.min_rest_hours : 11;
      out.push({ constraintInstanceId, type, severity, min_rest_hours: minRest });
      continue;
    }
    if (type === "max_assignments_per_month") {
      const maxM = typeof row.max_assignments_per_month === "number" ? row.max_assignments_per_month : 4;
      out.push({ constraintInstanceId, type, severity, max_assignments_per_month: maxM });
      continue;
    }
    if (type === "requires_coupled_shift") {
      const paired =
        typeof row.paired_shift_variant_id === "number" && row.paired_shift_variant_id >= 1
          ? row.paired_shift_variant_id
          : null;
      const offset =
        typeof row.partner_day_offset === "number" && row.partner_day_offset >= -7 && row.partner_day_offset <= 7
          ? row.partner_day_offset
          : 1;
      if (paired == null) {
        continue;
      }
      out.push({ constraintInstanceId, type, severity, paired_shift_variant_id: paired, partner_day_offset: offset });
      continue;
    }
    if (type === "team_member_property_requirement") {
      const pr = parsePropertyRequirement(row.property_requirement);
      if (!pr) {
        continue;
      }
      out.push({ constraintInstanceId, type, severity, property_requirement: pr });
      continue;
    }
    out.push({ constraintInstanceId, type, severity });
  }
  return out;
}

function shiftConstraintsToApi(constraints: ShiftConstraintRecord[]): unknown[] {
  return constraints.map((c) => {
    const base: Record<string, unknown> = { type: c.type, severity: c.severity };
    if (c.type === "min_rest_hours") {
      base.min_rest_hours = c.min_rest_hours ?? 11;
      return base;
    }
    if (c.type === "max_assignments_per_month") {
      base.max_assignments_per_month = c.max_assignments_per_month ?? 4;
      return base;
    }
    if (c.type === "requires_coupled_shift") {
      base.paired_shift_variant_id = c.paired_shift_variant_id;
      base.partner_day_offset = c.partner_day_offset ?? 1;
      return base;
    }
    if (c.type === "unavailable_overlap_policy") {
      base.unavailable_overlap_mode = c.unavailable_overlap_mode ?? "block";
      return base;
    }
    if (c.type === "team_member_property_requirement" && c.property_requirement) {
      base.property_requirement = c.property_requirement;
      return base;
    }
    return base;
  });
}

function setConstraintSeverity(
  constraints: ShiftConstraintRecord[],
  constraintInstanceId: string,
  severity: ConstraintSeverity
): ShiftConstraintRecord[] {
  return constraints.map((item) => (item.constraintInstanceId === constraintInstanceId ? { ...item, severity } : item));
}

function setConstraintMinRestHours(constraints: ShiftConstraintRecord[], constraintInstanceId: string, value: number): ShiftConstraintRecord[] {
  return constraints.map((item) =>
    item.constraintInstanceId === constraintInstanceId ? { ...item, min_rest_hours: value } : item
  );
}

function setConstraintMaxAssignments(constraints: ShiftConstraintRecord[], constraintInstanceId: string, value: number): ShiftConstraintRecord[] {
  return constraints.map((item) =>
    item.constraintInstanceId === constraintInstanceId ? { ...item, max_assignments_per_month: value } : item
  );
}

function setConstraintPairedVariant(
  constraints: ShiftConstraintRecord[],
  constraintInstanceId: string,
  paired_shift_variant_id: number
): ShiftConstraintRecord[] {
  return constraints.map((item) => (item.constraintInstanceId === constraintInstanceId ? { ...item, paired_shift_variant_id } : item));
}

function setConstraintPartnerDayOffset(
  constraints: ShiftConstraintRecord[],
  constraintInstanceId: string,
  partner_day_offset: number
): ShiftConstraintRecord[] {
  return constraints.map((item) => (item.constraintInstanceId === constraintInstanceId ? { ...item, partner_day_offset } : item));
}

function setConstraintPropertyRequirement(
  constraints: ShiftConstraintRecord[],
  constraintInstanceId: string,
  property_requirement: PropertyRequirementExpr
): ShiftConstraintRecord[] {
  return constraints.map((item) =>
    item.constraintInstanceId === constraintInstanceId ? { ...item, property_requirement } : item
  );
}

type AddConstraintContext = { allTemplates: ShiftTemplateRecord[]; excludeVariantId?: number | null; propertyDefinitions: PropertyDefinitionBrief[] };

function setConstraintUnavailableOverlapMode(
  constraints: ShiftConstraintRecord[],
  constraintInstanceId: string,
  unavailable_overlap_mode: UnavailableOverlapPolicyMode
): ShiftConstraintRecord[] {
  return constraints.map((item) =>
    item.constraintInstanceId === constraintInstanceId ? { ...item, unavailable_overlap_mode } : item
  );
}

function addConstraint(
  constraints: ShiftConstraintRecord[],
  type: ShiftConstraintType,
  ctx?: AddConstraintContext
): ShiftConstraintRecord[] {
  if (type !== "team_member_property_requirement" && constraints.some((item) => item.type === type)) {
    return constraints;
  }
  const constraintInstanceId = newConstraintInstanceId();
  if (type === "min_rest_hours") {
    return [...constraints, { constraintInstanceId, type, severity: "warning", min_rest_hours: 11 }];
  }
  if (type === "max_assignments_per_month") {
    return [...constraints, { constraintInstanceId, type, severity: "warning", max_assignments_per_month: 4 }];
  }
  if (type === "requires_coupled_shift") {
    const opts = flattenVariantOptions(ctx?.allTemplates ?? [], ctx?.excludeVariantId);
    const first = opts[0]?.id;
    if (first == null) {
      return constraints;
    }
    return [
      ...constraints,
      { constraintInstanceId, type, severity: "warning", paired_shift_variant_id: first, partner_day_offset: 1 }
    ];
  }
  if (type === "team_member_property_requirement") {
    const defs = ctx?.propertyDefinitions ?? [];
    return [
      ...constraints,
      {
        constraintInstanceId,
        type,
        severity: "warning",
        property_requirement: defaultPropertyRequirementExpr(defs)
      }
    ];
  }
  if (type === "unavailable_overlap_policy") {
    return [...constraints, { constraintInstanceId, type, severity: "warning", unavailable_overlap_mode: "warn" }];
  }
  return [...constraints, { constraintInstanceId, type, severity: "warning" }];
}

function removeConstraint(constraints: ShiftConstraintRecord[], constraintInstanceId: string): ShiftConstraintRecord[] {
  return constraints.filter((item) => item.constraintInstanceId !== constraintInstanceId);
}

const CONSTRAINT_SEVERITY_ORDER: ConstraintSeverity[] = ["info", "warning", "error"];

function constraintSeverityButtonClass(severity: ConstraintSeverity, active: boolean): string {
  const base =
    "min-w-[4.25rem] flex-1 rounded-md px-2 py-2 text-center text-xs font-semibold ring-1 transition sm:min-w-[5rem] sm:text-sm";
  if (severity === "info") {
    return active
      ? `${base} bg-sky-600 text-white ring-sky-700 shadow-sm`
      : `${base} bg-white text-sky-900 ring-slate-200 hover:bg-sky-50 hover:ring-sky-300`;
  }
  if (severity === "warning") {
    return active
      ? `${base} bg-amber-500 text-amber-950 ring-amber-600 shadow-sm`
      : `${base} bg-white text-amber-950 ring-slate-200 hover:bg-amber-50 hover:ring-amber-300`;
  }
  return active
    ? `${base} bg-rose-600 text-white ring-rose-700 shadow-sm`
    : `${base} bg-white text-rose-900 ring-slate-200 hover:bg-rose-50 hover:ring-rose-300`;
}

function RuleRowsEditor({
  constraints,
  onChange,
  allTemplates,
  excludeVariantId,
  propertyDefinitions
}: {
  constraints: ShiftConstraintRecord[];
  onChange: (next: ShiftConstraintRecord[]) => void;
  allTemplates: ShiftTemplateRecord[];
  excludeVariantId?: number | null;
  propertyDefinitions: PropertyDefinitionBrief[];
}) {
  const { locale } = useLocale();
  const coupledFieldId = useId();
  const partnerOffsetHintRef = useRef<HTMLDivElement>(null);
  const [partnerOffsetHintOpen, setPartnerOffsetHintOpen] = useState(false);
  const variantChoices = useMemo(
    () => flattenVariantOptions(allTemplates, excludeVariantId ?? null),
    [allTemplates, excludeVariantId]
  );
  useEffect(() => {
    if (!partnerOffsetHintOpen) {
      return;
    }
    const onDocMouseDown = (event: MouseEvent) => {
      if (!partnerOffsetHintRef.current?.contains(event.target as Node)) {
        setPartnerOffsetHintOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setPartnerOffsetHintOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocMouseDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onDocMouseDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [partnerOffsetHintOpen]);
  if (!constraints.length) {
    return null;
  }
  return (
    <div className="grid gap-2 rounded-lg border border-slate-200 bg-white p-3">
      {constraints.map((rule) => (
        <div key={rule.constraintInstanceId} className="grid gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <p className="min-w-0 flex-1 text-sm font-semibold text-slate-800">
              {t(
                locale,
                SHIFT_CONSTRAINT_OPTIONS.find((option) => option.type === rule.type)?.label ?? "constraintRules"
              )}
            </p>
            <div
              className="flex flex-col gap-1.5"
              role="group"
              aria-label={t(locale, "constraintRuleSeverityGroup")}
            >
              {rule.type === "unavailable_overlap_policy" ? (
                <select
                  className={inputClass}
                  value={rule.unavailable_overlap_mode ?? "warn"}
                  onChange={(event) =>
                    onChange(
                      setConstraintUnavailableOverlapMode(
                        constraints,
                        rule.constraintInstanceId,
                        event.target.value as UnavailableOverlapPolicyMode
                      )
                    )
                  }
                >
                  <option value="allow">{t(locale, "constraintUnavailableOverlapAllow")}</option>
                  <option value="warn">{t(locale, "constraintUnavailableOverlapWarn")}</option>
                  <option value="block">{t(locale, "constraintUnavailableOverlapBlock")}</option>
                </select>
              ) : (
                <div className="flex gap-1 rounded-lg border border-slate-200 bg-white p-1">
                  {CONSTRAINT_SEVERITY_ORDER.map((severity) => {
                    const active = rule.severity === severity;
                    const labelKey =
                      severity === "info"
                        ? "constraintSeverityInfo"
                        : severity === "warning"
                          ? "constraintSeverityWarning"
                          : "constraintSeverityError";
                    return (
                      <button
                        key={severity}
                        type="button"
                        aria-pressed={active}
                        title={severity === "error" ? t(locale, "constraintSeverityErrorHint") : undefined}
                        className={constraintSeverityButtonClass(severity, active)}
                        onClick={() => onChange(setConstraintSeverity(constraints, rule.constraintInstanceId, severity))}
                      >
                        {t(locale, labelKey)}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
            <button
              type="button"
              className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-rose-200 bg-rose-50 text-rose-700"
              onClick={() => onChange(removeConstraint(constraints, rule.constraintInstanceId))}
              aria-label={t(locale, "removeRule")}
              title={t(locale, "removeRule")}
            >
              <Trash2 size={16} />
            </button>
          </div>
          {rule.type === "min_rest_hours" ? (
            <input
              className={`${inputClass} max-w-xs`}
              type="number"
              min={1}
              max={48}
              value={rule.min_rest_hours ?? 11}
              onChange={(event) =>
                onChange(setConstraintMinRestHours(constraints, rule.constraintInstanceId, Number(event.target.value) || 1))
              }
            />
          ) : null}
          {rule.type === "max_assignments_per_month" ? (
            <input
              className={`${inputClass} max-w-xs`}
              type="number"
              min={1}
              max={31}
              value={rule.max_assignments_per_month ?? 4}
              onChange={(event) =>
                onChange(setConstraintMaxAssignments(constraints, rule.constraintInstanceId, Number(event.target.value) || 1))
              }
            />
          ) : null}
          {rule.type === "requires_coupled_shift" ? (
            variantChoices.length ? (
              <div className="grid max-w-2xl gap-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
                <Field label={t(locale, "constraintCoupledPartnerVariant")}>
                  <select
                    className={inputClass}
                    value={String(rule.paired_shift_variant_id ?? variantChoices[0]?.id ?? "")}
                    onChange={(event) => {
                      const nextId = Number(event.target.value);
                      if (Number.isFinite(nextId) && nextId >= 1) {
                        onChange(setConstraintPairedVariant(constraints, rule.constraintInstanceId, nextId));
                      }
                    }}
                  >
                    {variantChoices.map((opt) => (
                      <option key={opt.id} value={opt.id}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </Field>
                <div className="flex flex-col gap-1">
                  <div className="relative inline-flex min-w-0 flex-col" ref={partnerOffsetHintRef}>
                    <div className="flex items-center gap-1">
                      <label
                        className="text-xs font-medium text-slate-600"
                        htmlFor={`${coupledFieldId}-${rule.constraintInstanceId}-offset`}
                      >
                        {t(locale, "constraintPartnerDayOffsetLabel")}
                      </label>
                      <button
                        type="button"
                        className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border text-slate-600 outline-none ring-mint/20 transition focus:ring-4 ${
                          partnerOffsetHintOpen
                            ? "border-slate-300 bg-slate-50 text-slate-800 ring-1 ring-slate-200"
                            : "border-slate-200 bg-white hover:bg-slate-50"
                        }`}
                        aria-expanded={partnerOffsetHintOpen}
                        aria-controls={`${coupledFieldId}-offset-hint`}
                        aria-label={t(locale, "constraintPartnerDayOffsetInfoButton")}
                        onClick={() => setPartnerOffsetHintOpen((open) => !open)}
                      >
                        <Info size={15} strokeWidth={2} aria-hidden />
                      </button>
                    </div>
                    {partnerOffsetHintOpen ? (
                      <div
                        id={`${coupledFieldId}-offset-hint`}
                        role="region"
                        aria-label={t(locale, "constraintPartnerDayOffsetHint")}
                        className="absolute left-0 top-full z-30 mt-1 min-w-[14rem] max-w-[min(20rem,calc(100vw-2rem))] rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-xs leading-relaxed text-slate-700 shadow-soft ring-1 ring-slate-100"
                      >
                        {t(locale, "constraintPartnerDayOffsetHint")}
                      </div>
                    ) : null}
                  </div>
                  <input
                    id={`${coupledFieldId}-${rule.constraintInstanceId}-offset`}
                    className={`${inputClass} h-9 w-14 shrink-0 tabular-nums`}
                    type="number"
                    min={-7}
                    max={7}
                    value={rule.partner_day_offset ?? 1}
                    onChange={(event) => {
                      const v = parseInt(event.target.value, 10);
                      const clamped = Number.isNaN(v) ? 1 : Math.min(7, Math.max(-7, v));
                      onChange(setConstraintPartnerDayOffset(constraints, rule.constraintInstanceId, clamped));
                    }}
                  />
                </div>
              </div>
            ) : (
              <p className="text-xs text-amber-800">{t(locale, "constraintCoupledNoVariantsHint")}</p>
            )
          ) : null}
          {rule.type === "team_member_property_requirement" && rule.property_requirement ? (
            <TeamMemberPropertyRequirementConstraintEditor
              value={rule.property_requirement}
              definitions={propertyDefinitions}
              onChange={(next) =>
                onChange(setConstraintPropertyRequirement(constraints, rule.constraintInstanceId, next))
              }
            />
          ) : null}
        </div>
      ))}
    </div>
  );
}

function VariantEditFields({
  variant,
  applicability,
  onApplicabilityChange,
  constraints,
  onConstraintsChange,
  onRemove,
  allTemplates
}: {
  variant: ShiftVariantRecord;
  applicability: VariantApplicabilityState;
  onApplicabilityChange: (next: VariantApplicabilityState) => void;
  constraints: ShiftConstraintRecord[];
  onConstraintsChange: (next: ShiftConstraintRecord[]) => void;
  onRemove: () => void;
  allTemplates: ShiftTemplateRecord[];
}) {
  const { locale } = useLocale();
  const propertyDefinitions = useTeamMemberPropertyDefinitions();
  const [rulePickerOpen, setRulePickerOpen] = useState(false);
  const [nextRuleType, setNextRuleType] = useState<ShiftConstraintType>(SHIFT_CONSTRAINT_OPTIONS[0].type);

  function addRule() {
    onConstraintsChange(
      addConstraint(constraints, nextRuleType, {
        allTemplates,
        excludeVariantId: variant.id,
        propertyDefinitions
      })
    );
    setRulePickerOpen(false);
  }

  return (
    <div className="grid gap-3 rounded-lg bg-slate-50 p-3 ring-1 ring-slate-200 lg:grid-cols-[minmax(16rem,1fr)_8rem_8rem_6rem_auto]">
      <Field label={t(locale, "name")}><input className={inputClass} name={`variant_${variant.id}_label`} defaultValue={variant.label} required /></Field>
      <Field label={t(locale, "start")}><input className={`${inputClass} w-full`} name={`variant_${variant.id}_starts_at`} type="time" defaultValue={formatScalar(locale, variant.starts_at)} required /></Field>
      <Field label={t(locale, "end")}><input className={`${inputClass} w-full`} name={`variant_${variant.id}_ends_at`} type="time" defaultValue={formatScalar(locale, variant.ends_at)} required /></Field>
      <Field label={t(locale, "requiredCount")}><input className={`${inputClass} w-full`} name={`variant_${variant.id}_required_count`} type="number" min="1" max="20" defaultValue={variant.required_count} /></Field>
      <label className="flex h-11 items-center gap-2 self-end rounded-lg bg-white px-3 text-sm font-semibold text-slate-700 ring-1 ring-slate-200">
        <input name={`variant_${variant.id}_is_active`} type="checkbox" defaultChecked={variant.is_active} />
        {t(locale, "isActive")}
      </label>
      <button
        type="button"
        onClick={onRemove}
        className="inline-flex h-11 w-11 items-center justify-center self-end rounded-lg border border-rose-200 bg-rose-50 text-rose-700"
        aria-label={t(locale, "removeVariant")}
        title={t(locale, "removeVariant")}
      >
        <Trash2 size={16} />
      </button>
      <div className="flex items-end justify-end">
        <button
          type="button"
          className="inline-flex h-11 items-center justify-center rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700"
          onClick={() => setRulePickerOpen((open) => !open)}
        >
          {t(locale, "addRule")}
        </button>
      </div>
      <div className="lg:col-span-full">
        <VariantApplicabilityEditor value={applicability} onChange={onApplicabilityChange} />
      </div>
      {rulePickerOpen ? (
        <div className="lg:col-span-full grid gap-2 rounded-lg border border-slate-200 bg-white p-3 md:grid-cols-[minmax(16rem,1fr)_auto]">
          <select
            className={inputClass}
            value={nextRuleType}
            onChange={(event) => setNextRuleType(event.target.value as ShiftConstraintType)}
          >
            {SHIFT_CONSTRAINT_OPTIONS.map((option) => (
              <option key={option.type} value={option.type}>
                {t(locale, option.label)}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="inline-flex h-11 items-center justify-center rounded-lg bg-ink px-3 text-sm font-semibold text-white"
            onClick={addRule}
          >
            {t(locale, "addRule")}
          </button>
        </div>
      ) : null}
      <div className="lg:col-span-full">
        <RuleRowsEditor
          constraints={constraints}
          onChange={onConstraintsChange}
          allTemplates={allTemplates}
          excludeVariantId={variant.id}
          propertyDefinitions={propertyDefinitions}
        />
      </div>
    </div>
  );
}

function PendingVariantFields({
  variant,
  onChange,
  onRemove,
  allTemplates
}: {
  variant: PendingVariantDraft;
  onChange: (next: PendingVariantDraft) => void;
  onRemove: () => void;
  allTemplates: ShiftTemplateRecord[];
}) {
  const { locale } = useLocale();
  const propertyDefinitions = useTeamMemberPropertyDefinitions();
  const [rulePickerOpen, setRulePickerOpen] = useState(false);
  const [nextRuleType, setNextRuleType] = useState<ShiftConstraintType>(SHIFT_CONSTRAINT_OPTIONS[0].type);

  return (
    <div className="grid gap-3 rounded-lg border border-dashed border-slate-300 bg-slate-50 p-3 ring-1 ring-slate-200 lg:grid-cols-[minmax(16rem,1fr)_8rem_8rem_6rem_auto]">
      <Field label={t(locale, "name")}>
        <input
          className={inputClass}
          value={variant.label}
          onChange={(event) => onChange({ ...variant, label: event.target.value })}
          required
        />
      </Field>
      <Field label={t(locale, "start")}>
        <input
          className={`${inputClass} w-full`}
          type="time"
          value={variant.starts_at}
          onChange={(event) => onChange({ ...variant, starts_at: event.target.value })}
          required
        />
      </Field>
      <Field label={t(locale, "end")}>
        <input
          className={`${inputClass} w-full`}
          type="time"
          value={variant.ends_at}
          onChange={(event) => onChange({ ...variant, ends_at: event.target.value })}
          required
        />
      </Field>
      <Field label={t(locale, "requiredCount")}>
        <input
          className={`${inputClass} w-full`}
          type="number"
          min="1"
          max="20"
          value={variant.required_count}
          onChange={(event) => onChange({ ...variant, required_count: Number(event.target.value) || 1 })}
        />
      </Field>
      <div className="flex h-11 items-center justify-end gap-2 self-end">
        <button
          type="button"
          onClick={() => setRulePickerOpen((open) => !open)}
          className="inline-flex h-11 items-center justify-center rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700"
        >
          {t(locale, "addRule")}
        </button>
        <label className="inline-flex h-11 items-center gap-2 rounded-lg bg-white px-3 text-sm font-semibold text-slate-700 ring-1 ring-slate-200">
          <input
            type="checkbox"
            checked={variant.is_active}
            onChange={(event) => onChange({ ...variant, is_active: event.target.checked })}
          />
          {t(locale, "isActive")}
        </label>
        <button
          type="button"
          onClick={onRemove}
          className="inline-flex h-11 w-11 items-center justify-center rounded-lg border border-rose-200 bg-rose-50 text-rose-700"
          aria-label={t(locale, "removeVariant")}
          title={t(locale, "removeVariant")}
        >
          <Trash2 size={16} />
        </button>
      </div>
      <div className="lg:col-span-full">
        <VariantApplicabilityEditor
          value={{
            start_day_class: variant.start_day_class,
            end_day_class: variant.end_day_class || null,
            start_limit_weekdays: variant.start_limit_weekdays,
            start_weekdays: variant.start_weekdays,
            end_limit_weekdays: variant.end_limit_weekdays,
            end_weekdays: variant.end_weekdays,
            include_holidays: variant.include_holidays
          }}
          onChange={(next) =>
            onChange({
              ...variant,
              start_day_class: next.start_day_class,
              end_day_class: next.end_day_class ?? "",
              start_limit_weekdays: next.start_limit_weekdays,
              start_weekdays: next.start_weekdays,
              end_limit_weekdays: next.end_limit_weekdays,
              end_weekdays: next.end_weekdays,
              include_holidays: next.include_holidays
            })
          }
        />
      </div>
      {rulePickerOpen ? (
        <div className="lg:col-span-full grid gap-2 rounded-lg border border-slate-200 bg-white p-3 md:grid-cols-[minmax(16rem,1fr)_auto]">
          <select
            className={inputClass}
            value={nextRuleType}
            onChange={(event) => setNextRuleType(event.target.value as ShiftConstraintType)}
          >
            {SHIFT_CONSTRAINT_OPTIONS.map((option) => (
              <option key={option.type} value={option.type}>
                {t(locale, option.label)}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="inline-flex h-11 items-center justify-center rounded-lg bg-ink px-3 text-sm font-semibold text-white"
            onClick={() => {
              onChange({
                ...variant,
                constraints: addConstraint(variant.constraints, nextRuleType, {
                  allTemplates,
                  excludeVariantId: null,
                  propertyDefinitions
                })
              });
              setRulePickerOpen(false);
            }}
          >
            {t(locale, "addRule")}
          </button>
        </div>
      ) : null}
      <div className="lg:col-span-full">
        <RuleRowsEditor
          constraints={variant.constraints}
          onChange={(constraints) => onChange({ ...variant, constraints })}
          allTemplates={allTemplates}
          propertyDefinitions={propertyDefinitions}
        />
      </div>
    </div>
  );
}

function VariantRows({ variants }: { variants: ShiftVariantRecord[] }) {
  const { locale } = useLocale();
  if (!variants.length) {
    return <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-500 ring-1 ring-slate-100">{t(locale, "noVariants")}</p>;
  }
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200">
      <div className="hidden grid-cols-[minmax(7rem,1.4fr)_minmax(9rem,1.2fr)_minmax(6rem,0.8fr)_4rem_4rem] gap-3 bg-slate-50 px-3 py-2 text-[0.65rem] font-semibold uppercase tracking-wide text-slate-500 sm:grid">
        <span>{t(locale, "name")}</span>
        <span>{t(locale, "applicability")}</span>
        <span>{t(locale, "timeRange")}</span>
        <span>{t(locale, "count")}</span>
        <span>{t(locale, "status")}</span>
      </div>
      <div className="divide-y divide-slate-100">
        {variants.map((variant) => (
          <div key={variant.id} className="grid gap-2 px-3 py-3 text-sm sm:grid-cols-[minmax(7rem,1.4fr)_minmax(9rem,1.2fr)_minmax(6rem,0.8fr)_4rem_4rem] sm:items-center sm:gap-3">
            <div className="font-semibold text-ink">{variant.label}</div>
            <div className="flex flex-wrap items-center gap-1.5">
              <VariantApplicabilitySummary variant={variant} />
            </div>
            <div className="font-mono text-xs text-slate-700 sm:text-sm">{formatVariantTime(variant)}</div>
            <div className="text-slate-700">{variant.required_count}</div>
            <div>
              <span className={`rounded-full px-2 py-1 text-xs font-semibold ring-1 ${variant.is_active ? "bg-emerald-50 text-emerald-700 ring-emerald-200" : "bg-slate-100 text-slate-500 ring-slate-200"}`}>
                {variant.is_active ? t(locale, "yes") : t(locale, "no")}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function useTeamMemberPropertyDefinitions(): PropertyDefinitionBrief[] {
  const [defs, setDefs] = useState<PropertyDefinitionBrief[]>([]);
  useEffect(() => {
    void apiFetch<{ id: number; name: string; type: string; options?: string[] }[]>(
      "/api/v1/team-member-property-definitions?active_only=true"
    )
      .then((rows) =>
        setDefs(
          rows.map((row) => ({
            id: row.id,
            name: row.name,
            type: row.type,
            options: Array.isArray(row.options) ? row.options : []
          }))
        )
      )
      .catch(() => setDefs([]));
  }, []);
  return defs;
}

function ShiftTemplateEditorModal({
  template,
  allTemplates,
  onChanged,
  onClose
}: {
  template: ShiftTemplateRecord;
  allTemplates: ShiftTemplateRecord[];
  onChanged: () => Promise<void>;
  onClose: () => void;
}) {
  const { locale } = useLocale();
  const propertyDefinitions = useTeamMemberPropertyDefinitions();
  const title = template.name;
  const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState(false);
  const [removedVariantIds, setRemovedVariantIds] = useState<number[]>([]);
  const [pendingVariants, setPendingVariants] = useState<PendingVariantDraft[]>([]);
  const [templateConstraints, setTemplateConstraints] = useState<ShiftConstraintRecord[]>(() =>
    parseShiftConstraintList(template.constraints)
  );
  const [templateRulePickerOpen, setTemplateRulePickerOpen] = useState(false);
  const [nextTemplateRuleType, setNextTemplateRuleType] = useState<ShiftConstraintType>(SHIFT_CONSTRAINT_OPTIONS[0].type);
  const [variantConstraintsById, setVariantConstraintsById] = useState<Record<number, ShiftConstraintRecord[]>>(
    () =>
      Object.fromEntries(
        (template.variants ?? []).map((variant) => [variant.id, parseShiftConstraintList(variant.constraints)])
      )
  );
  const [variantApplicabilityById, setVariantApplicabilityById] = useState<Record<number, VariantApplicabilityState>>(
    () =>
      Object.fromEntries(
        (template.variants ?? []).map((variant) => [variant.id, applicabilityStateFromVariant(variant)])
      )
  );
  const [variantDeleteCandidate, setVariantDeleteCandidate] = useState<ShiftVariantRecord | null>(null);
  const [editorSaveError, setEditorSaveError] = useState<string | null>(null);

  useEffect(() => {
    setEditorSaveError(null);
    setTemplateConstraints(parseShiftConstraintList(template.constraints));
    setTemplateRulePickerOpen(false);
    setNextTemplateRuleType(SHIFT_CONSTRAINT_OPTIONS[0].type);
    setVariantConstraintsById(
      Object.fromEntries(
        (template.variants ?? []).map((variant) => [variant.id, parseShiftConstraintList(variant.constraints)])
      )
    );
    setVariantApplicabilityById(
      Object.fromEntries(
        (template.variants ?? []).map((variant) => [variant.id, applicabilityStateFromVariant(variant)])
      )
    );
  }, [template.id]);

  function addPendingVariant() {
    setPendingVariants((current) => [
      ...current,
      {
        uid: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        label: "",
        start_day_class: "any",
        end_day_class: "",
        start_limit_weekdays: false,
        start_weekdays: [],
        end_limit_weekdays: false,
        end_weekdays: [],
        include_holidays: false,
        starts_at: "",
        ends_at: "",
        required_count: 1,
        constraints: [],
        is_active: true
      }
    ]);
  }

  function updatePendingVariant(uid: string, next: PendingVariantDraft) {
    setPendingVariants((current) => current.map((variant) => (variant.uid === uid ? next : variant)));
  }

  function removePendingVariant(uid: string) {
    setPendingVariants((current) => current.filter((variant) => variant.uid !== uid));
  }

  function removeExistingVariant(variantId: number) {
    setRemovedVariantIds((current) => (current.includes(variantId) ? current : [...current, variantId]));
  }

  function confirmDeleteVariant() {
    if (!variantDeleteCandidate) {
      return;
    }
    removeExistingVariant(variantDeleteCandidate.id);
    setVariantDeleteCandidate(null);
  }

  async function deleteTemplate() {
    await apiFetch(`/api/v1/shift-templates/${template.id}`, { method: "DELETE" });
    setIsDeleteConfirmOpen(false);
    await onChanged();
    onClose();
  }

  async function submitEditor(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setEditorSaveError(null);
    const form = new FormData(event.currentTarget);
    try {
      await apiFetch(`/api/v1/shift-templates/${template.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          code: form.get("code"),
          name: form.get("name"),
          category: form.get("category"),
          constraints: shiftConstraintsToApi(templateConstraints),
          is_active: form.get("is_active") === "on"
        })
      });
    } catch (error) {
      setEditorSaveError(apiFailureUserMessage(locale, error));
      return;
    }
    for (const variant of template.variants ?? []) {
      if (removedVariantIds.includes(variant.id)) {
        continue;
      }
      const startsAt = form.get(`variant_${variant.id}_starts_at`);
      const endsAt = form.get(`variant_${variant.id}_ends_at`);
      await apiFetch(`/api/v1/shift-templates/variants/${variant.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          label: form.get(`variant_${variant.id}_label`),
          ...applicabilityPayload(variantApplicabilityById[variant.id] ?? applicabilityStateFromVariant(variant)),
          starts_at: startsAt,
          ends_at: endsAt,
          end_day_offset: inferEndDayOffset(startsAt, endsAt),
          required_count: Number(form.get(`variant_${variant.id}_required_count`)),
          constraints: shiftConstraintsToApi(variantConstraintsById[variant.id] ?? []),
          is_active: form.get(`variant_${variant.id}_is_active`) === "on"
        })
      });
    }
    for (const variantId of removedVariantIds) {
      await apiFetch(`/api/v1/shift-templates/variants/${variantId}`, {
        method: "DELETE"
      });
    }
    for (const variant of pendingVariants) {
      await apiFetch(`/api/v1/shift-templates/${template.id}/variants`, {
        method: "POST",
        body: JSON.stringify({
          label: variant.label,
          ...pendingApplicabilityPayload(variant),
          starts_at: variant.starts_at,
          ends_at: variant.ends_at,
          end_day_offset: inferEndDayOffset(variant.starts_at, variant.ends_at),
          required_count: variant.required_count,
          constraints: shiftConstraintsToApi(variant.constraints),
          is_active: variant.is_active
        })
      });
    }
    setRemovedVariantIds([]);
    setPendingVariants([]);
    await onChanged();
  }

  const visibleVariants = (template.variants ?? []).filter((variant) => !removedVariantIds.includes(variant.id));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 px-4 py-6 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby={`shift-template-edit-${template.id}`}>
      <form className="max-h-[90vh] w-full max-w-6xl overflow-auto rounded-xl bg-white p-5 shadow-soft ring-1 ring-slate-200" onSubmit={submitEditor}>
        <div className="mb-5 flex items-start justify-between gap-3">
          <div>
            <h2 id={`shift-template-edit-${template.id}`} className="text-lg font-semibold text-ink">{t(locale, "editShiftTemplate")}</h2>
            <p className="mt-1 text-sm text-slate-500">{template.code} · {title}</p>
            {editorSaveError ? (
              <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950" role="alert">
                {editorSaveError}
              </p>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            <button
              aria-label={t(locale, "deleteShiftTemplate")}
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-rose-200 bg-rose-50 text-rose-700"
              onClick={() => setIsDeleteConfirmOpen(true)}
              title={t(locale, "deleteShiftTemplate")}
              type="button"
            >
              <Trash2 size={17} />
            </button>
            <button
              aria-label={t(locale, "addVariant")}
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600"
              onClick={addPendingVariant}
              title={t(locale, "addVariant")}
              type="button"
            >
              <Plus size={17} />
            </button>
            <button
              aria-label={t(locale, "save")}
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-ink text-white"
              title={t(locale, "save")}
              type="submit"
            >
              <Save size={17} />
            </button>
            <button
              aria-label={t(locale, "close")}
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600"
              onClick={onClose}
              type="button"
            >
              <X size={17} />
            </button>
          </div>
        </div>
        <div className="grid gap-3 rounded-lg bg-slate-50 p-3 ring-1 ring-slate-200 md:grid-cols-[8rem_minmax(14rem,1fr)_14rem_auto_auto]">
          <Field label={t(locale, "code")}><input className={`${inputClass} w-full`} name="code" defaultValue={template.code} required /></Field>
          <Field label={t(locale, "name")}><input className={`${inputClass} w-full`} name="name" defaultValue={template.name} required /></Field>
          <Field label={t(locale, "category")}><select className={`${inputClass} w-full`} name="category" defaultValue={template.category}>{categoryOptions(locale)}</select></Field>
          <label className="flex h-11 items-center gap-2 self-end rounded-lg bg-white px-3 text-sm font-semibold text-slate-700 ring-1 ring-slate-200">
            <input name="is_active" type="checkbox" defaultChecked={template.is_active} />
            {t(locale, "isActive")}
          </label>
          <button
            type="button"
            className="inline-flex h-11 items-center justify-center self-end rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700"
            onClick={() => setTemplateRulePickerOpen((open) => !open)}
          >
            {t(locale, "addRule")}
          </button>
        </div>
        {templateRulePickerOpen ? (
          <div className="mt-3 grid gap-2 rounded-lg border border-slate-200 bg-white p-3 md:grid-cols-[minmax(20rem,1fr)_auto]">
            <select
              className={inputClass}
              value={nextTemplateRuleType}
              onChange={(event) => setNextTemplateRuleType(event.target.value as ShiftConstraintType)}
            >
              {SHIFT_CONSTRAINT_OPTIONS.map((option) => (
                <option key={option.type} value={option.type}>
                  {t(locale, option.label)}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="inline-flex h-11 items-center justify-center rounded-lg bg-ink px-3 text-sm font-semibold text-white"
              onClick={() => {
                setTemplateConstraints((current) =>
                  addConstraint(current, nextTemplateRuleType, { allTemplates, propertyDefinitions })
                );
                setTemplateRulePickerOpen(false);
              }}
            >
              {t(locale, "addRule")}
            </button>
          </div>
        ) : null}
        <div className="mt-3">
          <RuleRowsEditor
            constraints={templateConstraints}
            onChange={setTemplateConstraints}
            allTemplates={allTemplates}
            propertyDefinitions={propertyDefinitions}
          />
        </div>
        <div className="mt-5 grid gap-3">
          <h3 className="text-sm font-semibold text-ink">{t(locale, "editVariants")}</h3>
          {visibleVariants.length ? (
            visibleVariants.map((variant) => (
              <VariantEditFields
                key={variant.id}
                variant={variant}
                applicability={variantApplicabilityById[variant.id] ?? applicabilityStateFromVariant(variant)}
                onApplicabilityChange={(next) =>
                  setVariantApplicabilityById((current) => ({ ...current, [variant.id]: next }))
                }
                constraints={variantConstraintsById[variant.id] ?? []}
                onConstraintsChange={(next) =>
                  setVariantConstraintsById((current) => ({ ...current, [variant.id]: next }))
                }
                onRemove={() => setVariantDeleteCandidate(variant)}
                allTemplates={allTemplates}
              />
            ))
          ) : (
            <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-500 ring-1 ring-slate-100">{t(locale, "noVariants")}</p>
          )}
        </div>
        {pendingVariants.length ? (
          <div className="mt-5 grid gap-3">
            <h3 className="text-sm font-semibold text-ink">{t(locale, "newVariants")}</h3>
            {pendingVariants.map((variant) => (
              <PendingVariantFields
                key={variant.uid}
                variant={variant}
                onChange={(next) => updatePendingVariant(variant.uid, next)}
                onRemove={() => removePendingVariant(variant.uid)}
                allTemplates={allTemplates}
              />
            ))}
          </div>
        ) : null}
        {variantDeleteCandidate ? (
          <div className="mt-5 rounded-xl bg-rose-50 p-4 ring-1 ring-rose-200">
            <div className="flex gap-3">
              <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-white text-rose-700 ring-1 ring-rose-200">
                <AlertTriangle size={19} />
              </span>
              <div>
                <h3 className="text-sm font-semibold text-rose-950">{t(locale, "deleteVariant")}</h3>
                <p className="mt-1 text-sm text-rose-900">
                  {variantDeleteCandidate.label} · {t(locale, "deleteVariantWarning")}
                </p>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap justify-end gap-2">
              <button
                className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700"
                onClick={() => setVariantDeleteCandidate(null)}
                type="button"
              >
                {t(locale, "close")}
              </button>
              <button
                className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-rose-700 px-4 text-sm font-semibold text-white"
                onClick={confirmDeleteVariant}
                type="button"
              >
                <Trash2 size={16} />
                {t(locale, "confirm")}
              </button>
            </div>
          </div>
        ) : null}
        {isDeleteConfirmOpen ? (
          <div className="mt-5 rounded-xl bg-rose-50 p-4 ring-1 ring-rose-200">
            <div className="flex gap-3">
              <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-white text-rose-700 ring-1 ring-rose-200">
                <AlertTriangle size={19} />
              </span>
              <div>
                <h3 className="text-sm font-semibold text-rose-950">{t(locale, "deleteShiftTemplate")}</h3>
                <p className="mt-1 text-sm text-rose-900">{t(locale, "deleteShiftTemplateWarning")}</p>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap justify-end gap-2">
              <button
                className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700"
                onClick={() => setIsDeleteConfirmOpen(false)}
                type="button"
              >
                {t(locale, "close")}
              </button>
              <button
                className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-rose-700 px-4 text-sm font-semibold text-white"
                onClick={deleteTemplate}
                type="button"
              >
                <Trash2 size={16} />
                {t(locale, "confirm")}
              </button>
            </div>
          </div>
        ) : null}
      </form>
    </div>
  );
}

function ShiftTemplateCard({
  template,
  allTemplates,
  onChanged
}: {
  template: ShiftTemplateRecord;
  allTemplates: ShiftTemplateRecord[];
  onChanged: () => Promise<void>;
}) {
  const { locale } = useLocale();
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const title = template.name;
  const subtitle = template.name;

  return (
    <>
    <article className="overflow-hidden rounded-xl border border-slate-200/90 bg-white shadow-soft ring-1 ring-slate-100/80">
      <div className="border-b border-mint/25 bg-gradient-to-r from-mint/10 via-white to-sky-50/40 px-4 py-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-md bg-ink px-2 py-1 font-mono text-xs font-semibold text-white">{template.code}</span>
              <h2 className="truncate text-sm font-semibold text-ink">{title}</h2>
            </div>
            <p className="mt-1 text-xs text-slate-500">{subtitle}</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-sky-50 px-2.5 py-1 text-xs font-semibold text-sky-800 ring-1 ring-sky-200">
              {categoryLabel(locale, template.category)}
            </span>
            <button
              type="button"
              onClick={() => setIsEditorOpen(true)}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 shadow-sm hover:bg-slate-50"
              aria-label={t(locale, "edit")}
              title={t(locale, "edit")}
            >
              <MoreVertical size={17} />
            </button>
          </div>
        </div>
      </div>
      <div className="grid gap-4 p-4">
        <div className="flex flex-wrap gap-2 text-xs text-slate-600">
          <span className={`rounded-full px-2.5 py-1 font-semibold ring-1 ${template.is_active ? "bg-emerald-50 text-emerald-700 ring-emerald-200" : "bg-slate-100 text-slate-500 ring-slate-200"}`}>
            {t(locale, "isActive")}: {template.is_active ? t(locale, "yes") : t(locale, "no")}
          </span>
        </div>
        <VariantRows variants={template.variants ?? []} />
      </div>
    </article>
    {isEditorOpen ? (
      <ShiftTemplateEditorModal
        template={template}
        allTemplates={allTemplates}
        onChanged={onChanged}
        onClose={() => setIsEditorOpen(false)}
      />
    ) : null}
    </>
  );
}

function ShiftTemplateList({ rows, onChanged }: { rows: AnyRecord[]; onChanged: () => Promise<void> }) {
  const templates = rows.filter(isShiftTemplateRecord);
  if (templates.length !== rows.length) {
    return <DataList rows={rows} />;
  }
  if (!templates.length) {
    return <DataList rows={[]} />;
  }
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      {templates.map((template) => (
        <ShiftTemplateCard key={template.id} template={template} allTemplates={templates} onChanged={onChanged} />
      ))}
    </div>
  );
}

export function TeamMemberEditorModal({
  member,
  onChanged,
  onClose,
  embedded = false,
}: {
  member: TeamMemberRecord;
  onChanged: () => Promise<void>;
  onClose: () => void;
  embedded?: boolean;
}) {
  const { locale } = useLocale();
  const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState(false);
  const [shiftGroups, setShiftGroups] = useState<ShiftGroupOption[]>([]);
  const [selectedGroupIds, setSelectedGroupIds] = useState<Set<number>>(() => new Set(member.shift_group_ids ?? []));

  useEffect(() => {
    setSelectedGroupIds(new Set(member.shift_group_ids ?? []));
  }, [member]);

  useEffect(() => {
    void apiFetch<ShiftGroupOption[]>("/api/v1/shift-groups?active_only=true").then(setShiftGroups).catch(() => setShiftGroups([]));
  }, []);

  async function submitEditor(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const rawUserId = form.get("user_id");
    const user_id =
      rawUserId === "" || rawUserId == null ? null : Number(rawUserId);
    await apiFetch(`/api/v1/team-members/${member.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        first_name: form.get("first_name"),
        last_name: form.get("last_name"),
        nickname: form.get("nickname") || null,
        email: form.get("email"),
        employment_percentage: Number(form.get("employment_percentage")),
        notes: form.get("notes"),
        planning_preferences: form.get("planning_preferences") || null,
        is_active: form.get("is_active") === "on",
        shift_group_ids: [...selectedGroupIds],
        user_id
      })
    });
    await onChanged();
    if (!embedded) {
      onClose();
    }
  }

  async function deleteTeamMemberEntry() {
    await apiFetch(`/api/v1/team-members/${member.id}`, { method: "DELETE" });
    setIsDeleteConfirmOpen(false);
    await onChanged();
    onClose();
  }

  const shellClass = embedded
    ? "w-full"
    : "fixed inset-0 z-50 flex items-center justify-center bg-ink/30 px-4 py-6 backdrop-blur-sm";
  const formShellClass = embedded
    ? "max-h-[55vh] w-full overflow-auto rounded-xl border border-slate-200 bg-white p-4 shadow-sm ring-1 ring-slate-100"
    : "max-h-[90vh] w-full max-w-2xl overflow-auto rounded-xl bg-white p-5 shadow-soft ring-1 ring-slate-200";

  return (
    <div className={shellClass} role="dialog" aria-modal="true" aria-labelledby={`team-member-edit-${member.id}`}>
      <form className={formShellClass} onSubmit={submitEditor}>
        <div className="mb-5 flex items-start justify-between gap-3">
          <div>
            <h2 id={`team-member-edit-${member.id}`} className="text-lg font-semibold text-ink">{t(locale, "editTeamMember")}</h2>
            <p className="mt-1 truncate text-sm text-slate-500">{teamMemberLabel(member)} · {member.email}</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              aria-label={t(locale, "deleteTeamMember")}
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-rose-200 bg-rose-50 text-rose-700"
              onClick={() => setIsDeleteConfirmOpen(true)}
              title={t(locale, "deleteTeamMember")}
              type="button"
            >
              <Trash2 size={17} />
            </button>
            <button
              aria-label={t(locale, "save")}
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-ink text-white"
              title={t(locale, "save")}
              type="submit"
            >
              <Save size={17} />
            </button>
            <button
              aria-label={t(locale, "close")}
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600"
              onClick={onClose}
              type="button"
            >
              <X size={17} />
            </button>
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label={t(locale, "firstName")}><input className={inputClass} name="first_name" defaultValue={member.first_name} required /></Field>
          <Field label={t(locale, "lastName")}><input className={inputClass} name="last_name" defaultValue={member.last_name} required /></Field>
          <Field label={t(locale, "nickname")}>
            <input className={inputClass} name="nickname" maxLength={64} defaultValue={member.nickname ?? ""} />
            <p className="mt-1 text-xs text-slate-500">{t(locale, "nicknameHelp")}</p>
          </Field>
          <Field label={t(locale, "email")}><input className={inputClass} name="email" type="email" defaultValue={member.email} required /></Field>
          <Field label={t(locale, "employment")}><input className={inputClass} name="employment_percentage" type="number" min="1" max="100" defaultValue={member.employment_percentage} /></Field>
          <Field label={t(locale, "planningPreferencesField")}>
            <textarea
              className={`${inputClass} min-h-28`}
              name="planning_preferences"
              rows={4}
              defaultValue={member.planning_preferences ?? ""}
            />
          </Field>
          <Field label={t(locale, "notes")}><input className={inputClass} name="notes" defaultValue={member.notes ?? ""} /></Field>
          <Field label={t(locale, "linkedUserId")}>
            <input
              className={inputClass}
              name="user_id"
              type="number"
              min={1}
              defaultValue={member.user_id ?? ""}
              placeholder={t(locale, "emptyValue")}
              title={t(locale, "linkedUserIdHint")}
            />
          </Field>
          <label className="inline-flex h-11 items-center gap-2 rounded-lg bg-white px-3 text-sm font-semibold text-slate-700 ring-1 ring-slate-200">
            <input name="is_active" type="checkbox" defaultChecked={member.is_active} />
            {t(locale, "isActive")}
          </label>
        </div>
        <div className="mt-4 rounded-lg border border-slate-200 p-3">
          <p className="text-sm font-semibold text-ink">{t(locale, "teamMemberShiftGroups")}</p>
          <div className="mt-2 max-h-40 space-y-2 overflow-y-auto text-sm">
            {shiftGroups.map((group) => (
              <label key={group.id} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={selectedGroupIds.has(group.id)}
                  onChange={() => {
                    setSelectedGroupIds((prev) => {
                      const next = new Set(prev);
                      if (next.has(group.id)) {
                        next.delete(group.id);
                      } else {
                        next.add(group.id);
                      }
                      return next;
                    });
                  }}
                />
                <span className="font-mono text-xs">{group.code}</span>
                {group.name}
              </label>
            ))}
          </div>
        </div>
        {isDeleteConfirmOpen ? (
          <div className="mt-5 rounded-xl bg-rose-50 p-4 ring-1 ring-rose-200">
            <div className="flex gap-3">
              <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-white text-rose-700 ring-1 ring-rose-200">
                <AlertTriangle size={19} />
              </span>
              <div>
                <h3 className="text-sm font-semibold text-rose-950">{t(locale, "deleteTeamMember")}</h3>
                <p className="mt-1 text-sm text-rose-900">{t(locale, "deleteTeamMemberWarning")}</p>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap justify-end gap-2">
              <button
                className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700"
                onClick={() => setIsDeleteConfirmOpen(false)}
                type="button"
              >
                {t(locale, "close")}
              </button>
              <button
                className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-rose-700 px-4 text-sm font-semibold text-white"
                onClick={deleteTeamMemberEntry}
                type="button"
              >
                <Trash2 size={16} />
                {t(locale, "confirm")}
              </button>
            </div>
          </div>
        ) : null}
      </form>
      <div className={embedded ? "mt-4" : "mt-4 px-1"}>
        <TeamMemberPropertyValuesEditor teamMemberId={member.id} adminMode />
      </div>
      <div className={embedded ? "mt-4" : "mt-4 px-1"}>
        <TeamMemberPlanningPatternsEditor teamMemberId={member.id} allowErrorSeverity={embedded} />
      </div>
    </div>
  );
}

export function TeamMemberCreateModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => Promise<void>;
}) {
  const { locale } = useLocale();
  const [shiftGroups, setShiftGroups] = useState<ShiftGroupOption[]>([]);
  const [createGroupIds, setCreateGroupIds] = useState<Set<number>>(new Set());

  useEffect(() => {
    void apiFetch<ShiftGroupOption[]>("/api/v1/shift-groups?active_only=true").then(setShiftGroups).catch(() => setShiftGroups([]));
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const rawCreateUserId = form.get("user_id");
    const createUserId =
      rawCreateUserId === "" || rawCreateUserId == null ? null : Number(rawCreateUserId);
    await apiFetch("/api/v1/team-members", {
      method: "POST",
      body: JSON.stringify({
        first_name: form.get("first_name"),
        last_name: form.get("last_name"),
        nickname: form.get("nickname") || null,
        email: form.get("email"),
        employment_percentage: Number(form.get("employment_percentage")),
        notes: form.get("notes"),
        planning_preferences: form.get("planning_preferences") || null,
        shift_group_ids: [...createGroupIds],
        user_id: createUserId,
      }),
    });
    setCreateGroupIds(new Set());
    await onCreated();
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 px-4 py-6 backdrop-blur-sm" role="dialog" aria-modal="true">
      <form className="max-h-[90vh] w-full max-w-2xl overflow-auto rounded-xl bg-white p-5 shadow-soft ring-1 ring-slate-200" onSubmit={submit}>
        <div className="mb-4 flex items-start justify-between gap-3">
          <h2 className="text-lg font-semibold text-ink">{t(locale, "addTeamMember")}</h2>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600"
            aria-label={t(locale, "close")}
            title={t(locale, "close")}
          >
            <X size={17} />
          </button>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label={t(locale, "firstName")}>
            <input className={inputClass} name="first_name" required />
          </Field>
          <Field label={t(locale, "lastName")}>
            <input className={inputClass} name="last_name" required />
          </Field>
          <Field label={t(locale, "nickname")}>
            <input className={inputClass} name="nickname" maxLength={64} />
            <p className="mt-1 text-xs text-slate-500">{t(locale, "nicknameHelp")}</p>
          </Field>
          <Field label={t(locale, "email")}>
            <input className={inputClass} name="email" type="email" required />
          </Field>
          <Field label={t(locale, "employment")}>
            <input className={inputClass} name="employment_percentage" type="number" min="1" max="100" defaultValue="100" />
          </Field>
          <Field label={t(locale, "planningPreferencesField")}>
            <textarea className={`${inputClass} min-h-28`} name="planning_preferences" rows={4} />
          </Field>
          <Field label={t(locale, "notes")}>
            <input className={inputClass} name="notes" />
          </Field>
          <Field label={t(locale, "linkedUserId")}>
            <input
              className={inputClass}
              name="user_id"
              type="number"
              min={1}
              placeholder={t(locale, "emptyValue")}
              title={t(locale, "linkedUserIdHint")}
            />
          </Field>
        </div>
        <div className="mt-4 rounded-lg border border-slate-200 p-3">
          <p className="text-sm font-semibold text-ink">{t(locale, "teamMemberShiftGroups")}</p>
          <div className="mt-2 max-h-36 space-y-2 overflow-y-auto text-sm">
            {shiftGroups.map((group) => (
              <label key={group.id} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={createGroupIds.has(group.id)}
                  onChange={() => {
                    setCreateGroupIds((prev) => {
                      const next = new Set(prev);
                      if (next.has(group.id)) {
                        next.delete(group.id);
                      } else {
                        next.add(group.id);
                      }
                      return next;
                    });
                  }}
                />
                <span className="font-mono text-xs">{group.code}</span>
                {group.name}
              </label>
            ))}
          </div>
        </div>
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700"
          >
            {t(locale, "close")}
          </button>
          <button className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white">
            <Plus size={16} />
            {t(locale, "save")}
          </button>
        </div>
      </form>
    </div>
  );
}

export function ShiftTemplateForm() {
  const { locale } = useLocale();
  const [rows, setRows] = useState<AnyRecord[]>([]);
  const [previewRows, setPreviewRows] = useState<AnyRecord[]>([]);
  const [isCreateTemplateModalOpen, setIsCreateTemplateModalOpen] = useState(false);
  const [isPreviewModalOpen, setIsPreviewModalOpen] = useState(false);
  const currentDate = new Date();
  const [previewYear, setPreviewYear] = useState(String(currentDate.getFullYear()));
  const [previewMonth, setPreviewMonth] = useState(String(currentDate.getMonth() + 1));
  const [createTemplateError, setCreateTemplateError] = useState<string | null>(null);
  const [createTemplateConstraints, setCreateTemplateConstraints] = useState<ShiftConstraintRecord[]>([]);
  const [createTemplateRulePickerOpen, setCreateTemplateRulePickerOpen] = useState(false);
  const [nextCreateTemplateRuleType, setNextCreateTemplateRuleType] = useState<ShiftConstraintType>(
    SHIFT_CONSTRAINT_OPTIONS[0].type
  );
  const propertyDefinitions = useTeamMemberPropertyDefinitions();

  const refresh = useCallback(async () => {
    setRows(await apiFetch<AnyRecord[]>("/api/v1/shift-templates"));
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function submitTemplate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreateTemplateError(null);
    const form = new FormData(event.currentTarget);
    try {
      await apiFetch<AnyRecord>("/api/v1/shift-templates", {
        method: "POST",
        body: JSON.stringify({
          code: form.get("code"),
          name: form.get("name"),
          category: form.get("category"),
          constraints: shiftConstraintsToApi(createTemplateConstraints)
        })
      });
    } catch (error) {
      setCreateTemplateError(apiFailureUserMessage(locale, error));
      return;
    }
    event.currentTarget.reset();
    setIsCreateTemplateModalOpen(false);
    setCreateTemplateError(null);
    setCreateTemplateConstraints([]);
    setCreateTemplateRulePickerOpen(false);
    setNextCreateTemplateRuleType(SHIFT_CONSTRAINT_OPTIONS[0].type);
    await refresh();
  }

  async function loadPreview() {
    setPreviewRows(await apiFetch<AnyRecord[]>("/api/v1/shift-templates/preview", {
      method: "POST",
      body: JSON.stringify({ year: Number(previewYear), month: Number(previewMonth) })
    }));
  }

  return (
    <div className="grid gap-5">
      <Card>
        <div className="grid gap-4">
          <h1 className="text-2xl font-semibold text-ink">{t(locale, "shiftTemplates")}</h1>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 ring-1 ring-slate-100">
              <h2 className="text-base font-semibold text-ink">{t(locale, "shiftTemplateBuilder")}</h2>
              <p className="mt-1 text-sm text-slate-600">{t(locale, "shiftTemplateBuilderDescription")}</p>
              <button
                type="button"
                onClick={() => {
                  setCreateTemplateError(null);
                  setCreateTemplateConstraints([]);
                  setCreateTemplateRulePickerOpen(false);
                  setNextCreateTemplateRuleType(SHIFT_CONSTRAINT_OPTIONS[0].type);
                  setIsCreateTemplateModalOpen(true);
                }}
                className="mt-3 inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white"
              >
                <Plus size={16} />
                {t(locale, "shiftTemplateBuilder")}
              </button>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 ring-1 ring-slate-100">
              <h2 className="text-base font-semibold text-ink">{t(locale, "slotPreview")}</h2>
              <p className="mt-1 text-sm text-slate-600">{t(locale, "slotPreviewDescription")}</p>
              <button
                type="button"
                onClick={async () => {
                  setIsPreviewModalOpen(true);
                  await loadPreview();
                }}
                className="mt-3 inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700"
              >
                <RefreshCw size={16} />
                {t(locale, "slotPreview")}
              </button>
            </div>
          </div>
          <div>
            <button type="button" onClick={refresh} className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold">
              <RefreshCw size={16} />
              {t(locale, "refresh")}
            </button>
          </div>
        </div>
      </Card>
      {isCreateTemplateModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 px-4 py-6 backdrop-blur-sm" role="dialog" aria-modal="true">
          <form className="max-h-[90vh] w-full max-w-2xl overflow-auto rounded-xl bg-white p-5 shadow-soft ring-1 ring-slate-200" onSubmit={submitTemplate}>
            <div className="mb-4 flex items-start justify-between gap-3">
              <h2 className="text-lg font-semibold text-ink">{t(locale, "shiftTemplateBuilder")}</h2>
              <button
                type="button"
                onClick={() => {
                  setCreateTemplateError(null);
                  setIsCreateTemplateModalOpen(false);
                }}
                className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600"
                aria-label={t(locale, "close")}
                title={t(locale, "close")}
              >
                <X size={17} />
              </button>
            </div>
            {createTemplateError ? (
              <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950" role="alert">
                {createTemplateError}
              </div>
            ) : null}
            <div className="grid gap-4 md:grid-cols-2">
              <Field label={t(locale, "code")}><input className={inputClass} name="code" required /></Field>
              <Field label={t(locale, "category")}>
                <select className={inputClass} name="category" defaultValue="bereitschaftsdienst">
                  {SHIFT_TEMPLATE_CATEGORIES.map((category) => (
                    <option key={category.value} value={category.value}>{t(locale, category.label)}</option>
                  ))}
                </select>
              </Field>
              <Field label={t(locale, "name")}><input className={inputClass} name="name" required /></Field>
            </div>
            <div className="mt-4">
              <button
                type="button"
                className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700"
                onClick={() => setCreateTemplateRulePickerOpen((open) => !open)}
              >
                {t(locale, "addRule")}
              </button>
            </div>
            {createTemplateRulePickerOpen ? (
              <div className="mt-3 grid gap-2 rounded-lg border border-slate-200 bg-white p-3 md:grid-cols-[minmax(20rem,1fr)_auto]">
                <select
                  className={inputClass}
                  value={nextCreateTemplateRuleType}
                  onChange={(event) => setNextCreateTemplateRuleType(event.target.value as ShiftConstraintType)}
                >
                  {SHIFT_CONSTRAINT_OPTIONS.map((option) => (
                    <option key={option.type} value={option.type}>
                      {t(locale, option.label)}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="inline-flex h-11 items-center justify-center rounded-lg bg-ink px-3 text-sm font-semibold text-white"
                  onClick={() => {
                    setCreateTemplateConstraints((current) =>
                      addConstraint(current, nextCreateTemplateRuleType, {
                        allTemplates: rows.filter(isShiftTemplateRecord),
                        propertyDefinitions
                      })
                    );
                    setCreateTemplateRulePickerOpen(false);
                  }}
                >
                  {t(locale, "addRule")}
                </button>
              </div>
            ) : null}
            <div className="mt-4">
              <RuleRowsEditor
                constraints={createTemplateConstraints}
                onChange={setCreateTemplateConstraints}
                allTemplates={rows.filter(isShiftTemplateRecord)}
                propertyDefinitions={propertyDefinitions}
              />
            </div>
            <div className="mt-4 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setCreateTemplateError(null);
                  setCreateTemplateConstraints([]);
                  setCreateTemplateRulePickerOpen(false);
                  setNextCreateTemplateRuleType(SHIFT_CONSTRAINT_OPTIONS[0].type);
                  setIsCreateTemplateModalOpen(false);
                }}
                className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700"
              >
                {t(locale, "close")}
              </button>
              <button className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white">
                <Plus size={16} />
                {t(locale, "save")}
              </button>
            </div>
          </form>
        </div>
      ) : null}
      {isPreviewModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 px-4 py-6 backdrop-blur-sm" role="dialog" aria-modal="true">
          <div className="max-h-[90vh] w-full max-w-5xl overflow-auto rounded-xl bg-white p-5 shadow-soft ring-1 ring-slate-200">
            <div className="mb-4 flex items-start justify-between gap-3">
              <h2 className="text-lg font-semibold text-ink">{t(locale, "slotPreview")}</h2>
              <button
                type="button"
                onClick={() => setIsPreviewModalOpen(false)}
                className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600"
                aria-label={t(locale, "close")}
                title={t(locale, "close")}
              >
                <X size={17} />
              </button>
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              <Field label={t(locale, "year")}><input className={inputClass} value={previewYear} onChange={(event) => setPreviewYear(event.target.value)} type="number" /></Field>
              <Field label={t(locale, "month")}><input className={inputClass} value={previewMonth} onChange={(event) => setPreviewMonth(event.target.value)} type="number" min="1" max="12" /></Field>
              <button type="button" onClick={loadPreview} className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white"><RefreshCw size={17} />{t(locale, "refresh")}</button>
            </div>
            <div className="mt-5"><DataList rows={previewRows.slice(0, 24)} /></div>
          </div>
        </div>
      ) : null}
      <Card>
        <h2 className="text-lg font-semibold text-ink">{t(locale, "shiftTemplates")}</h2>
        <div className="mt-5"><ShiftTemplateList rows={rows} onChanged={refresh} /></div>
      </Card>
    </div>
  );
}

export function PeriodForm() {
  const { locale } = useLocale();
  return (
    <form className="grid gap-4 md:grid-cols-2" onSubmit={async (event) => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      await apiFetch("/api/v1/planning-periods", {
        method: "POST",
        body: JSON.stringify({ year: Number(form.get("year")), month: Number(form.get("month")) })
      });
    }}>
      <h2 className="md:col-span-2 text-lg font-semibold">{t(locale, "createPeriod")}</h2>
      <Field label={t(locale, "year")}><input className={inputClass} name="year" type="number" defaultValue="2026" /></Field>
      <Field label={t(locale, "month")}><input className={inputClass} name="month" type="number" min="1" max="12" defaultValue="5" /></Field>
      <button className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white"><Plus size={17} />{t(locale, "save")}</button>
    </form>
  );
}

export function ValidationPanel() {
  const { locale } = useLocale();
  const [rows, setRows] = useState<AnyRecord[]>([]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setRows(await apiFetch<AnyRecord[]>(`/api/v1/validation/${form.get("planning_period_id")}`));
  }
  return (
    <Card>
      <form className="grid gap-4 md:grid-cols-2" onSubmit={submit}>
        <h1 className="md:col-span-2 text-2xl font-semibold text-ink">{t(locale, "warnings")}</h1>
        <Field label={t(locale, "planningPeriod")}><input className={inputClass} name="planning_period_id" type="number" required /></Field>
        <button className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white"><RefreshCw size={17} />{t(locale, "refresh")}</button>
      </form>
      <div className="mt-5"><DataList rows={rows} /></div>
    </Card>
  );
}
