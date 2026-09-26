"use client";

import { t, type Locale } from "@/lib/i18n";
import {
  readPostCheckFinding,
  readUnfilledSlot,
  solverWeightLabel,
  type SolverRunRead
} from "@/lib/solver";

function findingTone(severity: string): string {
  if (severity === "error") {
    return "text-rose-800";
  }
  if (severity === "warning") {
    return "text-amber-800";
  }
  return "text-slate-700";
}

export function SolverRunResult({ locale, run }: { locale: Locale; run: SolverRunRead }) {
  const breakdownEntries = Object.entries(run.objective_breakdown ?? {}).filter(([name]) => name !== "nogo");
  const assignmentCount = run.proposed_assignments?.length ?? 0;
  const unfilledSlots = (run.unfilled_slots ?? []).map(readUnfilledSlot);
  const postCheckFindings = (run.post_check_findings ?? []).map(readPostCheckFinding);

  return (
    <div className="grid gap-4">
      {run.failure_reason ? (
        <p className="text-sm text-rose-700">
          {t(locale, "solverFailureReason")}: {run.failure_reason}
        </p>
      ) : null}
      {run.status === "succeeded" ? (
        <p className="text-sm text-slate-600">
          {t(locale, "solverProposedCount", { count: String(assignmentCount) })}
        </p>
      ) : null}
      <div>
        <h3 className="text-sm font-semibold text-ink">{t(locale, "solverObjectiveBreakdown")}</h3>
        {breakdownEntries.length === 0 ? (
          <p className="mt-1 text-sm text-slate-500">{t(locale, "noData")}</p>
        ) : (
          <ul className="mt-2 grid gap-1 text-sm text-slate-700">
            {breakdownEntries.map(([name, value]) => (
              <li className="flex items-center justify-between gap-3" key={name}>
                <span>{solverWeightLabel(locale, name)}</span>
                <span className="font-medium tabular-nums">{typeof value === "number" ? value.toLocaleString() : String(value)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <h3 className="text-sm font-semibold text-ink">{t(locale, "solverUnfilledSlots")}</h3>
        {unfilledSlots.length === 0 ? (
          <p className="mt-1 text-sm text-slate-500">{t(locale, "solverUnfilledNone")}</p>
        ) : (
          <ul className="mt-2 grid gap-2">
            {unfilledSlots.map((slot) => (
              <li className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950" key={slot.roster_slot_id}>
                <p className="font-medium">
                  {slot.slot_date} · {slot.label}
                </p>
                {slot.binding_constraints.length > 0 ? (
                  <p className="mt-1 text-xs text-amber-800">
                    {t(locale, "solverBindingConstraints")}: {slot.binding_constraints.join(", ")}
                  </p>
                ) : (
                  <p className="mt-1 text-xs text-amber-800">{t(locale, "solverBindingConstraintsUnknown")}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <h3 className="text-sm font-semibold text-ink">{t(locale, "solverPostCheckFindings")}</h3>
        {postCheckFindings.length === 0 ? (
          <p className="mt-1 text-sm text-slate-500">{t(locale, "solverPostCheckNone")}</p>
        ) : (
          <ul className="mt-2 grid gap-1 text-sm">
            {postCheckFindings.map((finding, index) => (
              <li className={findingTone(finding.severity)} key={`${finding.code}-${finding.date ?? ""}-${index}`}>
                {finding.code}
                {finding.date ? ` · ${finding.date}` : ""}
                {finding.message ? ` — ${finding.message}` : ""}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
