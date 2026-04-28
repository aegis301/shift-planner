"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Download, RefreshCw, Save } from "lucide-react";
import { Card, Field, inputClass } from "@/components/Card";
import { MatrixEditor } from "@/components/MatrixEditor";
import { LocaleShell, useLocale } from "@/components/LocaleProvider";
import { RosterMatrixEditor, type RosterMatrix } from "@/components/RosterMatrixEditor";
import { API_BASE_URL, apiFetch } from "@/lib/api";
import { t } from "@/lib/i18n";

type PlanningPeriod = {
  id: number;
  year: number;
  month: number;
  status: string;
};

type ValidationWarning = {
  code: string;
  severity: "info" | "warning" | "error";
  message: string;
  doctor_id: number | null;
  date: string | null;
  details: Record<string, unknown>;
};

type DoctorStats = {
  doctorId: number;
  name: string;
  total: number;
  day: number;
  night: number;
  late: number;
  onCall: number;
  conflicts: number;
};

function monthLabel(period: PlanningPeriod | undefined) {
  if (!period) {
    return "";
  }
  return `${period.year}-${String(period.month).padStart(2, "0")}`;
}

function isLateShift(name: string, code: string) {
  const text = `${name} ${code}`.toLowerCase();
  return text.includes("spät") || text.includes("spaet") || text.includes("late");
}

function buildStats(matrix: RosterMatrix | null, warnings: ValidationWarning[]): { rows: DoctorStats[]; unassigned: number } {
  if (!matrix) {
    return { rows: [], unassigned: 0 };
  }
  const shiftTypes = new Map(matrix.shift_types.map((shiftType) => [shiftType.id, shiftType]));
  const slots = new Map(matrix.slots.map((slot) => [slot.id, slot]));
  const stats = new Map<number, DoctorStats>(
    matrix.doctors.map((doctor) => [
      doctor.id,
      {
        doctorId: doctor.id,
        name: doctor.name,
        total: 0,
        day: 0,
        night: 0,
        late: 0,
        onCall: 0,
        conflicts: 0
      }
    ])
  );

  for (const assignment of matrix.assignments) {
    const doctorStats = stats.get(assignment.doctor_id);
    const slot = slots.get(assignment.roster_slot_id);
    const shiftType = slot ? shiftTypes.get(slot.shift_type_id) : undefined;
    if (!doctorStats || !shiftType) {
      continue;
    }
    doctorStats.total += 1;
    if (shiftType.category === "night") {
      doctorStats.night += 1;
    } else if (shiftType.category === "on_call") {
      doctorStats.onCall += 1;
    } else if (isLateShift(`${shiftType.name_de} ${shiftType.name_en}`, shiftType.code)) {
      doctorStats.late += 1;
    } else {
      doctorStats.day += 1;
    }
  }

  for (const warning of warnings) {
    if (!warning.code.startsWith("ROSTER_MATRIX") || !warning.doctor_id) {
      continue;
    }
    const doctorStats = stats.get(warning.doctor_id);
    if (doctorStats) {
      doctorStats.conflicts += 1;
    }
  }

  return {
    rows: [...stats.values()].sort((a, b) => a.name.localeCompare(b.name)),
    unassigned: Math.max(0, matrix.slots.length - matrix.assignments.length)
  };
}

