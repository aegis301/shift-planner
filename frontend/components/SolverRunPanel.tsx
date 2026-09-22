"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/Card";
import { SolverRunResult } from "@/components/SolverRunResult";
import { useLocale } from "@/components/LocaleProvider";
import { ApiError } from "@/lib/api";
import { t } from "@/lib/i18n";
import {
  applySolverRun,
  getSolverRun,
  isSolverRunActive,
  listSolverRuns,
  solverStatusLabel,
  type SolverRunRead
} from "@/lib/solver";

export function SolverRunPanel({
  periodId,
  shiftGroupId,
  reloadToken,
  onApplied
}: {
  periodId: string;
  shiftGroupId: string;
  reloadToken: number;
  onApplied: (run: SolverRunRead) => void;
}) {
  const { locale } = useLocale();
  const [run, setRun] = useState<SolverRunRead | null>(null);
  const [loadError, setLoadError] = useState("");
  const [confirmApply, setConfirmApply] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!periodId || !shiftGroupId) {
      setRun(null);
      setLoadError("");
      return;
    }
    void listSolverRuns(periodId, shiftGroupId)
      .then((runs) => {
        setRun(runs[0] ?? null);
        setLoadError("");
      })
      .catch(() => {
        setRun(null);
        setLoadError(t(locale, "solverLoadError"));
      });
  }, [periodId, shiftGroupId, reloadToken, locale]);

  useEffect(() => {
    if (!periodId || !run || !isSolverRunActive(run.status)) {
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void getSolverRun(periodId, run.id)
        .then((next) => {
          if (!cancelled) {
            setRun(next);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setLoadError(t(locale, "solverLoadError"));
          }
        });
    }, 1000);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [periodId, run, locale]);

  async function handleApply() {
    if (!run) {
      return;
    }
    setBusy(true);
    try {
      const applied = await applySolverRun(periodId, run.id);
      setRun(applied.run);
      setConfirmApply(false);
      onApplied(applied.run);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setLoadError(t(locale, "solverGeneratePublishedBlocked"));
      } else {
        setLoadError(t(locale, "solverLoadError"));
      }
    } finally {
      setBusy(false);
    }
  }

  const canApply = run?.status === "succeeded" && run.applied_at == null;

  return (
    <Card>
      <div className="grid gap-4">
        <div>
          <h2 className="text-lg font-semibold text-ink">{t(locale, "solverSection")}</h2>
          <p className="mt-1 text-sm text-slate-600">{t(locale, "solverSectionHelp")}</p>
        </div>
        {loadError ? <p className="text-sm text-rose-700">{loadError}</p> : null}
        {!shiftGroupId ? (
          <p className="text-sm text-amber-800">{t(locale, "selectPlanningShiftGroup")}</p>
        ) : !run ? (
          <p className="text-sm text-slate-500">{t(locale, "solverNoRuns")}</p>
        ) : (
          <div className="grid gap-3">
            <p className="text-sm font-medium text-ink">
              {t(locale, "solverLatestRun")}: {solverStatusLabel(locale, run.status)}
            </p>
            {isSolverRunActive(run.status) ? (
              <p className="text-sm text-slate-600">{t(locale, "solverRunningHelp")}</p>
            ) : (
              <SolverRunResult locale={locale} run={run} />
            )}
            {canApply && confirmApply ? (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
                <p className="text-sm font-semibold text-ink">{t(locale, "solverApplyConfirmTitle")}</p>
                <p className="mt-1 text-sm text-slate-700">
                  {t(locale, "solverApplyConfirmBody", { count: String(run.proposed_assignments.length) })}
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
            ) : canApply ? (
              <div className="flex justify-end">
                <button
                  className="inline-flex h-10 items-center justify-center rounded-lg bg-ink px-4 text-sm font-semibold text-white"
                  onClick={() => setConfirmApply(true)}
                  type="button"
                >
                  {t(locale, "solverApply")}
                </button>
              </div>
            ) : null}
          </div>
        )}
      </div>
    </Card>
  );
}
