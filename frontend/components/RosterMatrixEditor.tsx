"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Download, RefreshCw, Save } from "lucide-react";
import { API_BASE_URL, apiFetch } from "@/lib/api";
import { t, type Locale, type TranslationKey } from "@/lib/i18n";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";

type PlanningStatus =
  | "dienstwunsch"
  | "urlaub"
  | "kein_dienst"
  | "forschung"
  | "lehre"
  | "frei"
  | "tagdienst"
  | "nachtdienst"
  | "spaetdienst"
  | "rufdienst";

type Doctor = {
  id: number;
  name: string;
  email: string;
  employment_percentage: number;
};

type MatrixDay = {
  date: string;
  weekday: string;
};

type PlanningPeriod = {
  id: number;
  year: number;
  month: number;
  status: string;
};

type ShiftType = {
  id: number;
  code: string;
  name_de: string;
  name_en: string;
  starts_at: string;
  ends_at: string;
  category: "day" | "night" | "on_call" | "other";
  is_active: boolean;
};

type RosterSlot = {
  id: number;
  planning_period_id: number;
  shift_type_id: number;
  slot_date: string;
  position: number;
  label: string | null;
};

type RosterSlotAssignment = {
  id: number;
  roster_slot_id: number;
  doctor_id: number;
  manual_override: boolean;
};

type PlanningCell = {
  id: number;
  planning_period_id: number;
  doctor_id: number;
  cell_date: string;
  status: PlanningStatus;
  comment: string | null;
};

export type RosterMatrix = {
  planning_period: PlanningPeriod;
  doctors: Doctor[];
  days: MatrixDay[];
  shift_types: ShiftType[];
  slots: RosterSlot[];
  assignments: RosterSlotAssignment[];
  planning_cells: PlanningCell[];
};

const STATUS_META: Record<PlanningStatus, { label: TranslationKey; color: string }> = {
  dienstwunsch: { label: "dienstwunsch", color: "bg-sky-100 text-sky-800 ring-sky-200" },
  urlaub: { label: "urlaub", color: "bg-rose-100 text-rose-800 ring-rose-200" },
  kein_dienst: { label: "keinDienst", color: "bg-orange-100 text-orange-800 ring-orange-200" },
  forschung: { label: "forschung", color: "bg-violet-100 text-violet-800 ring-violet-200" },
  lehre: { label: "lehre", color: "bg-amber-100 text-amber-800 ring-amber-200" },
  frei: { label: "frei", color: "bg-slate-100 text-slate-700 ring-slate-200" },
  tagdienst: { label: "tagdienst", color: "bg-emerald-100 text-emerald-800 ring-emerald-200" },
  nachtdienst: { label: "nachtdienst", color: "bg-indigo-100 text-indigo-800 ring-indigo-200" },
  spaetdienst: { label: "spaetdienst", color: "bg-teal-100 text-teal-800 ring-teal-200" },
  rufdienst: { label: "rufdienst", color: "bg-coral/15 text-red-800 ring-coral/30" }
};

const UNAVAILABLE_STATUSES = new Set<PlanningStatus>(["urlaub", "kein_dienst", "forschung", "lehre", "frei"]);

function formatDate(locale: Locale, value: string) {
  return new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-GB", {
    weekday: "short",
    day: "2-digit",
    month: "2-digit"
  }).format(new Date(`${value}T12:00:00`));
}

function shiftLabel(locale: Locale, shiftType: ShiftType) {
  return locale === "de" ? shiftType.name_de : shiftType.name_en;
}