function PlanningWorkspaceContent() {
  const { locale } = useLocale();
  const currentDate = new Date();
  const [periods, setPeriods] = useState<PlanningPeriod[]>([]);
  const [periodId, setPeriodId] = useState("");
  const [newYear, setNewYear] = useState(String(currentDate.getFullYear()));
  const [newMonth, setNewMonth] = useState(String(currentDate.getMonth() + 1));
  const [rosterMatrix, setRosterMatrix] = useState<RosterMatrix | null>(null);
  const [warnings, setWarnings] = useState<ValidationWarning[]>([]);
  const [message, setMessage] = useState("");
  const [rosterReloadToken, setRosterReloadToken] = useState(0);

  const activePeriod = periods.find((period) => String(period.id) === periodId);
  const stats = useMemo(() => buildStats(rosterMatrix, warnings), [rosterMatrix, warnings]);

  const loadWarnings = useCallback(async (nextPeriodId: string) => {
    if (!nextPeriodId) {
      setWarnings([]);
      return;
    }
    setWarnings(await apiFetch<ValidationWarning[]>(`/api/v1/validation/${nextPeriodId}`));
  }, []);

  const refreshPeriods = useCallback(async () => {
    const next = await apiFetch<PlanningPeriod[]>("/api/v1/planning-periods");
    setPeriods(next);
    if (!periodId && next[0]) {
      setPeriodId(String(next[0].id));
    }
  }, [periodId]);

  useEffect(() => {
    void refreshPeriods();
  }, [refreshPeriods]);

  useEffect(() => {
    if (!periodId) {
      return;
    }
    void loadWarnings(periodId);
  }, [loadWarnings, periodId]);

  async function createAndLoadPeriod(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const period = await apiFetch<PlanningPeriod>("/api/v1/planning-periods", {
      method: "POST",
      body: JSON.stringify({ year: Number(newYear), month: Number(newMonth) })
    });
    const nextPeriodId = String(period.id);
    const nextPeriods = await apiFetch<PlanningPeriod[]>("/api/v1/planning-periods");
    setPeriods(nextPeriods);
    setPeriodId(nextPeriodId);
    setMessage(`${t(locale, "saved")}: ${monthLabel(period)}`);
  }

  const handleRosterChange = useCallback(async (nextMatrix: RosterMatrix) => {
    setRosterMatrix(nextMatrix);
    await loadWarnings(String(nextMatrix.planning_period.id));
  }, [loadWarnings]);

  const handleWishesChanged = useCallback(async () => {
    if (periodId) {
      await loadWarnings(periodId);
      setRosterReloadToken((value) => value + 1);
    }
  }, [loadWarnings, periodId]);

  return (
    <div className="grid gap-6">
      <Card>
        <div className="grid gap-5">
          <div>
            <h1 className="text-2xl font-semibold text-ink">{t(locale, "planning")}</h1>
            <p className="mt-2 max-w-3xl text-sm text-slate-600">{t(locale, "planningWorkspaceHelp")}</p>
          </div>
          <form className="flex flex-wrap items-end gap-2 rounded-lg bg-slate-50 p-3 ring-1 ring-slate-200" onSubmit={createAndLoadPeriod}>
            <Field label={t(locale, "year")}>
              <input className={`${inputClass} w-28`} value={newYear} onChange={(event) => setNewYear(event.target.value)} type="number" min="2020" max="2100" />
            </Field>
            <Field label={t(locale, "month")}>
              <input className={`${inputClass} w-24`} value={newMonth} onChange={(event) => setNewMonth(event.target.value)} type="number" min="1" max="12" />
            </Field>
            <button className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-mint px-4 text-sm font-semibold text-ink">
              <Save size={17} />
              {t(locale, "createAndLoadPeriod")}
            </button>
          </form>
          <div className="flex flex-wrap items-end gap-2">
            <Field label={t(locale, "planningPeriod")}>
              <select className={`${inputClass} min-w-44`} value={periodId} onChange={(event) => setPeriodId(event.target.value)}>
                <option value="">{t(locale, "emptyValue")}</option>
                {periods.map((period) => (
                  <option key={period.id} value={period.id}>
                    {monthLabel(period)}
                  </option>
                ))}
              </select>
            </Field>
            <button
              className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white"
              onClick={() => {
                if (periodId) {
                  void loadWarnings(periodId);
                  setRosterReloadToken((value) => value + 1);
                }
              }}
              type="button"
            >
              <RefreshCw size={17} />
              {t(locale, "refresh")}
            </button>
            {periodId ? (
              <>
                <a
                  className="inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700"
                  href={`${API_BASE_URL}/api/v1/exports/matrix/${periodId}.csv`}
                >
                  <Download size={17} />
                  {t(locale, "wishesCsvExport")}
                </a>
                <a
                  className="inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700"
                  href={`${API_BASE_URL}/api/v1/exports/roster-matrix/${periodId}.csv`}
                >
                  <Download size={17} />
                  {t(locale, "rosterCsvExport")}
                </a>
              </>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-3 text-sm">
            {activePeriod ? <p className="text-slate-600">{t(locale, "selectedMonth")}: {monthLabel(activePeriod)}</p> : null}
            {message ? <p className="text-emerald-700">{message}</p> : null}
          </div>
        </div>
      </Card>

      {periodId ? (
        <>
          <section className="grid gap-3">
            <div>
              <h2 className="text-xl font-semibold text-ink">{t(locale, "wishesSection")}</h2>
              <p className="mt-1 text-sm text-slate-600">{t(locale, "matrixHelp")}</p>
            </div>
            <MatrixEditor periodId={periodId} compact onChanged={handleWishesChanged} />
          </section>

          <section className="grid gap-3">
            <div>
              <h2 className="text-xl font-semibold text-ink">{t(locale, "rosterSection")}</h2>
              <p className="mt-1 text-sm text-slate-600">{t(locale, "finalRosterHelp")}</p>
            </div>
            <RosterMatrixEditor periodId={periodId} compact reloadToken={rosterReloadToken} onMatrixChange={handleRosterChange} />
          </section>

          <InlineValidation warnings={warnings} />
          <WorkloadStats rows={stats.rows} unassigned={stats.unassigned} />
        </>
      ) : (
        <Card>
          <p className="text-sm text-slate-500">{t(locale, "noPlanningPeriodSelected")}</p>
        </Card>
      )}
    </div>
  );
}

function InlineValidation({ warnings }: { warnings: ValidationWarning[] }) {
  const { locale } = useLocale();
  const rosterWarnings = warnings.filter((warning) => warning.code.startsWith("ROSTER_MATRIX"));
  return (
    <Card>
      <div className="grid gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold text-ink">{t(locale, "conflictSummary")}</h2>
          <span className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 ${rosterWarnings.length ? "bg-rose-100 text-rose-800 ring-rose-200" : "bg-emerald-100 text-emerald-800 ring-emerald-200"}`}>
            {rosterWarnings.length}
          </span>
        </div>
        {rosterWarnings.length ? (
          <div className="grid gap-2">
            {rosterWarnings.slice(0, 6).map((warning, index) => (
              <div key={`${warning.code}-${warning.doctor_id}-${warning.date}-${index}`} className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-900 ring-1 ring-rose-200">
                {warning.date ? `${warning.date}: ` : ""}{warning.message}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-slate-600">{t(locale, "noConflicts")}</p>
        )}
      </div>
    </Card>
  );
}

function WorkloadStats({ rows, unassigned }: { rows: DoctorStats[]; unassigned: number }) {
  const { locale } = useLocale();
  return (
    <Card>
      <div className="grid gap-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold text-ink">{t(locale, "workloadStats")}</h2>
            <p className="mt-1 text-sm text-slate-600">{t(locale, "unassignedSlots")}: {unassigned}</p>
          </div>
        </div>
        {rows.length ? (
          <div className="overflow-auto rounded-lg border border-slate-200">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-left text-slate-600">
                <tr>
                  <th className="p-3 font-semibold">{t(locale, "doctors")}</th>
                  <th className="p-3 font-semibold">{t(locale, "totalShifts")}</th>
                  <th className="p-3 font-semibold">{t(locale, "day")}</th>
                  <th className="p-3 font-semibold">{t(locale, "night")}</th>
                  <th className="p-3 font-semibold">{t(locale, "spaetdienst")}</th>
                  <th className="p-3 font-semibold">{t(locale, "onCall")}</th>
                  <th className="p-3 font-semibold">{t(locale, "conflicts")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.doctorId} className="border-t border-slate-100">
                    <td className="p-3 font-medium text-ink">{row.name}</td>
                    <td className="p-3">{row.total}</td>
                    <td className="p-3">{row.day}</td>
                    <td className="p-3">{row.night}</td>
                    <td className="p-3">{row.late}</td>
                    <td className="p-3">{row.onCall}</td>
                    <td className={row.conflicts ? "p-3 font-semibold text-rose-700" : "p-3"}>{row.conflicts}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-slate-500">{t(locale, "noData")}</p>
        )}
      </div>
    </Card>
  );
}

export function PlanningWorkspace() {
  return (
    <LocaleShell>
      <PlanningWorkspaceContent />
    </LocaleShell>
  );
}
