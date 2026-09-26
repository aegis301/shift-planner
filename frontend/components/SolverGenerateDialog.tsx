"use client";

import { FormEvent, useEffect, useState } from "react";
import { Sparkles, X } from "lucide-react";
import { Field, inputClass } from "@/components/Card";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { SolverRunResult } from "@/components/SolverRunResult";
import { ApiError } from "@/lib/api";
import { t, type Locale } from "@/lib/i18n";
import {
  applySolverRun,
  cancelSolverRun,
  createSolverRun,
  fetchSolverConfig,
  getSolverRun,
  isSolverRunActive,
  SOLVER_FORM_WEIGHT_KEYS,
  solverStatusLabel,
  solverWeightLabel,
  type SolverFormWeightKey,
  type SolverObjectiveWeights,
  type SolverRunRead
} from "@/lib/solver";

type FormWeights = Record<SolverFormWeightKey, string>;

function weightsToForm(weights: SolverObjectiveWeights): FormWeights {
  return {
    unfilled: String(weights.unfilled),
    duty_count: String(weights.duty_count),
    fairness: String(weights.fairness),
    wish: String(weights.wish),
    avoid_time_window: String(weights.avoid_time_window)
  };
}

export function SolverGenerateDialog({
  locale,
  open,
  periodId,
  shiftGroupId,
  onClose,
  onApplied,
  onRunChange
}: {
  locale: Locale;
  open: boolean;
  periodId: string;
  shiftGroupId: string;
  onClose: () => void;
  onApplied: (run: SolverRunRead) => void;
  onRunChange: (run: SolverRunRead) => void;
}) {
  const [ceiling, setCeiling] = useState(120);
  const [budget, setBudget] = useState("30");
  const [overwrite, setOverwrite] = useState(false);
  const [weights, setWeights] = useState<FormWeights | null>(null);
  const [sourceWeights, setSourceWeights] = useState<SolverObjectiveWeights | null>(null);
  const [run, setRun] = useState<SolverRunRead | null>(null);
  const [confirmApply, setConfirmApply] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!open) {
      return;
    }
    setRun(null);
    setConfirmApply(false);
    setBusy(false);
    setMessage("");
    void fetchSolverConfig()
      .then((config) => {
        setCeiling(config.time_budget_ceiling_seconds);
        setBudget(String(config.default_time_budget_seconds));
        setSourceWeights(config.weights);
        setWeights(weightsToForm(config.weights));
      })
      .catch(() => {
        setMessage(t(locale, "solverLoadError"));
      });
  }, [open, locale]);

  useEffect(() => {
    if (!open || !run || !isSolverRunActive(run.status)) {
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void getSolverRun(periodId, run.id)
        .then((next) => {
          if (cancelled) {
            return;
          }
          setRun(next);
          if (!isSolverRunActive(next.status)) {
            onRunChange(next);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setMessage(t(locale, "solverLoadError"));
          }
        });
    }, 1000);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [open, run, periodId, locale, onRunChange]);

  if (!open) {
    return null;
  }

  async function startRun(event: FormEvent) {
    event.preventDefault();
    if (!weights) {
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const created = await createSolverRun(periodId, {
        shift_group_id: Number(shiftGroupId),
        time_budget_seconds: Number(budget),
        overwrite_existing: overwrite,
        objective_weights: {
          ...(sourceWeights ?? {
            unfilled: 10000,
            duty_count: 250,
            fairness: 8,
            wish: 25,
            avoid_time_window: 15,
            warning: 40,
            pair_warning: 70
          }),
          unfilled: Number(weights.unfilled),
          duty_count: Number(weights.duty_count),
          fairness: Number(weights.fairness),
          wish: Number(weights.wish),
          avoid_time_window: Number(weights.avoid_time_window)
        }
      });
      setRun(created);
      onRunChange(created);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setMessage(t(locale, "solverGeneratePublishedBlocked"));
      } else {
        setMessage(t(locale, "solverLoadError"));
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleCancel() {
    if (!run) {
      return;
    }
    setBusy(true);
    try {
      const next = await cancelSolverRun(periodId, run.id);
      setRun(next);
      onRunChange(next);
    } catch {
      setMessage(t(locale, "solverLoadError"));
    } finally {
      setBusy(false);
    }
  }

  async function handleApply() {
    if (!run) {
      return;
    }
    setBusy(true);
    try {
      const applied = await applySolverRun(periodId, run.id);
      setRun(applied.run);
      onRunChange(applied.run);
      setConfirmApply(false);
      onApplied(applied.run);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setMessage(t(locale, "solverGeneratePublishedBlocked"));
      } else {
        setMessage(t(locale, "solverLoadError"));
      }
    } finally {
      setBusy(false);
    }
  }

  const showForm = run == null;
  const canApply = run?.status === "succeeded" && run.applied_at == null;

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onClose(); }}>
      <DialogContent className="max-h-[90vh] max-w-lg overflow-y-auto" aria-labelledby="solver-generate-title">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <DialogTitle id="solver-generate-title">
              {t(locale, "solverGenerateTitle")}
            </DialogTitle>
            <p className="mt-2 text-sm text-slate-600">{t(locale, "solverGenerateHelp")}</p>
          </div>
          <button
            aria-label={t(locale, "close")}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600"
            onClick={onClose}
            type="button"
          >
            <X size={17} />
          </button>
        </div>
        {message ? <p className="mb-3 text-sm text-rose-700">{message}</p> : null}
        {showForm ? (
          <form className="grid gap-4" onSubmit={startRun}>
            <Field hint={t(locale, "solverTimeBudgetHint", { ceiling: String(ceiling) })} label={t(locale, "solverTimeBudget")}>
              <input
                className={inputClass}
                max={ceiling}
                min={1}
                onChange={(event) => setBudget(event.target.value)}
                required
                type="number"
                value={budget}
              />
            </Field>
            <label className="flex items-start gap-2 text-sm text-slate-700">
              <input
                checked={overwrite}
                className="mt-1"
                onChange={(event) => setOverwrite(event.target.checked)}
                type="checkbox"
              />
              <span>
                <span className="font-medium">{t(locale, "solverOverwriteExisting")}</span>
                <span className="mt-1 block font-normal text-xs text-slate-500">{t(locale, "solverOverwriteExistingHint")}</span>
              </span>
            </label>
            <fieldset className="grid gap-3">
              <legend className="text-sm font-medium text-slate-700">{t(locale, "solverObjectiveWeights")}</legend>
              {weights
                ? SOLVER_FORM_WEIGHT_KEYS.map((key) => (
                    <Field key={key} label={solverWeightLabel(locale, key)}>
                      <input
                        className={inputClass}
                        min={0}
                        onChange={(event) => setWeights({ ...weights, [key]: event.target.value })}
                        required
                        type="number"
                        value={weights[key]}
                      />
                    </Field>
                  ))
                : null}
            </fieldset>
            <div className="flex flex-wrap justify-end gap-2">
              <button
                className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700"
                onClick={onClose}
                type="button"
              >
                {t(locale, "close")}
              </button>
              <button
                className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white disabled:opacity-40"
                disabled={busy || weights == null}
                type="submit"
              >
                <Sparkles size={16} />
                {t(locale, "solverStart")}
              </button>
            </div>
          </form>
        ) : run ? (
          <div className="grid gap-4">
            <p className="text-sm font-medium text-ink">{solverStatusLabel(locale, run.status)}</p>
            {isSolverRunActive(run.status) ? <p className="text-sm text-slate-600">{t(locale, "solverRunningHelp")}</p> : null}
            {!isSolverRunActive(run.status) ? <SolverRunResult locale={locale} run={run} /> : null}
            {confirmApply ? (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
                <p className="text-sm font-semibold text-ink">{t(locale, "solverApplyConfirmTitle")}</p>
                <p className="mt-1 text-sm text-slate-700">
                  {t(locale, "solverApplyConfirmBody", { count: String((run.proposed_assignments ?? []).length) })}
                </p>
                <div className="mt-3 flex flex-wrap justify-end gap-2">
                  <button
                    className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700"
                    onClick={() => setConfirmApply(false)}
                    type="button"
                  >
                    {t(locale, "close")}
                  </button>
                  <button
                    className="inline-flex h-10 items-center justify-center rounded-lg bg-ink px-4 text-sm font-semibold text-white disabled:opacity-40"
                    disabled={busy}
                    onClick={() => void handleApply()}
                    type="button"
                  >
                    {t(locale, "solverApply")}
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex flex-wrap justify-end gap-2">
                <button
                  className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700"
                  onClick={onClose}
                  type="button"
                >
                  {t(locale, "close")}
                </button>
                {isSolverRunActive(run.status) ? (
                  <button
                    className="inline-flex h-10 items-center justify-center rounded-lg border border-rose-200 bg-rose-50 px-4 text-sm font-semibold text-rose-800 disabled:opacity-40"
                    disabled={busy}
                    onClick={() => void handleCancel()}
                    type="button"
                  >
                    {t(locale, "solverCancelRun")}
                  </button>
                ) : null}
                {canApply ? (
                  <button
                    className="inline-flex h-10 items-center justify-center rounded-lg bg-ink px-4 text-sm font-semibold text-white"
                    onClick={() => setConfirmApply(true)}
                    type="button"
                  >
                    {t(locale, "solverApply")}
                  </button>
                ) : null}
              </div>
            )}
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
