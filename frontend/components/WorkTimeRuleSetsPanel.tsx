"use client";

import { FormEvent, useEffect, useState } from "react";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";
import { apiFetch } from "@/lib/api";
import { t, type TranslationKey } from "@/lib/i18n";

type Severity = "info" | "warning" | "error";
type RuleType =
  | "max_daily_working_time"
  | "min_rest_period"
  | "rest_after_long_duty"
  | "weekly_average_cap"
  | "opt_out_weekly_cap"
  | "max_consecutive_work_days"
  | "max_duties_per_period"
  | "documentation_requirement"
  | "duty_utilization_bands";

type WorkTimeRule = {
  type: RuleType;
  severity: Severity;
  source_note: string;
  base_hours?: number;
  extended_hours?: number;
  extension_requires_duty_hours?: number;
  hours?: number;
  reducible_to_hours?: number | null;
  compensation_window_days?: number;
  call_out_handling?: "interrupt" | "restart" | "ignore";
  trigger_hours?: number;
  mandatory_rest_hours?: number;
  reference_period_months?: number;
  rolling?: boolean;
  hours_by_tier?: Record<string, number>;
  days?: number;
  count?: number;
  period?: "week" | "month" | "quarter" | "year";
  additional_allowance_per_quarter?: number;
  threshold_hours?: number;
  retention_months?: number;
  stufe_i_max_percent?: number;
  on_call_max_percent?: number;
};

type WorkTimeRuleSet = {
  id: number;
  name: string;
  version: number;
  is_active: boolean;
  rules: WorkTimeRule[];
};

type WorkTimePreset = {
  id: number;
  code: string;
  name: string;
  values_confirmed: boolean;
  rules: WorkTimeRule[];
};

const RULE_TYPES: RuleType[] = [
  "max_daily_working_time",
  "min_rest_period",
  "rest_after_long_duty",
  "weekly_average_cap",
  "opt_out_weekly_cap",
  "max_consecutive_work_days",
  "max_duties_per_period",
  "documentation_requirement",
  "duty_utilization_bands"
];

const RULE_TYPE_KEYS: Record<RuleType, TranslationKey> = {
  max_daily_working_time: "workTimeRuleMaxDaily",
  min_rest_period: "workTimeRuleMinRest",
  rest_after_long_duty: "workTimeRuleRestAfterLong",
  weekly_average_cap: "workTimeRuleWeeklyAvg",
  opt_out_weekly_cap: "workTimeRuleOptOut",
  max_consecutive_work_days: "workTimeRuleMaxConsecutive",
  max_duties_per_period: "workTimeRuleMaxDuties",
  documentation_requirement: "workTimeRuleDocumentation",
  duty_utilization_bands: "workTimeRuleDutyUtilization"
};

function hoursByTierText(hoursByTier: Record<string, number> | undefined): string {
  return Object.entries(hoursByTier ?? {})
    .map(([tier, hours]) => `${tier}=${hours}`)
    .join("\n");
}

function parseHoursByTier(value: string): Record<string, number> {
  const parsed: Record<string, number> = {};
  for (const line of value.split(/[\n,]+/)) {
    const [tier, hours] = line.split("=").map((part) => part.trim());
    if (!tier || !hours) continue;
    const numeric = Number(hours);
    if (!Number.isFinite(numeric)) continue;
    parsed[tier] = numeric;
  }
  return parsed;
}

function emptyRule(type: RuleType): WorkTimeRule {
  const base = { type, severity: "warning" as Severity, source_note: "" };
  if (type === "max_daily_working_time") {
    return { ...base, severity: "error", base_hours: 8, extended_hours: 10, extension_requires_duty_hours: 3 };
  }
  if (type === "min_rest_period") {
    return { ...base, severity: "error", hours: 11, reducible_to_hours: 9, compensation_window_days: 14, call_out_handling: "interrupt" };
  }
  if (type === "rest_after_long_duty") {
    return { ...base, severity: "error", trigger_hours: 12, mandatory_rest_hours: 24 };
  }
  if (type === "weekly_average_cap") {
    return { ...base, hours: 48, reference_period_months: 6, rolling: true };
  }
  if (type === "opt_out_weekly_cap") {
    return { ...base, hours_by_tier: { standard: 48, opt_out: 54 }, reference_period_months: 6 };
  }
  if (type === "max_consecutive_work_days") {
    return { ...base, days: 6 };
  }
  if (type === "max_duties_per_period") {
    return { ...base, count: 4, period: "month", additional_allowance_per_quarter: 1 };
  }
  if (type === "duty_utilization_bands") {
    return { ...base, severity: "info", stufe_i_max_percent: 25, on_call_max_percent: 49 };
  }
  return { ...base, severity: "info", threshold_hours: 8, retention_months: 24 };
}