export function RosterMatrixEditor({
  periodId: controlledPeriodId,
  compact = false,
  reloadToken = 0,
  onMatrixChange
}: {
  periodId?: string;
  compact?: boolean;
  reloadToken?: number;
  onMatrixChange?: (matrix: RosterMatrix) => void | Promise<void>;
} = {}) {
  const { locale } = useLocale();
  const currentDate = new Date();
  const [periodId, setPeriodId] = useState("1");
  const [newYear, setNewYear] = useState(String(currentDate.getFullYear()));
  const [newMonth, setNewMonth] = useState(String(currentDate.getMonth() + 1));
  const [matrix, setMatrix] = useState<RosterMatrix | null>(null);
  const [message, setMessage] = useState("");
  const [savingAssignments, setSavingAssignments] = useState(0);

  const slotMap = useMemo(() => {
    const map = new Map<string, RosterSlot>();
    matrix?.slots.forEach((slot) => map.set(`${slot.slot_date}:${slot.shift_type_id}:${slot.position}`, slot));
    return map;
  }, [matrix]);

  const assignmentMap = useMemo(() => {
    const map = new Map<number, RosterSlotAssignment>();
    matrix?.assignments.forEach((assignment) => map.set(assignment.roster_slot_id, assignment));
    return map;
  }, [matrix]);

  const planningCellMap = useMemo(() => {
    const map = new Map<string, PlanningCell>();
    matrix?.planning_cells.forEach((cell) => map.set(`${cell.cell_date}:${cell.doctor_id}`, cell));
    return map;
  }, [matrix]);

  const activePeriodId = controlledPeriodId ?? periodId;

  const publishMatrix = useCallback(
    async (next: RosterMatrix) => {
      setMatrix(next);
      await onMatrixChange?.(next);
    },
    [onMatrixChange]
  );

  const loadRosterById = useCallback(async (nextPeriodId: string) => {
    const next = await apiFetch<RosterMatrix>(`/api/v1/roster-matrix/${nextPeriodId}`);
    await publishMatrix(next);
  }, [publishMatrix]);

  const loadRoster = useCallback(async () => {
    await loadRosterById(activePeriodId);
  }, [activePeriodId, loadRosterById]);

  useEffect(() => {
    if (controlledPeriodId) {
      void loadRosterById(controlledPeriodId);
      return;
    }

    async function loadLatestPeriod() {
      const periods = await apiFetch<PlanningPeriod[]>("/api/v1/planning-periods");
      const latest = periods[0];
      if (!latest) {
        return;
      }
      const nextPeriodId = String(latest.id);
      setPeriodId(nextPeriodId);
      await loadRosterById(nextPeriodId);
    }

    void loadLatestPeriod();
  }, [controlledPeriodId, loadRosterById, reloadToken]);

  async function createAndLoadPeriod(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const period = await apiFetch<PlanningPeriod>("/api/v1/planning-periods", {
      method: "POST",
      body: JSON.stringify({ year: Number(newYear), month: Number(newMonth) })
    });
    const nextPeriodId = String(period.id);
    setPeriodId(nextPeriodId);
    await loadRosterById(nextPeriodId);
    setMessage(`${t(locale, "saved")}: ${t(locale, "periodId")} ${nextPeriodId}`);
  }

  async function manualSave() {
    await loadRoster();
    setMessage(t(locale, "saved"));
  }

  async function saveAssignment(rosterSlotId: number, doctorId: number | "") {
    setSavingAssignments((count) => count + 1);
    try {
      if (!doctorId) {
        await apiFetch("/api/v1/roster-matrix/assignments/clear", {
          method: "POST",
          body: JSON.stringify({ roster_slot_id: rosterSlotId })
        });
        if (matrix) {
          await publishMatrix({
            ...matrix,
            assignments: matrix.assignments.filter((assignment) => assignment.roster_slot_id !== rosterSlotId)
          });
        }
      } else {
        const saved = await apiFetch<RosterSlotAssignment>("/api/v1/roster-matrix/assignments", {
          method: "PUT",
          body: JSON.stringify({
            roster_slot_id: rosterSlotId,
            doctor_id: doctorId,
            comment: null,
            manual_override: true
          })
        });
        if (matrix) {
          await publishMatrix({
            ...matrix,
            assignments: [
              ...matrix.assignments.filter((assignment) => assignment.roster_slot_id !== rosterSlotId),
              saved
            ]
          });
        }
      }
      setMessage(t(locale, "autosaved"));
    } finally {
      setSavingAssignments((count) => Math.max(0, count - 1));
    }
  }

  return (
    <div className="grid gap-5">
      {!compact ? (
        <Card>
          <div className="grid gap-5">
            <div>
              <h1 className="text-2xl font-semibold text-ink">{t(locale, "finalRosterMatrix")}</h1>
              <p className="mt-2 max-w-3xl text-sm text-slate-600">{t(locale, "finalRosterHelp")}</p>
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
              <label className="grid gap-1 text-sm font-medium text-slate-700">
                {t(locale, "periodId")}
                <input className={`${inputClass} w-24`} value={periodId} onChange={(event) => setPeriodId(event.target.value)} />
              </label>
              <button
                className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white"
                onClick={loadRoster}
                type="button"
              >
                <RefreshCw size={17} />
                {t(locale, "loadRoster")}
              </button>
              <button
                className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-mint px-4 text-sm font-semibold text-ink"
                onClick={manualSave}
                title={t(locale, "saveNowHint")}
                type="button"
              >
                <Save size={17} />
                {t(locale, "saveNow")}
              </button>
              <a
                className="inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700"
                href={`${API_BASE_URL}/api/v1/exports/roster-matrix/${activePeriodId}.csv`}
              >
                <Download size={17} />
                {t(locale, "rosterCsvExport")}
              </a>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-3 text-sm">
            {savingAssignments > 0 ? <p className="text-slate-600">{t(locale, "saving")}</p> : null}
            {message ? <p className="text-emerald-700">{message}</p> : null}
          </div>
        </Card>
      ) : (
        <div className="flex flex-wrap gap-3 text-sm">
          {savingAssignments > 0 ? <p className="text-slate-600">{t(locale, "saving")}</p> : null}
          {message ? <p className="text-emerald-700">{message}</p> : null}
        </div>
      )}

      {matrix ? (
        matrix.shift_types.length > 0 ? (
          <>
            <DesktopRosterMatrix
              matrix={matrix}
              slotMap={slotMap}
              assignmentMap={assignmentMap}
              planningCellMap={planningCellMap}
              onSave={saveAssignment}
              locale={locale}
            />
            <MobileRosterMatrix
              matrix={matrix}
              slotMap={slotMap}
              assignmentMap={assignmentMap}
              planningCellMap={planningCellMap}
              onSave={saveAssignment}
              locale={locale}
            />
          </>
        ) : (
          <Card>
            <p className="text-sm text-slate-500">{t(locale, "noShiftTypesForRoster")}</p>
          </Card>
        )
      ) : (
        <Card>
          <p className="text-sm text-slate-500">{t(locale, "noData")}</p>
        </Card>
      )}
    </div>
  );
}

