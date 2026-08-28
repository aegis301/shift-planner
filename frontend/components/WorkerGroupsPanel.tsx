"use client";

import { FormEvent, useEffect, useState } from "react";
import { Pencil, Plus, Trash2, X } from "lucide-react";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";
import { ApiError, apiFetch } from "@/lib/api";
import { t, type TranslationKey } from "@/lib/i18n";
import type {
  RegularWeekdayHours,
  Weekday,
  WorkerGroup,
  WorkerGroupCategoryRule,
  WorkerGroupStatusMapping
} from "@/lib/hours";
import { fetchWorkerGroups } from "@/lib/hours";

const WEEKDAYS: Weekday[] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const CATEGORIES: WorkerGroupCategoryRule["category"][] = [
  "bereitschaftsdienst",
  "rufdienst",
  "spaetdienst",
  "other"
];

const weekdayKey: Record<Weekday, TranslationKey> = {
  mon: "hoursWeekdayMon",
  tue: "hoursWeekdayTue",
  wed: "hoursWeekdayWed",
  thu: "hoursWeekdayThu",
  fri: "hoursWeekdayFri",
  sat: "hoursWeekdaySat",
  sun: "hoursWeekdaySun"
};

const categoryKey: Record<WorkerGroupCategoryRule["category"], TranslationKey> = {
  bereitschaftsdienst: "onCallDutyCategory",
  rufdienst: "standbyDutyCategory",
  spaetdienst: "lateDutyCategory",
  other: "other"
};

type Draft = {
  name: string;
  weekly_hours_at_100: number;
  vacation_days_at_100: number;
  regular_week_pattern: RegularWeekdayHours[];
  category_rules: WorkerGroupCategoryRule[];
  status_mappings: WorkerGroupStatusMapping[];
  is_active: boolean;
};

function defaultRules(): WorkerGroupCategoryRule[] {
  return [
    { category: "bereitschaftsdienst", counts_toward_contract: false, credit_mode: "duration" },
    { category: "rufdienst", counts_toward_contract: false, credit_mode: "none" },
    { category: "spaetdienst", counts_toward_contract: true, credit_mode: "duration" },
    { category: "other", counts_toward_contract: true, credit_mode: "duration" }
  ];
}

function emptyDraft(): Draft {
  return {
    name: "",
    weekly_hours_at_100: 40,
    vacation_days_at_100: 30,
    regular_week_pattern: [],
    category_rules: defaultRules(),
    status_mappings: [
      { code: "urlaub", absence_kind: "vacation", consumes_vacation: true, counts_as_work_day: true },
      { code: "forschung", absence_kind: "other", consumes_vacation: false, counts_as_work_day: true },
      { code: "lehre", absence_kind: "other", consumes_vacation: false, counts_as_work_day: true },
      { code: "frei", absence_kind: "none", consumes_vacation: false, counts_as_work_day: false }
    ],
    is_active: true
  };
}

function fromGroup(row: WorkerGroup): Draft {
  return {
    name: row.name,
    weekly_hours_at_100: row.weekly_hours_at_100,
    vacation_days_at_100: row.vacation_days_at_100,
    regular_week_pattern: row.regular_week_pattern.map((item) => ({
      ...item,
      starts_at: item.starts_at.slice(0, 5),
      ends_at: item.ends_at.slice(0, 5)
    })),
    category_rules: CATEGORIES.map((category) => {
      const found = row.category_rules.find((rule) => rule.category === category);
      return found ?? { category, counts_toward_contract: true, credit_mode: "duration" };
    }),
    status_mappings: row.status_mappings,
    is_active: row.is_active
  };
}