export function WorkTimeRuleSetsPanel() {
  const { locale } = useLocale();
  const [rows, setRows] = useState<WorkTimeRuleSet[]>([]);
  const [presets, setPresets] = useState<WorkTimePreset[]>([]);
  const [name, setName] = useState("");
  const [rules, setRules] = useState<WorkTimeRule[]>([emptyRule("max_consecutive_work_days")]);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const [ruleSets, presetRows] = await Promise.all([
        apiFetch<WorkTimeRuleSet[]>("/api/v1/work-time-rule-sets"),
        apiFetch<WorkTimePreset[]>("/api/v1/work-time-rule-sets/presets")
      ]);
      setRows(ruleSets);
      setPresets(presetRows);
      setError(false);
    } catch {
      setError(true);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  function resetForm() {
    setEditingId(null);
    setName("");
    setRules([emptyRule("max_consecutive_work_days")]);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      if (editingId == null) {
        await apiFetch("/api/v1/work-time-rule-sets", {
          method: "POST",
          body: JSON.stringify({ name, rules })
        });
      } else {
        await apiFetch(`/api/v1/work-time-rule-sets/${editingId}`, {
          method: "PATCH",
          body: JSON.stringify({ name, rules })
        });
      }
      resetForm();
      await load();
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  async function adoptPreset(code: string) {
    setBusy(true);
    try {
      await apiFetch(`/api/v1/work-time-rule-sets/presets/${code}/adopt`, {
        method: "POST",
        body: JSON.stringify({})
      });
      resetForm();
      await load();
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  async function activate(id: number) {
    setBusy(true);
    try {
      await apiFetch(`/api/v1/work-time-rule-sets/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: true })
      });
      await load();
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  function startEdit(row: WorkTimeRuleSet) {
    setEditingId(row.id);
    setName(row.name);
    setRules(row.rules.length ? row.rules : [emptyRule("max_consecutive_work_days")]);
  }

  return (
    <div className="grid gap-4">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">{t(locale, "workTimeRuleSetsNav")}</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-600">{t(locale, "workTimeRuleSetsHelp")}</p>
      </div>
      {error ? <p className="text-sm text-red-600">{t(locale, "apiUnavailable")}</p> : null}
      <Card>
        <h2 className="text-lg font-semibold text-slate-900">{t(locale, "workTimePresetsTitle")}</h2>
        <p className="mt-2 text-sm text-slate-600">{t(locale, "workTimePresetDisclaimer")}</p>
        <div className="mt-3 grid gap-3">
          {presets.map((preset) => (
            <div key={preset.code} className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-slate-200 p-3">
              <div>
                <p className="font-semibold text-slate-900">
                  {preset.name}
                  {preset.values_confirmed ? "" : ` · ${t(locale, "workTimePresetUnconfirmed")}`}
                </p>
                <ul className="mt-2 list-disc pl-5 text-sm text-slate-600">
                  {preset.rules.map((rule, index) => (
                    <li key={`${preset.code}-${index}`}>
                      {t(locale, RULE_TYPE_KEYS[rule.type])}
                      {rule.source_note ? ` — ${rule.source_note}` : ""}
                    </li>
                  ))}
                </ul>
              </div>
              <button
                type="button"
                className="inline-flex h-10 items-center rounded-lg bg-ink px-3 text-sm font-semibold text-white disabled:opacity-60"
                disabled={busy}
                onClick={() => void adoptPreset(preset.code)}
              >
                {t(locale, "workTimePresetAdopt")}
              </button>
            </div>
          ))}
        </div>
      </Card>
      <Card>
        <form className="grid gap-3" onSubmit={(event) => void onSubmit(event)}>
          <Field label={t(locale, "workTimeRuleSetName")}>
            <input className={inputClass} value={name} onChange={(event) => setName(event.target.value)} required />
          </Field>
          <div className="grid gap-3">
            {rules.map((rule, index) => {
              const update = (patch: Partial<WorkTimeRule>) => {
                const next = [...rules];
                next[index] = { ...rule, ...patch };
                setRules(next);
              };
              return (
              <div key={`${rule.type}-${index}`} className="grid gap-2 rounded-lg border border-slate-200 p-3">
                <div className="grid gap-2 sm:grid-cols-3">
                  <Field label={t(locale, "workTimeRuleType")}>
                    <select
                      className={inputClass}
                      value={rule.type}
                      onChange={(event) => {
                        const next = [...rules];
                        next[index] = emptyRule(event.target.value as RuleType);
                        setRules(next);
                      }}
                    >
                      {RULE_TYPES.map((type) => (
                        <option key={type} value={type}>
                          {t(locale, RULE_TYPE_KEYS[type])}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label={t(locale, "workTimeRuleSeverity")}>
                    <select
                      className={inputClass}
                      value={rule.severity}
                      onChange={(event) => update({ severity: event.target.value as Severity })}
                    >
                      <option value="info">info</option>
                      <option value="warning">warning</option>
                      <option value="error">error</option>
                    </select>
                  </Field>
                  <Field label={t(locale, "workTimeRuleSourceNote")}>
                    <input
                      className={inputClass}
                      value={rule.source_note}
                      onChange={(event) => update({ source_note: event.target.value })}
                    />
                  </Field>
                </div>
                {rule.type === "max_consecutive_work_days" ? (
                  <Field label={t(locale, "workTimeRuleDays")}>
                    <input
                      className={inputClass}
                      type="number"
                      min={1}
                      value={rule.days ?? 6}
                      onChange={(event) => update({ days: Number(event.target.value) })}
                    />
                  </Field>
                ) : null}
                {rule.type === "max_daily_working_time" ? (
                  <div className="grid gap-2 sm:grid-cols-3">
                    <Field label={t(locale, "workTimeRuleBaseHours")}>
                      <input
                        className={inputClass}
                        type="number"
                        min={1}
                        step="0.25"
                        value={rule.base_hours ?? 8}
                        onChange={(event) => update({ base_hours: Number(event.target.value) })}
                      />
                    </Field>
                    <Field label={t(locale, "workTimeRuleExtendedHours")}>
                      <input
                        className={inputClass}
                        type="number"
                        min={1}
                        step="0.25"
                        value={rule.extended_hours ?? 10}
                        onChange={(event) => update({ extended_hours: Number(event.target.value) })}
                      />
                    </Field>
                    <Field label={t(locale, "workTimeRuleDutyHours")}>
                      <input
                        className={inputClass}
                        type="number"
                        min={0}
                        step="0.25"
                        value={rule.extension_requires_duty_hours ?? 3}
                        onChange={(event) => update({ extension_requires_duty_hours: Number(event.target.value) })}
                      />
                    </Field>
                  </div>
                ) : null}
                {rule.type === "min_rest_period" ? (
                  <div className="grid gap-2 sm:grid-cols-2">
                    <Field label={t(locale, "workTimeRuleHours")}>
                      <input
                        className={inputClass}
                        type="number"
                        min={1}
                        step="0.25"
                        value={rule.hours ?? 11}
                        onChange={(event) => update({ hours: Number(event.target.value) })}
                      />
                    </Field>
                    <Field label={t(locale, "workTimeRuleReducibleHours")}>
                      <input
                        className={inputClass}
                        type="number"
                        min={1}
                        step="0.25"
                        value={rule.reducible_to_hours ?? ""}
                        onChange={(event) =>
                          update({
                            reducible_to_hours: event.target.value === "" ? null : Number(event.target.value)
                          })
                        }
                      />
                    </Field>
                    <Field label={t(locale, "workTimeRuleCompensationDays")}>
                      <input
                        className={inputClass}
                        type="number"
                        min={1}
                        value={rule.compensation_window_days ?? 14}
                        onChange={(event) => update({ compensation_window_days: Number(event.target.value) })}
                      />
                    </Field>
                    <Field label={t(locale, "workTimeRuleCallOutHandling")}>
                      <select
                        className={inputClass}
                        value={rule.call_out_handling ?? "interrupt"}
                        onChange={(event) =>
                          update({ call_out_handling: event.target.value as WorkTimeRule["call_out_handling"] })
                        }
                      >
                        <option value="interrupt">{t(locale, "workTimeRuleCallOutInterrupt")}</option>
                        <option value="restart">{t(locale, "workTimeRuleCallOutRestart")}</option>
                        <option value="ignore">{t(locale, "workTimeRuleCallOutIgnore")}</option>
                      </select>
                    </Field>
                  </div>
                ) : null}
                {rule.type === "rest_after_long_duty" ? (
                  <div className="grid gap-2 sm:grid-cols-2">
                    <Field label={t(locale, "workTimeRuleTriggerHours")}>
                      <input
                        className={inputClass}
                        type="number"
                        min={1}
                        step="0.25"
                        value={rule.trigger_hours ?? 12}
                        onChange={(event) => update({ trigger_hours: Number(event.target.value) })}
                      />
                    </Field>
                    <Field label={t(locale, "workTimeRuleMandatoryRest")}>
                      <input
                        className={inputClass}
                        type="number"
                        min={1}
                        step="0.25"
                        value={rule.mandatory_rest_hours ?? 24}
                        onChange={(event) => update({ mandatory_rest_hours: Number(event.target.value) })}
                      />
                    </Field>
                  </div>
                ) : null}
                {rule.type === "weekly_average_cap" ? (
                  <div className="grid gap-2 sm:grid-cols-3">
                    <Field label={t(locale, "workTimeRuleHours")}>
                      <input
                        className={inputClass}
                        type="number"
                        min={1}
                        step="0.25"
                        value={rule.hours ?? 48}
                        onChange={(event) => update({ hours: Number(event.target.value) })}
                      />
                    </Field>
                    <Field label={t(locale, "workTimeRuleReferenceMonths")}>
                      <input
                        className={inputClass}
                        type="number"
                        min={1}
                        value={rule.reference_period_months ?? 6}
                        onChange={(event) => update({ reference_period_months: Number(event.target.value) })}
                      />
                    </Field>
                    <label className="flex items-center gap-2 text-sm text-slate-700">
                      <input
                        type="checkbox"
                        checked={rule.rolling !== false}
                        onChange={(event) => update({ rolling: event.target.checked })}
                      />
                      {t(locale, "workTimeRuleRolling")}
                    </label>
                  </div>
                ) : null}
                {rule.type === "opt_out_weekly_cap" ? (
                  <div className="grid gap-2 sm:grid-cols-2">
                    <Field label={t(locale, "workTimeRuleHoursByTier")}>
                      <textarea
                        className={inputClass}
                        rows={3}
                        value={hoursByTierText(rule.hours_by_tier)}
                        onChange={(event) => update({ hours_by_tier: parseHoursByTier(event.target.value) })}
                      />
                    </Field>
                    <Field label={t(locale, "workTimeRuleReferenceMonths")}>
                      <input
                        className={inputClass}
                        type="number"
                        min={1}
                        value={rule.reference_period_months ?? 6}
                        onChange={(event) => update({ reference_period_months: Number(event.target.value) })}
                      />
                    </Field>
                  </div>
                ) : null}
                {rule.type === "max_duties_per_period" ? (
                  <div className="grid gap-2 sm:grid-cols-3">
                    <Field label={t(locale, "workTimeRuleCount")}>
                      <input
                        className={inputClass}
                        type="number"
                        min={1}
                        value={rule.count ?? 4}
                        onChange={(event) => update({ count: Number(event.target.value) })}
                      />
                    </Field>
                    <Field label={t(locale, "workTimeRulePeriod")}>
                      <select
                        className={inputClass}
                        value={rule.period ?? "month"}
                        onChange={(event) => update({ period: event.target.value as WorkTimeRule["period"] })}
                      >
                        <option value="week">{t(locale, "workTimeRulePeriodWeek")}</option>
                        <option value="month">{t(locale, "workTimeRulePeriodMonth")}</option>
                        <option value="quarter">{t(locale, "workTimeRulePeriodQuarter")}</option>
                        <option value="year">{t(locale, "workTimeRulePeriodYear")}</option>
                      </select>
                    </Field>
                    <Field label={t(locale, "workTimeRuleAdditionalAllowance")}>
                      <input
                        className={inputClass}
                        type="number"
                        min={0}
                        value={rule.additional_allowance_per_quarter ?? 0}
                        onChange={(event) => update({ additional_allowance_per_quarter: Number(event.target.value) })}
                      />
                    </Field>
                  </div>
                ) : null}
                {rule.type === "documentation_requirement" ? (
                  <div className="grid gap-2 sm:grid-cols-2">
                    <Field label={t(locale, "workTimeRuleThresholdHours")}>
                      <input
                        className={inputClass}
                        type="number"
                        min={0}
                        step="0.25"
                        value={rule.threshold_hours ?? 8}
                        onChange={(event) => update({ threshold_hours: Number(event.target.value) })}
                      />
                    </Field>
                    <Field label={t(locale, "workTimeRuleRetentionMonths")}>
                      <input
                        className={inputClass}
                        type="number"
                        min={1}
                        value={rule.retention_months ?? 24}
                        onChange={(event) => update({ retention_months: Number(event.target.value) })}
                      />
                    </Field>
                  </div>
                ) : null}
                {rule.type === "duty_utilization_bands" ? (
                  <div className="grid gap-2 sm:grid-cols-2">
                    <Field label={t(locale, "workTimeRuleStufeIMaxPercent")}>
                      <input
                        className={inputClass}
                        type="number"
                        min={0}
                        max={100}
                        step="0.1"
                        value={rule.stufe_i_max_percent ?? 25}
                        onChange={(event) => update({ stufe_i_max_percent: Number(event.target.value) })}
                      />
                    </Field>
                    <Field label={t(locale, "workTimeRuleOnCallMaxPercent")}>
                      <input
                        className={inputClass}
                        type="number"
                        min={0}
                        max={100}
                        step="0.1"
                        value={rule.on_call_max_percent ?? 49}
                        onChange={(event) => update({ on_call_max_percent: Number(event.target.value) })}
                      />
                    </Field>
                  </div>
                ) : null}
                <button
                  type="button"
                  className="justify-self-start text-sm text-slate-600 underline"
                  onClick={() => setRules(rules.filter((_, ruleIndex) => ruleIndex !== index))}
                >
                  {t(locale, "workTimeRuleRemove")}
                </button>
              </div>
              );
            })}
          </div>
          <button
            type="button"
            className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 px-3 text-sm"
            onClick={() => setRules([...rules, emptyRule("max_consecutive_work_days")])}
          >
            {t(locale, "workTimeRuleAdd")}
          </button>
          <div className="flex flex-wrap gap-2">
            <button
              type="submit"
              className="inline-flex h-11 items-center justify-center rounded-lg bg-ink px-4 text-sm font-semibold text-white disabled:opacity-60"
              disabled={busy || !name.trim() || rules.length === 0}
            >
              {editingId == null ? t(locale, "workTimeRuleSetCreate") : t(locale, "save")}
            </button>
            {editingId != null ? (
              <button type="button" className="inline-flex h-11 items-center rounded-lg border border-slate-200 px-4 text-sm" onClick={resetForm}>
                {t(locale, "close")}
              </button>
            ) : null}
          </div>
        </form>
      </Card>
      <div className="grid gap-3">
        {rows.map((row) => (
          <Card key={row.id}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="font-semibold text-slate-900">
                  {row.name}{" "}
                  <span className="text-sm font-normal text-slate-500">
                    v{row.version}
                    {row.is_active ? ` · ${t(locale, "workTimeRuleSetActive")}` : ""}
                  </span>
                </p>
                <ul className="mt-2 list-disc pl-5 text-sm text-slate-600">
                  {row.rules.map((rule, index) => (
                    <li key={`${row.id}-${index}`}>
                      {t(locale, RULE_TYPE_KEYS[rule.type])}
                      {rule.source_note ? ` — ${rule.source_note}` : ""}
                    </li>
                  ))}
                </ul>
              </div>
              <div className="flex flex-wrap gap-2">
                <button type="button" className="inline-flex h-10 items-center rounded-lg border border-slate-200 px-3 text-sm" onClick={() => startEdit(row)}>
                  {t(locale, "workTimeRuleSetEdit")}
                </button>
                {!row.is_active ? (
                  <button
                    type="button"
                    className="inline-flex h-10 items-center rounded-lg bg-ink px-3 text-sm font-semibold text-white disabled:opacity-60"
                    disabled={busy}
                    onClick={() => void activate(row.id)}
                  >
                    {t(locale, "workTimeRuleSetActivate")}
                  </button>
                ) : null}
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