function DesktopRosterMatrix({
  matrix,
  slotMap,
  assignmentMap,
  planningCellMap,
  onSave,
  locale
}: {
  matrix: RosterMatrix;
  slotMap: Map<string, RosterSlot>;
  assignmentMap: Map<number, RosterSlotAssignment>;
  planningCellMap: Map<string, PlanningCell>;
  onSave: (rosterSlotId: number, doctorId: number | "") => Promise<void>;
  locale: Locale;
}) {
  return (
    <div className="hidden overflow-auto rounded-lg border border-slate-200 bg-white shadow-soft lg:block">
      <table className="min-w-full border-separate border-spacing-0 text-sm">
        <thead>
          <tr>
            <th className="sticky left-0 top-0 z-20 border-b border-r border-slate-200 bg-white p-3 text-left font-semibold text-slate-700">
              {t(locale, "date")}
            </th>
            {matrix.shift_types.map((shiftType) => (
              <th key={shiftType.id} className="sticky top-0 z-10 min-w-56 border-b border-slate-200 bg-white p-3 text-left font-semibold text-slate-700">
                <span className="block text-slate-800">{shiftLabel(locale, shiftType)}</span>
                <span className="block text-xs font-normal text-slate-500">{shiftType.starts_at.slice(0, 5)}-{shiftType.ends_at.slice(0, 5)}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.days.map((day) => (
            <tr key={day.date}>
              <td className="sticky left-0 z-10 border-r border-slate-200 bg-white p-3 font-medium text-slate-700">
                {formatDate(locale, day.date)}
              </td>
              {matrix.shift_types.map((shiftType) => {
                const slot = slotMap.get(`${day.date}:${shiftType.id}:1`);
                return (
                  <td key={shiftType.id} className="border-b border-slate-100 p-2 align-top">
                    {slot ? (
                      <RosterCell
                        slot={slot}
                        doctors={matrix.doctors}
                        assignment={assignmentMap.get(slot.id)}
                        planningCellMap={planningCellMap}
                        onSave={onSave}
                        locale={locale}
                      />
                    ) : null}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MobileRosterMatrix({
  matrix,
  slotMap,
  assignmentMap,
  planningCellMap,
  onSave,
  locale
}: {
  matrix: RosterMatrix;
  slotMap: Map<string, RosterSlot>;
  assignmentMap: Map<number, RosterSlotAssignment>;
  planningCellMap: Map<string, PlanningCell>;
  onSave: (rosterSlotId: number, doctorId: number | "") => Promise<void>;
  locale: Locale;
}) {
  return (
    <div className="grid gap-4 lg:hidden">
      {matrix.days.map((day) => (
        <Card key={day.date}>
          <h2 className="mb-3 text-base font-semibold text-ink">{formatDate(locale, day.date)}</h2>
          <div className="grid gap-3">
            {matrix.shift_types.map((shiftType) => {
              const slot = slotMap.get(`${day.date}:${shiftType.id}:1`);
              return (
                <div key={shiftType.id} className="grid gap-2 rounded-lg border border-slate-200 p-3">
                  <p className="text-sm font-semibold text-slate-700">{shiftLabel(locale, shiftType)}</p>
                  {slot ? (
                    <RosterCell
                      slot={slot}
                      doctors={matrix.doctors}
                      assignment={assignmentMap.get(slot.id)}
                      planningCellMap={planningCellMap}
                      onSave={onSave}
                      locale={locale}
                    />
                  ) : null}
                </div>
              );
            })}
          </div>
        </Card>
      ))}
    </div>
  );
}

function RosterCell({
  slot,
  doctors,
  assignment,
  planningCellMap,
  onSave,
  locale
}: {
  slot: RosterSlot;
  doctors: Doctor[];
  assignment?: RosterSlotAssignment;
  planningCellMap: Map<string, PlanningCell>;
  onSave: (rosterSlotId: number, doctorId: number | "") => Promise<void>;
  locale: Locale;
}) {
  const [doctorId, setDoctorId] = useState<number | "">(assignment?.doctor_id ?? "");
  const planningCell = doctorId ? planningCellMap.get(`${slot.slot_date}:${doctorId}`) : undefined;
  const status = planningCell?.status;
  const meta = status ? STATUS_META[status] : undefined;
  const hasConflict = status ? UNAVAILABLE_STATUSES.has(status) : false;

  useEffect(() => {
    setDoctorId(assignment?.doctor_id ?? "");
  }, [assignment?.doctor_id]);

  return (
    <div className={`grid gap-2 rounded-lg p-1 ${hasConflict ? "bg-rose-50 ring-2 ring-rose-300" : ""}`}>
      <select
        className={`min-w-0 rounded-lg border bg-white px-2 py-2 text-xs font-medium ${
          hasConflict ? "border-rose-300 text-rose-950" : "border-slate-200"
        }`}
        value={doctorId}
        onChange={(event) => {
          const nextDoctorId = event.target.value ? Number(event.target.value) : "";
          setDoctorId(nextDoctorId);
          void onSave(slot.id, nextDoctorId);
        }}
      >
        <option value="">{t(locale, "emptyValue")}</option>
        {doctors.map((doctor) => (
          <option key={doctor.id} value={doctor.id}>
            {doctor.name}
          </option>
        ))}
      </select>
      {meta ? (
        <div className="flex flex-wrap items-center gap-1">
          {hasConflict ? <span className="text-xs font-semibold text-rose-700">{t(locale, "conflict")}</span> : null}
          <span className={`inline-flex w-fit rounded-full px-2 py-1 text-xs font-semibold ring-1 ${meta.color}`}>
            {t(locale, meta.label)}
          </span>
        </div>
      ) : null}
    </div>
  );
}