export function WorkerGroupsPanel() {
  const { locale } = useLocale();
  const [rows, setRows] = useState<WorkerGroup[]>([]);
  const [editing, setEditing] = useState<{ id: number | null; draft: Draft } | null>(null);
  const [message, setMessage] = useState("");

  async function reload() {
    const data = await fetchWorkerGroups();
    setRows(data);
  }

  useEffect(() => {
    void reload().catch(() => setRows([]));
  }, []);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!editing) {
      return;
    }
    setMessage("");
    const body = {
      name: editing.draft.name.trim(),
      weekly_hours_at_100: editing.draft.weekly_hours_at_100,
      vacation_days_at_100: editing.draft.vacation_days_at_100,
      regular_week_pattern: editing.draft.regular_week_pattern,
      category_rules: editing.draft.category_rules,
      status_mappings: editing.draft.status_mappings,
      is_active: editing.draft.is_active
    };
    try {
      if (editing.id == null) {
        await apiFetch("/api/v1/worker-groups", { method: "POST", body: JSON.stringify(body) });
      } else {
        await apiFetch(`/api/v1/worker-groups/${editing.id}`, { method: "PATCH", body: JSON.stringify(body) });
      }
      setEditing(null);
      await reload();
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : t(locale, "apiRequestFailed", { status: "" }));
    }
  }

  async function remove(id: number) {
    setMessage("");
    try {
      await apiFetch(`/api/v1/worker-groups/${id}`, { method: "DELETE" });
      await reload();
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : t(locale, "apiRequestFailed", { status: "" }));
    }
  }

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-ink">{t(locale, "hoursWorkerGroupsTitle")}</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">{t(locale, "hoursWorkerGroupsHelp")}</p>
        </div>
        <button
          className="inline-flex h-10 items-center gap-2 rounded-lg bg-ink px-3 text-sm font-semibold text-white"
          onClick={() => setEditing({ id: null, draft: emptyDraft() })}
          type="button"
        >
          <Plus size={16} />
          {t(locale, "hoursAddWorkerGroup")}
        </button>
      </div>
      {message ? <p className="text-sm text-rose-700">{message}</p> : null}
      <div className="grid gap-3">
        {rows.map((row) => (
          <Card key={row.id}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="font-semibold text-ink">{row.name}</p>
                <p className="mt-1 text-sm text-slate-600">
                  {row.weekly_hours_at_100} h · {row.vacation_days_at_100} {t(locale, "hoursVacationDaysAt100")}
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200"
                  onClick={() => setEditing({ id: row.id, draft: fromGroup(row) })}
                  type="button"
                  aria-label={t(locale, "hoursEditWorkerGroup")}
                >
                  <Pencil size={16} />
                </button>
                <button
                  className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-rose-200 text-rose-700"
                  onClick={() => void remove(row.id)}
                  type="button"
                  aria-label={t(locale, "hoursDeleteWorkerGroup")}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          </Card>
        ))}
      </div>
      {editing ? (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/30 p-4 sm:items-center">
          <form className="max-h-[92vh] w-full max-w-2xl overflow-auto rounded-xl bg-white p-5 shadow-soft" onSubmit={save}>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-ink">
                {editing.id == null ? t(locale, "hoursAddWorkerGroup") : t(locale, "hoursEditWorkerGroup")}
              </h2>
              <button type="button" onClick={() => setEditing(null)} aria-label={t(locale, "close")}>
                <X size={18} />
              </button>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t(locale, "name")}>
                <input
                  className={inputClass}
                  value={editing.draft.name}
                  onChange={(e) => setEditing({ ...editing, draft: { ...editing.draft, name: e.target.value } })}
                  required
                />
              </Field>
              <Field label={t(locale, "hoursWeeklyHours")}>
                <input
                  className={inputClass}
                  type="number"
                  min={1}
                  step={0.5}
                  value={editing.draft.weekly_hours_at_100}
                  onChange={(e) =>
                    setEditing({ ...editing, draft: { ...editing.draft, weekly_hours_at_100: Number(e.target.value) } })
                  }
                />
              </Field>
              <Field label={t(locale, "hoursVacationDaysAt100")}>
                <input
                  className={inputClass}
                  type="number"
                  min={0}
                  step={0.5}
                  value={editing.draft.vacation_days_at_100}
                  onChange={(e) =>
                    setEditing({ ...editing, draft: { ...editing.draft, vacation_days_at_100: Number(e.target.value) } })
                  }
                />
              </Field>
              <label className="inline-flex items-center gap-2 text-sm font-semibold text-slate-700">
                <input
                  type="checkbox"
                  checked={editing.draft.is_active}
                  onChange={(e) => setEditing({ ...editing, draft: { ...editing.draft, is_active: e.target.checked } })}
                />
                {t(locale, "isActive")}
              </label>
            </div>
            <div className="mt-5">
              <p className="text-sm font-semibold text-ink">{t(locale, "hoursRegularWeek")}</p>
              <p className="mt-1 text-xs text-slate-500">{t(locale, "hoursPatternEmpty")}</p>
              <div className="mt-2 grid gap-2">
                {editing.draft.regular_week_pattern.map((item, index) => (
                  <div key={`${item.weekday}-${index}`} className="grid grid-cols-[5rem_1fr_1fr_auto] items-center gap-2">
                    <span className="text-sm">{t(locale, weekdayKey[item.weekday])}</span>
                    <input
                      className={inputClass}
                      type="time"
                      value={item.starts_at}
                      onChange={(e) => {
                        const next = [...editing.draft.regular_week_pattern];
                        next[index] = { ...item, starts_at: e.target.value };
                        setEditing({ ...editing, draft: { ...editing.draft, regular_week_pattern: next } });
                      }}
                    />
                    <input
                      className={inputClass}
                      type="time"
                      value={item.ends_at}
                      onChange={(e) => {
                        const next = [...editing.draft.regular_week_pattern];
                        next[index] = { ...item, ends_at: e.target.value };
                        setEditing({ ...editing, draft: { ...editing.draft, regular_week_pattern: next } });
                      }}
                    />
                    <button
                      type="button"
                      className="text-rose-700"
                      onClick={() =>
                        setEditing({
                          ...editing,
                          draft: {
                            ...editing.draft,
                            regular_week_pattern: editing.draft.regular_week_pattern.filter((_, i) => i !== index)
                          }
                        })
                      }
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
                <select
                  className={inputClass}
                  value=""
                  onChange={(e) => {
                    const weekday = e.target.value as Weekday;
                    if (!weekday) {
                      return;
                    }
                    setEditing({
                      ...editing,
                      draft: {
                        ...editing.draft,
                        regular_week_pattern: [
                          ...editing.draft.regular_week_pattern,
                          { weekday, starts_at: "08:00", ends_at: "16:00" }
                        ]
                      }
                    });
                  }}
                >
                  <option value="">{t(locale, "hoursAddWeekday")}</option>
                  {WEEKDAYS.filter((day) => !editing.draft.regular_week_pattern.some((item) => item.weekday === day)).map(
                    (day) => (
                      <option key={day} value={day}>
                        {t(locale, weekdayKey[day])}
                      </option>
                    )
                  )}
                </select>
              </div>
            </div>
            <div className="mt-5">
              <p className="text-sm font-semibold text-ink">{t(locale, "hoursCategoryRules")}</p>
              <div className="mt-2 grid gap-2">
                {editing.draft.category_rules.map((rule, index) => (
                  <div key={rule.category} className="flex flex-wrap items-center gap-2 rounded-lg bg-slate-50 p-2 text-sm">
                    <span className="min-w-40 font-medium">{t(locale, categoryKey[rule.category])}</span>
                    <label className="inline-flex items-center gap-1">
                      <input
                        type="checkbox"
                        checked={rule.counts_toward_contract}
                        onChange={(e) => {
                          const next = [...editing.draft.category_rules];
                          next[index] = { ...rule, counts_toward_contract: e.target.checked };
                          setEditing({ ...editing, draft: { ...editing.draft, category_rules: next } });
                        }}
                      />
                      {t(locale, "hoursCountsTowardContract")}
                    </label>
                    <select
                      className={inputClass}
                      value={rule.credit_mode}
                      onChange={(e) => {
                        const next = [...editing.draft.category_rules];
                        next[index] = { ...rule, credit_mode: e.target.value as "duration" | "none" };
                        setEditing({ ...editing, draft: { ...editing.draft, category_rules: next } });
                      }}
                    >
                      <option value="duration">{t(locale, "hoursCreditDuration")}</option>
                      <option value="none">{t(locale, "hoursCreditNone")}</option>
                    </select>
                  </div>
                ))}
              </div>
            </div>
            <div className="mt-5">
              <p className="text-sm font-semibold text-ink">{t(locale, "hoursStatusMappings")}</p>
              <div className="mt-2 grid gap-2">
                {editing.draft.status_mappings.map((row, index) => (
                  <div key={row.code} className="grid gap-2 rounded-lg bg-slate-50 p-2 sm:grid-cols-2">
                    <span className="font-mono text-sm">{row.code}</span>
                    <select
                      className={inputClass}
                      value={row.absence_kind}
                      onChange={(e) => {
                        const next = [...editing.draft.status_mappings];
                        next[index] = { ...row, absence_kind: e.target.value as WorkerGroupStatusMapping["absence_kind"] };
                        setEditing({ ...editing, draft: { ...editing.draft, status_mappings: next } });
                      }}
                    >
                      <option value="vacation">{t(locale, "hoursAbsenceVacation")}</option>
                      <option value="sick">{t(locale, "hoursAbsenceSick")}</option>
                      <option value="other">{t(locale, "hoursAbsenceOther")}</option>
                      <option value="none">{t(locale, "hoursAbsenceNone")}</option>
                    </select>
                    <label className="inline-flex items-center gap-1 text-sm">
                      <input
                        type="checkbox"
                        checked={row.consumes_vacation}
                        onChange={(e) => {
                          const next = [...editing.draft.status_mappings];
                          next[index] = { ...row, consumes_vacation: e.target.checked };
                          setEditing({ ...editing, draft: { ...editing.draft, status_mappings: next } });
                        }}
                      />
                      {t(locale, "hoursConsumesVacation")}
                    </label>
                    <label className="inline-flex items-center gap-1 text-sm">
                      <input
                        type="checkbox"
                        checked={row.counts_as_work_day}
                        onChange={(e) => {
                          const next = [...editing.draft.status_mappings];
                          next[index] = { ...row, counts_as_work_day: e.target.checked };
                          setEditing({ ...editing, draft: { ...editing.draft, status_mappings: next } });
                        }}
                      />
                      {t(locale, "hoursCountsAsWorkDay")}
                    </label>
                  </div>
                ))}
              </div>
            </div>
            <div className="mt-5 flex justify-end">
              <button className="h-10 rounded-lg bg-ink px-4 text-sm font-semibold text-white" type="submit">
                {t(locale, "save")}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}
