"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Pencil, Plus, Trash2, X } from "lucide-react";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";
import { ApiError, apiFetch } from "@/lib/api";
import { t } from "@/lib/i18n";

type CreditMode = "duration" | "factor" | "none";
type Category = "bereitschaftsdienst" | "rufdienst" | "spaetdienst" | "other";

export type ContractCategoryRule = {
  category: Category;
  counts_toward_contract: boolean;
  credit_mode: CreditMode;
  credit_factor: number | string | null;
  holiday_credit_bonus: number | string;
  statutory_factor: number | string;
  call_outs_count_as_work: boolean;
};

export type ContractStatusMapping = {
  code: string;
  absence_kind: "vacation" | "sick" | "other" | "none";
  consumes_vacation: boolean;
  counts_as_work_day: boolean;
};

export type RegularWeekPatternDay = {
  weekday: string;
  start: string;
  end: string;
};

export type ContractGroup = {
  id: number;
  name: string;
  display_order: number;
  is_active: boolean;
  weekly_hours_at_100: number | string;
  vacation_days_at_100: number | string;
  regular_week_pattern: RegularWeekPatternDay[];
  category_rules: ContractCategoryRule[];
  status_mappings: ContractStatusMapping[];
};

const CATEGORIES: Category[] = ["bereitschaftsdienst", "rufdienst", "spaetdienst", "other"];

function defaultRules(): ContractCategoryRule[] {
  return [
    {
      category: "bereitschaftsdienst",
      counts_toward_contract: true,
      credit_mode: "factor",
      credit_factor: 0.6,
      holiday_credit_bonus: 25,
      statutory_factor: 1,
      call_outs_count_as_work: false
    },
    {
      category: "rufdienst",
      counts_toward_contract: false,
      credit_mode: "none",
      credit_factor: null,
      holiday_credit_bonus: 0,
      statutory_factor: 1,
      call_outs_count_as_work: true
    },
    {
      category: "spaetdienst",
      counts_toward_contract: true,
      credit_mode: "duration",
      credit_factor: null,
      holiday_credit_bonus: 0,
      statutory_factor: 1,
      call_outs_count_as_work: false
    },
    {
      category: "other",
      counts_toward_contract: true,
      credit_mode: "duration",
      credit_factor: null,
      holiday_credit_bonus: 0,
      statutory_factor: 1,
      call_outs_count_as_work: false
    }
  ];
}

function defaultMappings(): ContractStatusMapping[] {
  return [
    { code: "urlaub", absence_kind: "vacation", consumes_vacation: true, counts_as_work_day: false },
    { code: "forschung", absence_kind: "other", consumes_vacation: false, counts_as_work_day: true },
    { code: "lehre", absence_kind: "other", consumes_vacation: false, counts_as_work_day: true },
    { code: "frei", absence_kind: "none", consumes_vacation: false, counts_as_work_day: false }
  ];
}

function defaultWeek(): RegularWeekPatternDay[] {
  return ["mon", "tue", "wed", "thu", "fri"].map((weekday) => ({
    weekday,
    start: "08:00:00",
    end: "16:30:00"
  }));
}

type Draft = {
  name: string;
  weekly_hours_at_100: string;
  vacation_days_at_100: string;
  is_active: boolean;
  category_rules: ContractCategoryRule[];
  status_mappings: ContractStatusMapping[];
  regular_week_pattern: RegularWeekPatternDay[];
};

function emptyDraft(): Draft {
  return {
    name: "",
    weekly_hours_at_100: "40",
    vacation_days_at_100: "30",
    is_active: true,
    category_rules: defaultRules(),
    status_mappings: defaultMappings(),
    regular_week_pattern: defaultWeek()
  };
}

function fromGroup(group: ContractGroup): Draft {
  return {
    name: group.name,
    weekly_hours_at_100: String(group.weekly_hours_at_100),
    vacation_days_at_100: String(group.vacation_days_at_100),
    is_active: group.is_active,
    category_rules: group.category_rules.length ? group.category_rules : defaultRules(),
    status_mappings: group.status_mappings.length ? group.status_mappings : defaultMappings(),
    regular_week_pattern: group.regular_week_pattern.length ? group.regular_week_pattern : defaultWeek()
  };
}

