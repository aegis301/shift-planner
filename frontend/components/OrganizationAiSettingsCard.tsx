"use client";

import { FormEvent, useEffect, useState } from "react";
import { Bot } from "lucide-react";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";
import { ApiError, apiFetch } from "@/lib/api";
import { t } from "@/lib/i18n";

type AiSettings = {
  provider: "anthropic" | "openai" | string;
  default_model: string;
  enabled_task_ids: string[];
  monthly_token_budget: number | null;
  is_enabled: boolean;
  has_api_key: boolean;
  assistant_ready: boolean;
  key_last4?: string | null;
};

const TASK_IDS = ["summarize_wishes", "explain_validation", "draft_fair_roster"] as const;
const TASK_LABELS: Record<(typeof TASK_IDS)[number], "aiTaskSummarizeWishes" | "aiTaskExplainValidation" | "aiTaskDraftFairRoster"> = {
  summarize_wishes: "aiTaskSummarizeWishes",
  explain_validation: "aiTaskExplainValidation",
  draft_fair_roster: "aiTaskDraftFairRoster",
};
const ANTHROPIC_MODELS = ["claude-sonnet-4-5", "claude-haiku-4-5", "claude-3-5-haiku-latest", "claude-3-5-sonnet-latest"];
const OPENAI_MODELS = ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini", "gpt-4o"];

export function OrganizationAiSettingsCard() {
  const { locale } = useLocale();
  const [settings, setSettings] = useState<AiSettings | null>(null);
  const [provider, setProvider] = useState("anthropic");
  const [model, setModel] = useState("claude-sonnet-4-5");
  const [apiKey, setApiKey] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [tasks, setTasks] = useState<string[]>([...TASK_IDS]);
  const [budget, setBudget] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiFetch<AiSettings>("/api/v1/organization/ai-settings")
      .then((row) => {
        if (cancelled) return;
        setSettings(row);
        setProvider(row.provider);
        setModel(row.default_model);
        setEnabled(row.is_enabled);
        setTasks(row.enabled_task_ids?.length ? row.enabled_task_ids : [...TASK_IDS]);
        setBudget(row.monthly_token_budget != null ? String(row.monthly_token_budget) : "");
      })
      .catch(() => {
        if (!cancelled) setMsg(t(locale, "aiSettingsLoadError"));
      });
    return () => {
      cancelled = true;
    };
  }, [locale]);

  const models = provider === "openai" ? OPENAI_MODELS : ANTHROPIC_MODELS;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMsg("");
    try {
      const row = await apiFetch<AiSettings>("/api/v1/organization/ai-settings", {
        method: "PUT",
        body: JSON.stringify({
          provider,
          default_model: model,
          enabled_task_ids: tasks,
          is_enabled: enabled,
            monthly_token_budget: budget.trim() ? Number(budget) : null,
          api_key: apiKey.trim() || null,
        }),
      });
      setSettings(row);
      setApiKey("");
      setMsg(t(locale, "aiSettingsSaved"));
    } catch (err) {
      setMsg(err instanceof ApiError && typeof err.detail === "string" ? err.detail : t(locale, "aiSettingsSaveError"));
    } finally {
      setBusy(false);
    }
  }

  function toggleTask(id: string) {
    setTasks((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]));
  }

  return (
    <Card>
      <div className="flex items-start gap-3">
        <Bot className="mt-0.5 shrink-0 text-emerald-700" aria-hidden />
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-semibold text-ink">{t(locale, "aiSettingsTitle")}</h2>
          <p className="mt-1 text-sm text-slate-600">{t(locale, "aiSettingsHelp")}</p>
          {settings?.has_api_key ? (
            <p className="mt-2 text-sm text-slate-700">
              {t(locale, "aiSettingsKeyOnFile", { last4: settings.key_last4 || "****" })}
            </p>
          ) : (
            <p className="mt-2 text-sm text-amber-800">{t(locale, "aiSettingsNoKey")}</p>
          )}
          <form className="mt-4 grid gap-3" onSubmit={onSubmit}>
            <label className="inline-flex items-center gap-2 text-sm text-slate-800">
              <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
              {t(locale, "aiSettingsEnabled")}
            </label>
            <Field label={t(locale, "aiSettingsProvider")}>
              <select
                className={inputClass}
                value={provider}
                onChange={(event) => {
                  const next = event.target.value;
                  setProvider(next);
                  setModel(next === "openai" ? OPENAI_MODELS[0] : ANTHROPIC_MODELS[0]);
                }}
              >
                <option value="anthropic">Anthropic</option>
                <option value="openai">OpenAI</option>
              </select>
            </Field>
            <Field label={t(locale, "aiSettingsModel")}>
              <select className={inputClass} value={model} onChange={(event) => setModel(event.target.value)}>
                {models.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </Field>
            <Field label={t(locale, "aiSettingsApiKey")}>
              <input
                className={inputClass}
                type="password"
                autoComplete="off"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder={settings?.has_api_key ? "••••" : ""}
              />
            </Field>
            <Field label={t(locale, "aiSettingsBudget")}>
              <input
                className={inputClass}
                type="number"
                min={0}
                value={budget}
                onChange={(event) => setBudget(event.target.value)}
              />
            </Field>
            <fieldset className="grid gap-2">
              <legend className="text-sm font-medium text-slate-800">{t(locale, "aiSettingsTasks")}</legend>
              {TASK_IDS.map((id) => (
                <label key={id} className="inline-flex items-center gap-2 text-sm text-slate-800">
                  <input type="checkbox" checked={tasks.includes(id)} onChange={() => toggleTask(id)} />
                  {t(locale, TASK_LABELS[id])}
                </label>
              ))}
            </fieldset>
            {msg ? <p className="text-sm text-slate-700">{msg}</p> : null}
            <button
              type="submit"
              disabled={busy}
              className="h-11 max-w-xs rounded-lg bg-emerald-700 px-4 text-sm font-semibold text-white disabled:opacity-40"
            >
              {t(locale, "save")}
            </button>
          </form>
        </div>
      </div>
    </Card>
  );
}
