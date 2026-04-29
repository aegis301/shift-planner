"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, BarChart3, CalendarCheck, Columns3, Download, Heart, LayoutList, Plus, RotateCw, Save, Trash2, X } from "lucide-react";
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
  onCallDuty: number;
  standbyDuty: number;
  lateDuty: number;
  other: number;
  conflicts: number;
};

type PlanningViewMode = "stacked" | "tabs";
type PlanningTab = "wishes" | "roster" | "analysis";
type DestructiveAction = "delete-period" | "regenerate-roster";

function monthLabel(period: PlanningPeriod | undefined) {
  if (!period) {
    return "";
  }
  return `${period.year}-${String(period.month).padStart(2, "0")}`;
}

function buildStats(matrix: RosterMatrix | null, warnings: ValidationWarning[]): { rows: DoctorStats[]; unassigned: number } {
  if (!matrix) {
    return { rows: [], unassigned: 0 };
  }
  const slots = new Map(matrix.slots.map((slot) => [slot.id, slot]));
  const stats = new Map<number, DoctorStats>(
    matrix.doctors.map((doctor) => [
      doctor.id,
      {
        doctorId: doctor.id,
        name: doctor.name,
        total: 0,
        onCallDuty: 0,
        standbyDuty: 0,
        lateDuty: 0,
        other: 0,
        conflicts: 0
      }
    ])
  );

  for (const assignment of matrix.assignments) {
    const doctorStats = stats.get(assignment.doctor_id);
    const slot = slots.get(assignment.roster_slot_id);
    const category = slot?.category;
    if (!doctorStats || !category) {
      continue;
    }
    doctorStats.total += 1;
    if (category === "bereitschaftsdienst") {
      doctorStats.onCallDuty += 1;
    } else if (category === "rufdienst") {
      doctorStats.standbyDuty += 1;
    } else if (category === "spaetdienst") {
      doctorStats.lateDuty += 1;
    } else {
      doctorStats.other += 1;
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
  const [viewMode, setViewMode] = useState<PlanningViewMode>("tabs");
  const [activeTab, setActiveTab] = useState<PlanningTab>("wishes");
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isExportModalOpen, setIsExportModalOpen] = useState(false);
  const [destructiveAction, setDestructiveAction] = useState<DestructiveAction | null>(null);

  const activePeriod = periods.find((period) => String(period.id) === periodId);
  const stats = useMemo(() => buildStats(rosterMatrix, warnings), [rosterMatrix, warnings]);

  const loadWarnings = useCallback(async (nextPeriodId: string) => {
    if (!nextPeriodId) {
      setWarnings([]);
      return;
    }
    setWarnings(await apiFetch<ValidationWarning[]>(`/api/v1/validation/${nextPeriodId}`));
  }, []);

  const loadRosterMatrix = useCallback(async (nextPeriodId: string) => {
    if (!nextPeriodId) {
      setRosterMatrix(null);
      return;
    }
    setRosterMatrix(await apiFetch<RosterMatrix>(`/api/v1/roster-matrix/${nextPeriodId}`));
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
    void loadRosterMatrix(periodId);
  }, [loadRosterMatrix, loadWarnings, periodId]);

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
    setActiveTab("wishes");
    setIsCreateModalOpen(false);
    setMessage(`${t(locale, "saved")}: ${monthLabel(period)}`);
  }

  async function confirmDestructiveAction() {
    if (!periodId || !destructiveAction) {
      return;
    }
    if (destructiveAction === "regenerate-roster") {
      const nextMatrix = await apiFetch<RosterMatrix>(`/api/v1/planning-periods/${periodId}/regenerate-roster`, {
        method: "POST"
      });
      setRosterMatrix(nextMatrix);
      setRosterReloadToken((value) => value + 1);
      await loadWarnings(periodId);
      setMessage(`${t(locale, "saved")}: ${t(locale, "regenerateRoster")}`);
    } else {
      await apiFetch(`/api/v1/planning-periods/${periodId}`, { method: "DELETE" });
      const nextPeriods = await apiFetch<PlanningPeriod[]>("/api/v1/planning-periods");
      setPeriods(nextPeriods);
      setPeriodId(nextPeriods[0] ? String(nextPeriods[0].id) : "");
      setRosterMatrix(null);
      setWarnings([]);
      setActiveTab("wishes");
      setMessage(t(locale, "deletePlanningPeriod"));
    }
    setDestructiveAction(null);
  }

  const handleRosterChange = useCallback(async (nextMatrix: RosterMatrix) => {
    setRosterMatrix(nextMatrix);
    await loadWarnings(String(nextMatrix.planning_period.id));
  }, [loadWarnings]);

  const handleWishesChanged = useCallback(async () => {
    if (periodId) {
      await loadWarnings(periodId);
      setRosterReloadToken((value) => value + 1);
      await loadRosterMatrix(periodId);
    }
  }, [loadRosterMatrix, loadWarnings, periodId]);

  const wishesSection = periodId ? (
    <section className="grid gap-3">
      <div>
        <h2 className="text-xl font-semibold text-ink">{t(locale, "wishesSection")}</h2>
        <p className="mt-1 text-sm text-slate-600">{t(locale, "matrixHelp")}</p>
      </div>
      <MatrixEditor periodId={periodId} compact onChanged={handleWishesChanged} />
    </section>
  ) : null;

  const rosterSection = periodId ? (
    <section className="grid gap-3">
      <div>
        <h2 className="text-xl font-semibold text-ink">{t(locale, "rosterSection")}</h2>
        <p className="mt-1 text-sm text-slate-600">{t(locale, "finalRosterHelp")}</p>
      </div>
      <RosterMatrixEditor periodId={periodId} compact reloadToken={rosterReloadToken} onMatrixChange={handleRosterChange} />
    </section>
  ) : null;

  const analysisSection = (
    <section className="grid gap-4">
      <div>
        <h2 className="text-xl font-semibold text-ink">{t(locale, "analysisSection")}</h2>
        <p className="mt-1 text-sm text-slate-600">{t(locale, "analysisHelp")}</p>
      </div>
      <InlineValidation warnings={warnings} />
      <WorkloadStats rows={stats.rows} unassigned={stats.unassigned} />
    </section>
  );

  return (
    <div className="grid gap-6">
      <Card>
        <div className="grid gap-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h1 className="text-2xl font-semibold text-ink">{t(locale, "planning")}</h1>
            <div className="flex flex-wrap items-center gap-2">
              <Field label={t(locale, "planningPeriod")}>
                <select className={`${inputClass} h-10 min-w-40`} value={periodId} onChange={(event) => setPeriodId(event.target.value)}>
                  <option value="">{t(locale, "emptyValue")}</option>
                  {periods.map((period) => (
                    <option key={period.id} value={period.id}>
                      {monthLabel(period)}
                    </option>
                  ))}
                </select>
              </Field>
              <button
                aria-label={t(locale, "createPeriod")}
                className="mt-5 inline-flex h-10 w-10 items-center justify-center rounded-lg bg-mint text-ink ring-1 ring-mint/60"
                onClick={() => setIsCreateModalOpen(true)}
                title={t(locale, "createPeriod")}
                type="button"
              >
                <Plus size={19} />
              </button>
              <button
                aria-label={t(locale, "exports")}
                className="mt-5 inline-flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-700 shadow-sm disabled:cursor-not-allowed disabled:opacity-40"
                disabled={!periodId}
                onClick={() => setIsExportModalOpen(true)}
                title={t(locale, "exports")}
                type="button"
              >
                <Download size={18} />
              </button>
              <button
                aria-label={t(locale, "regenerateRoster")}
                className="mt-5 inline-flex h-10 w-10 items-center justify-center rounded-lg border border-amber-200 bg-amber-50 text-amber-800 shadow-sm disabled:cursor-not-allowed disabled:opacity-40"
                disabled={!periodId}
                onClick={() => setDestructiveAction("regenerate-roster")}
                title={t(locale, "regenerateRoster")}
                type="button"
              >
                <RotateCw size={18} />
              </button>
              <button
                aria-label={t(locale, "deletePlanningPeriod")}
                className="mt-5 inline-flex h-10 w-10 items-center justify-center rounded-lg border border-rose-200 bg-rose-50 text-rose-700 shadow-sm disabled:cursor-not-allowed disabled:opacity-40"
                disabled={!periodId}
                onClick={() => setDestructiveAction("delete-period")}
                title={t(locale, "deletePlanningPeriod")}
                type="button"
              >
                <Trash2 size={18} />
              </button>
              <div className="mt-5 inline-flex rounded-lg border border-slate-200 bg-white p-1 shadow-sm">
                <button
                  aria-label={t(locale, "stackedView")}
                  className={`inline-flex h-8 w-9 items-center justify-center rounded-md text-sm font-semibold ${viewMode === "stacked" ? "bg-ink text-white" : "text-slate-600"}`}
                  onClick={() => setViewMode("stacked")}
                  title={t(locale, "stackedView")}
                  type="button"
                >
                  <LayoutList size={17} />
                </button>
                <button
                  aria-label={t(locale, "tabbedView")}
                  className={`inline-flex h-8 w-9 items-center justify-center rounded-md text-sm font-semibold ${viewMode === "tabs" ? "bg-ink text-white" : "text-slate-600"}`}
                  onClick={() => setViewMode("tabs")}
                  title={t(locale, "tabbedView")}
                  type="button"
                >
                  <Columns3 size={17} />
                </button>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-3 text-sm">
            {activePeriod ? <p className="text-slate-600">{t(locale, "selectedMonth")}: {monthLabel(activePeriod)}</p> : null}
            {message ? <p className="text-emerald-700">{message}</p> : null}
          </div>
        </div>
      </Card>

      {isCreateModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 px-4 py-6 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="create-period-title">
          <div className="w-full max-w-md rounded-xl bg-white p-5 shadow-soft ring-1 ring-slate-200">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 id="create-period-title" className="text-lg font-semibold text-ink">{t(locale, "createPeriod")}</h2>
              <button
                aria-label={t(locale, "close")}
                className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600"
                onClick={() => setIsCreateModalOpen(false)}
                type="button"
              >
                <X size={17} />
              </button>
            </div>
            <form className="grid gap-4 sm:grid-cols-2" onSubmit={createAndLoadPeriod}>
              <Field label={t(locale, "year")}>
                <input className={inputClass} value={newYear} onChange={(event) => setNewYear(event.target.value)} type="number" min="2020" max="2100" />
              </Field>
              <Field label={t(locale, "month")}>
                <input className={inputClass} value={newMonth} onChange={(event) => setNewMonth(event.target.value)} type="number" min="1" max="12" />
              </Field>
              <button className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-mint px-4 text-sm font-semibold text-ink sm:col-span-2">
                <Save size={17} />
                {t(locale, "createAndLoadPeriod")}
              </button>
            </form>
          </div>
        </div>
      ) : null}

      {isExportModalOpen && periodId ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 px-4 py-6 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="export-title">
          <div className="w-full max-w-md rounded-xl bg-white p-5 shadow-soft ring-1 ring-slate-200">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 id="export-title" className="text-lg font-semibold text-ink">{t(locale, "exports")}</h2>
              <button
                aria-label={t(locale, "close")}
                className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600"
                onClick={() => setIsExportModalOpen(false)}
                type="button"
              >
                <X size={17} />
              </button>
            </div>
            <div className="grid gap-3">
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
            </div>
          </div>
        </div>
      ) : null}

      {destructiveAction ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 px-4 py-6 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="destructive-title">
          <div className="w-full max-w-md rounded-xl bg-white p-5 shadow-soft ring-1 ring-rose-200">
            <div className="mb-4 flex items-start justify-between gap-3">
              <div className="flex gap-3">
                <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-rose-50 text-rose-700 ring-1 ring-rose-200">
                  <AlertTriangle size={19} />
                </span>
                <div>
                  <h2 id="destructive-title" className="text-lg font-semibold text-ink">
                    {destructiveAction === "delete-period" ? t(locale, "deletePlanningPeriod") : t(locale, "regenerateRoster")}
                  </h2>
                  <p className="mt-1 text-sm text-slate-600">{t(locale, "destructiveAction")}</p>
                </div>
              </div>
              <button
                aria-label={t(locale, "close")}
                className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600"
                onClick={() => setDestructiveAction(null)}
                type="button"
              >
                <X size={17} />
              </button>
            </div>
            <p className="rounded-lg bg-rose-50 p-3 text-sm text-rose-900 ring-1 ring-rose-100">
              {destructiveAction === "delete-period" ? t(locale, "deletePlanningPeriodWarning") : t(locale, "regenerateRosterWarning")}
            </p>
            <div className="mt-5 flex flex-wrap justify-end gap-2">
              <button
                className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700"
                onClick={() => setDestructiveAction(null)}
                type="button"
              >
                {t(locale, "close")}
              </button>
              <button
                className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-rose-700 px-4 text-sm font-semibold text-white"
                onClick={confirmDestructiveAction}
                type="button"
              >
                {destructiveAction === "delete-period" ? <Trash2 size={16} /> : <RotateCw size={16} />}
                {t(locale, "confirm")}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {periodId ? (
        viewMode === "stacked" ? (
          <>
            {wishesSection}
            {rosterSection}
            {analysisSection}
          </>
        ) : (
          <div className="grid gap-5">
            <div className="flex gap-2 overflow-x-auto rounded-lg border border-slate-200 bg-white p-1 shadow-sm">
              {([
                ["wishes", "wishesSection", Heart],
                ["roster", "rosterSection", CalendarCheck],
                ["analysis", "analysisSection", BarChart3]
              ] as const).map(([tab, label, Icon]) => (
                <button
                  key={tab}
                  aria-label={t(locale, label)}
                  className={`inline-flex h-10 w-12 shrink-0 items-center justify-center rounded-md text-sm font-semibold ${activeTab === tab ? "bg-ink text-white" : "text-slate-600"}`}
                  onClick={() => setActiveTab(tab)}
                  title={t(locale, label)}
                  type="button"
                >
                  <Icon size={19} />
                </button>
              ))}
            </div>
            {activeTab === "wishes" ? wishesSection : null}
            {activeTab === "roster" ? rosterSection : null}
            {activeTab === "analysis" ? analysisSection : null}
          </div>
        )
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
                  <th className="p-3 font-semibold">{t(locale, "onCallDutyCategory")}</th>
                  <th className="p-3 font-semibold">{t(locale, "standbyDutyCategory")}</th>
                  <th className="p-3 font-semibold">{t(locale, "lateDutyCategory")}</th>
                  <th className="p-3 font-semibold">{t(locale, "other")}</th>
                  <th className="p-3 font-semibold">{t(locale, "conflicts")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.doctorId} className="border-t border-slate-100">
                    <td className="p-3 font-medium text-ink">{row.name}</td>
                    <td className="p-3">{row.total}</td>
                    <td className="p-3">{row.onCallDuty}</td>
                    <td className="p-3">{row.standbyDuty}</td>
                    <td className="p-3">{row.lateDuty}</td>
                    <td className="p-3">{row.other}</td>
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