function payloadFromDraft(draft: Draft) {
  return {
    name: draft.name.trim(),
    weekly_hours_at_100: Number(draft.weekly_hours_at_100),
    vacation_days_at_100: Number(draft.vacation_days_at_100),
    is_active: draft.is_active,
    regular_week_pattern: draft.regular_week_pattern,
    category_rules: draft.category_rules.map((rule) => ({
      ...rule,
      credit_factor: rule.credit_mode === "factor" ? Number(rule.credit_factor) : null,
      holiday_credit_bonus: Number(rule.holiday_credit_bonus),
      statutory_factor: Number(rule.statutory_factor)
    })),
    status_mappings: draft.status_mappings
  };
}

function ContractGroupModal({
  initial,
  groupId,
  onClose,
  onSaved
}: {
  initial: Draft;
  groupId: number | null;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const { locale } = useLocale();
  const [draft, setDraft] = useState<Draft>(initial);
  const [message, setMessage] = useState("");
  const isCreate = groupId === null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    try {
      if (isCreate) {
        await apiFetch("/api/v1/contract-groups", { method: "POST", body: JSON.stringify(payloadFromDraft(draft)) });
      } else {
        await apiFetch(`/api/v1/contract-groups/${groupId}`, {
          method: "PATCH",
          body: JSON.stringify(payloadFromDraft(draft))
        });
      }
      await onSaved();
      onClose();
    } catch (e) {
      if (e instanceof ApiError && typeof e.detail === "string") {
        setMessage(e.detail);
      } else {
        setMessage(t(locale, "contractGroupSaveError"));
      }
    }
  }

  function updateRule(category: Category, patch: Partial<ContractCategoryRule>) {
    setDraft((prev) => ({
      ...prev,
      category_rules: prev.category_rules.map((rule) => (rule.category === category ? { ...rule, ...patch } : rule))
    }));
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 px-3 py-6 backdrop-blur-sm">
      <div className="max-h-[92vh] w-full max-w-3xl overflow-y-auto rounded-xl bg-white p-5 shadow-soft ring-1 ring-slate-200">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-ink">
            {isCreate ? t(locale, "contractGroupAdd") : t(locale, "contractGroupEdit")}
          </h2>
          <button type="button" className="rounded-lg p-2 text-slate-600 hover:bg-slate-100" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <form className="grid gap-4" onSubmit={(event) => void submit(event)}>
          <Field label={t(locale, "name")}>
            <input
              className={inputClass}
              required
              value={draft.name}
              onChange={(event) => setDraft((prev) => ({ ...prev, name: event.target.value }))}
            />
          </Field>
          <div className="grid gap-3 md:grid-cols-2">
            <Field label={t(locale, "contractGroupWeeklyHours")}>
              <input
                className={inputClass}
                type="number"
                min={0}
                step="0.25"
                required
                value={draft.weekly_hours_at_100}
                onChange={(event) => setDraft((prev) => ({ ...prev, weekly_hours_at_100: event.target.value }))}
              />
            </Field>
            <Field label={t(locale, "contractGroupVacationDays")}>
              <input
                className={inputClass}
                type="number"
                min={0}
                step="0.5"
                required
                value={draft.vacation_days_at_100}
                onChange={(event) => setDraft((prev) => ({ ...prev, vacation_days_at_100: event.target.value }))}
              />
            </Field>
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={draft.is_active}
              onChange={(event) => setDraft((prev) => ({ ...prev, is_active: event.target.checked }))}
            />
            {t(locale, "isActive")}
          </label>
          <div>
            <p className="mb-2 text-sm font-semibold text-slate-800">{t(locale, "contractCategoryRules")}</p>
            <div className="grid gap-3">
              {CATEGORIES.map((category) => {
                const rule = draft.category_rules.find((item) => item.category === category) ?? defaultRules().find((item) => item.category === category)!;
                return (
                  <div key={category} className="rounded-lg border border-slate-200 p-3">
                    <p className="mb-2 text-sm font-medium text-ink">{category}</p>
                    <div className="grid gap-2 md:grid-cols-2">
                      <Field label={t(locale, "contractCreditMode")}>
                        <select
                          className={inputClass}
                          value={rule.credit_mode}
                          onChange={(event) =>
                            updateRule(category, {
                              credit_mode: event.target.value as CreditMode,
                              credit_factor: event.target.value === "factor" ? Number(rule.credit_factor ?? 0.6) : null
                            })
                          }
                        >
                          <option value="duration">duration</option>
                          <option value="factor">factor</option>
                          <option value="none">none</option>
                        </select>
                      </Field>
                      <Field label={t(locale, "contractCreditFactor")}>
                        <input
                          className={inputClass}
                          type="number"
                          min={0}
                          max={1}
                          step="0.05"
                          disabled={rule.credit_mode !== "factor"}
                          value={rule.credit_factor ?? ""}
                          onChange={(event) => updateRule(category, { credit_factor: event.target.value })}
                        />
                      </Field>
                      <Field label={t(locale, "contractHolidayBonus")}>
                        <input
                          className={inputClass}
                          type="number"
                          min={0}
                          max={100}
                          step="1"
                          value={rule.holiday_credit_bonus}
                          onChange={(event) => updateRule(category, { holiday_credit_bonus: event.target.value })}
                        />
                      </Field>
                      <Field label={t(locale, "contractStatutoryFactor")} hint={t(locale, "contractStatutoryFactorHelp")}>
                        <input
                          className={inputClass}
                          type="number"
                          min={0}
                          max={1}
                          step="0.05"
                          value={rule.statutory_factor}
                          onChange={(event) => updateRule(category, { statutory_factor: event.target.value })}
                        />
                      </Field>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-4 text-sm">
                      <label className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={rule.counts_toward_contract}
                          onChange={(event) => updateRule(category, { counts_toward_contract: event.target.checked })}
                        />
                        {t(locale, "contractCountsToward")}
                      </label>
                      <label className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={rule.call_outs_count_as_work}
                          onChange={(event) => updateRule(category, { call_outs_count_as_work: event.target.checked })}
                        />
                        {t(locale, "contractCallOuts")}
                      </label>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          {message ? <p className="text-sm text-rose-700">{message}</p> : null}
          <div className="flex justify-end gap-2">
            <button type="button" className="rounded-lg border border-slate-200 px-4 py-2 text-sm" onClick={onClose}>
              {t(locale, "close")}
            </button>
            <button type="submit" className="rounded-lg bg-ink px-4 py-2 text-sm font-semibold text-white">
              {t(locale, "save")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export function ContractGroupsPanel() {
  const { locale } = useLocale();
  const [groups, setGroups] = useState<ContractGroup[]>([]);
  const [modal, setModal] = useState<{ draft: Draft; id: number | null } | null>(null);
  const [message, setMessage] = useState("");

  const reload = useCallback(async () => {
    const rows = await apiFetch<ContractGroup[]>("/api/v1/contract-groups");
    setGroups(rows);
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function remove(id: number) {
    setMessage("");
    try {
      await apiFetch(`/api/v1/contract-groups/${id}`, { method: "DELETE" });
      await reload();
    } catch (e) {
      if (e instanceof ApiError && typeof e.detail === "string") {
        setMessage(e.detail);
      } else {
        setMessage(t(locale, "contractGroupSaveError"));
      }
    }
  }

  return (
    <Card>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-ink">{t(locale, "contractGroupsTitle")}</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-600">{t(locale, "contractGroupsHelp")}</p>
        </div>
        <button
          type="button"
          className="inline-flex h-10 items-center gap-2 rounded-lg bg-ink px-3 text-sm font-semibold text-white"
          onClick={() => setModal({ draft: emptyDraft(), id: null })}
        >
          <Plus size={16} />
          {t(locale, "contractGroupAdd")}
        </button>
      </div>
      {message ? <p className="mb-3 text-sm text-rose-700">{message}</p> : null}
      <ul className="grid gap-2">
        {groups.map((group) => (
          <li key={group.id} className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2">
            <div>
              <p className="font-medium text-ink">{group.name}</p>
              <p className="text-xs text-slate-500">
                {group.weekly_hours_at_100} h · {group.vacation_days_at_100} d
              </p>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                className="rounded-lg border border-slate-200 p-2"
                onClick={() => setModal({ draft: fromGroup(group), id: group.id })}
                aria-label={t(locale, "contractGroupEdit")}
              >
                <Pencil size={16} />
              </button>
              <button
                type="button"
                className="rounded-lg border border-rose-200 p-2 text-rose-700"
                onClick={() => void remove(group.id)}
                aria-label={t(locale, "contractGroupDelete")}
              >
                <Trash2 size={16} />
              </button>
            </div>
          </li>
        ))}
      </ul>
      {modal ? (
        <ContractGroupModal
          initial={modal.draft}
          groupId={modal.id}
          onClose={() => setModal(null)}
          onSaved={reload}
        />
      ) : null}
    </Card>
  );
}
