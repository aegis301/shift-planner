"use client";

import { useEffect, useMemo, useState } from "react";
import { Bot } from "lucide-react";
import { Card } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";
import { ApiError, apiFetch } from "@/lib/api";
import { t, type TranslationKey } from "@/lib/i18n";

type AiSettings = {
  assistant_ready: boolean;
  is_enabled: boolean;
  enabled_task_ids: string[];
};

type AiRun = {
  id: number;
  task_id: string;
  status: string;
  output: Record<string, unknown> | null;
  error_message: string | null;
  applied_assignment_ids: number[];
};

type DraftProposal = {
  roster_slot_id: number;
  team_member_id: number;
  reason: string;
};

const TASKS: Array<{ id: "summarize_wishes" | "explain_validation" | "draft_fair_roster"; label: TranslationKey }> = [
  { id: "summarize_wishes", label: "aiTaskSummarizeWishes" },
  { id: "explain_validation", label: "aiTaskExplainValidation" },
  { id: "draft_fair_roster", label: "aiTaskDraftFairRoster" },
];

export function PlanningAiPanel({
  planningPeriodId,
  shiftGroupId,
  groupPublished,
  plannerPlanningEditable,
  onApplied,
}: {
  planningPeriodId: number | null;
  shiftGroupId: number | null;
  groupPublished: boolean;
  plannerPlanningEditable: boolean;
  onApplied?: () => void;
}) {
  const { locale } = useLocale();
  const [settings, setSettings] = useState<AiSettings | null>(null);
  const [busyTask, setBusyTask] = useState<string | null>(null);
  const [run, setRun] = useState<AiRun | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [msg, setMsg] = useState("");

  useEffect(() => {
    let cancelled = false;
    apiFetch<AiSettings>("/api/v1/ai/settings")
      .then((row) => {
        if (!cancelled) setSettings(row);
      })
      .catch(() => {
        if (!cancelled) setSettings(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const proposals = useMemo(() => {
    const raw = run?.output?.proposals;
    if (!Array.isArray(raw)) return [];
    return raw.filter((item): item is DraftProposal => {
      return (
        Boolean(item) &&
        typeof item === "object" &&
        typeof (item as DraftProposal).roster_slot_id === "number" &&
        typeof (item as DraftProposal).team_member_id === "number"
      );
    });
  }, [run]);

  const disabledReason: TranslationKey | null = !settings?.assistant_ready
    ? "aiAssistantNotConfigured"
    : !planningPeriodId
      ? "noPlanningPeriodSelected"
      : !shiftGroupId
        ? "selectPlanningShiftGroup"
        : null;

  async function runTask(taskId: (typeof TASKS)[number]["id"]) {
    if (!planningPeriodId || !shiftGroupId) return;
    if (taskId === "draft_fair_roster" && (groupPublished || !plannerPlanningEditable)) return;
    setBusyTask(taskId);
    setMsg("");
    try {
      const result = await apiFetch<AiRun>(`/api/v1/ai/tasks/${taskId}/runs`, {
        method: "POST",
        body: JSON.stringify({ planning_period_id: planningPeriodId, shift_group_id: shiftGroupId }),
      });
      setRun(result);
      setSelected(new Set());
    } catch (err) {
      setMsg(err instanceof ApiError && typeof err.detail === "string" ? err.detail : t(locale, "aiRunError"));
    } finally {
      setBusyTask(null);
    }
  }

  async function applySelected() {
    if (!run) return;
    const ids = [...selected];
    if (!ids.length) return;
    setBusyTask("apply");
    setMsg("");
    try {
      await apiFetch(`/api/v1/ai/runs/${run.id}/apply`, {
        method: "POST",
        body: JSON.stringify({ roster_slot_ids: ids }),
      });
      setMsg(t(locale, "aiApplyDone"));
      onApplied?.();
    } catch (err) {
      setMsg(err instanceof ApiError && typeof err.detail === "string" ? err.detail : t(locale, "aiApplyError"));
    } finally {
      setBusyTask(null);
    }
  }

  const summary = typeof run?.output?.summary === "string" ? run.output.summary : null;
  const gaps = Array.isArray(run?.output?.coverage_gaps) ? (run?.output?.coverage_gaps as string[]) : [];
  const clusters = Array.isArray(run?.output?.vacation_clusters) ? (run?.output?.vacation_clusters as string[]) : [];
  const conflicts = Array.isArray(run?.output?.conflicts) ? (run?.output?.conflicts as string[]) : [];
  const explanations = Array.isArray(run?.output?.explanations)
    ? (run?.output?.explanations as Array<{ code?: string; explanation?: string }>)
    : [];
  const fixes = Array.isArray(run?.output?.suggested_fixes) ? (run?.output?.suggested_fixes as string[]) : [];
  const notes = typeof run?.output?.notes === "string" ? run.output.notes : null;

  return (
    <Card>
      <div className="flex items-start gap-3">
        <Bot className="mt-0.5 shrink-0 text-emerald-700" aria-hidden />
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-semibold text-ink">{t(locale, "aiAssistantTitle")}</h2>
          <p className="mt-1 text-sm text-slate-600">{t(locale, "aiAssistantHelp")}</p>
          {disabledReason ? <p className="mt-2 text-sm text-amber-800">{t(locale, disabledReason)}</p> : null}
          <div className="mt-4 flex flex-wrap gap-2">
            {TASKS.map((task) => {
              const blocked =
                Boolean(disabledReason) ||
                Boolean(busyTask) ||
                (task.id === "draft_fair_roster" && (groupPublished || !plannerPlanningEditable)) ||
                Boolean(settings && !settings.enabled_task_ids.includes(task.id));
              return (
                <button
                  key={task.id}
                  type="button"
                  disabled={blocked}
                  className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-800 disabled:opacity-40"
                  onClick={() => void runTask(task.id)}
                >
                  {busyTask === task.id ? t(locale, "aiRunning") : t(locale, task.label)}
                </button>
              );
            })}
          </div>
          {msg ? <p className="mt-3 text-sm text-slate-700">{msg}</p> : null}
          {run?.status === "failed" && run.error_message ? (
            <p className="mt-3 text-sm text-red-700">{run.error_message}</p>
          ) : null}
          {summary ? <p className="mt-4 text-sm text-slate-800">{summary}</p> : null}
          {gaps.length ? (
            <ul className="mt-3 list-disc pl-5 text-sm text-slate-700">
              {gaps.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : null}
          {clusters.length ? (
            <ul className="mt-3 list-disc pl-5 text-sm text-slate-700">
              {clusters.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : null}
          {conflicts.length ? (
            <ul className="mt-3 list-disc pl-5 text-sm text-slate-700">
              {conflicts.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : null}
          {explanations.length ? (
            <div className="mt-4 grid gap-2">
              {explanations.map((item, index) => (
                <p key={`${item.code}-${index}`} className="text-sm text-slate-800">
                  {item.code ? <span className="font-medium">{item.code}: </span> : null}
                  {item.explanation}
                </p>
              ))}
            </div>
          ) : null}
          {fixes.length ? (
            <ul className="mt-3 list-disc pl-5 text-sm text-slate-700">
              {fixes.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : null}
          {notes ? <p className="mt-3 text-sm text-slate-700">{notes}</p> : null}
          {proposals.length ? (
            <div className="mt-4 grid gap-2">
              <p className="text-sm font-medium text-slate-800">{t(locale, "aiDraftProposals")}</p>
              {proposals.map((item) => (
                <label key={item.roster_slot_id} className="flex items-start gap-2 text-sm text-slate-800">
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={selected.has(item.roster_slot_id)}
                    onChange={() => {
                      setSelected((prev) => {
                        const next = new Set(prev);
                        if (next.has(item.roster_slot_id)) next.delete(item.roster_slot_id);
                        else next.add(item.roster_slot_id);
                        return next;
                      });
                    }}
                  />
                  <span>
                    {t(locale, "aiDraftProposalRow", {
                      slot: String(item.roster_slot_id),
                      member: String(item.team_member_id),
                    })}{" "}
                    {item.reason}
                  </span>
                </label>
              ))}
              <button
                type="button"
                disabled={!selected.size || Boolean(busyTask) || groupPublished || !plannerPlanningEditable}
                className="mt-2 h-10 max-w-xs rounded-lg bg-emerald-700 px-4 text-sm font-semibold text-white disabled:opacity-40"
                onClick={() => void applySelected()}
              >
                {t(locale, "aiApplySelected")}
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </Card>
  );
}
