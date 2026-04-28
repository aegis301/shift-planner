"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Download, MessageSquareText, RefreshCw, Save, X } from "lucide-react";
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

type MatrixDoctor = {
  id: number;
  name: string;
  email: string;
  employment_percentage: number;
};

type MatrixDay = {
  date: string;
  weekday: string;
};

type PlanningCell = {
  id: number;
  planning_period_id: number;
  doctor_id: number;
  cell_date: string;
  status: PlanningStatus;
  comment: string | null;
};

type PlanningMatrix = {
  planning_period: { id: number; year: number; month: number; status: string };
  doctors: MatrixDoctor[];
  days: MatrixDay[];
  cells: PlanningCell[];
};

type PlanningPeriod = {
  id: number;
  year: number;
  month: number;
  status: string;
};

type DoctorPeriodNote = {
  id: number;
  planning_period_id: number;
  doctor_id: number;
  source_text: string | null;
  summary: string | null;
};

const STATUSES: Array<{ value: PlanningStatus; label: TranslationKey; color: string }> = [
  { value: "dienstwunsch", label: "dienstwunsch", color: "bg-sky-100 text-sky-800 ring-sky-200" },
  { value: "urlaub", label: "urlaub", color: "bg-rose-100 text-rose-800 ring-rose-200" },
  { value: "kein_dienst", label: "keinDienst", color: "bg-orange-100 text-orange-800 ring-orange-200" },
  { value: "forschung", label: "forschung", color: "bg-violet-100 text-violet-800 ring-violet-200" },
  { value: "lehre", label: "lehre", color: "bg-amber-100 text-amber-800 ring-amber-200" },
  { value: "frei", label: "frei", color: "bg-slate-100 text-slate-700 ring-slate-200" },
  { value: "tagdienst", label: "tagdienst", color: "bg-emerald-100 text-emerald-800 ring-emerald-200" },
  { value: "nachtdienst", label: "nachtdienst", color: "bg-indigo-100 text-indigo-800 ring-indigo-200" },
  { value: "spaetdienst", label: "spaetdienst", color: "bg-teal-100 text-teal-800 ring-teal-200" },
  { value: "rufdienst", label: "rufdienst", color: "bg-coral/15 text-red-800 ring-coral/30" }
];

function statusMeta(status: PlanningStatus | "") {
  return STATUSES.find((item) => item.value === status);
}

function formatDate(locale: Locale, value: string) {
  return new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-GB", {
    weekday: "short",
    day: "2-digit",
    month: "2-digit"
  }).format(new Date(`${value}T12:00:00`));
}

export function MatrixEditor({
  periodId: controlledPeriodId,
  compact = false,
  onChanged
}: {
  periodId?: string;
  compact?: boolean;
  onChanged?: () => void | Promise<void>;
} = {}) {
  const { locale } = useLocale();
  const currentDate = new Date();
  const [periodId, setPeriodId] = useState("1");
  const [newYear, setNewYear] = useState(String(currentDate.getFullYear()));
  const [newMonth, setNewMonth] = useState(String(currentDate.getMonth() + 1));
  const [matrix, setMatrix] = useState<PlanningMatrix | null>(null);
  const [activeDoctorId, setActiveDoctorId] = useState<number | null>(null);
  const [notes, setNotes] = useState<DoctorPeriodNote[]>([]);
  const [noteDoctor, setNoteDoctor] = useState<MatrixDoctor | null>(null);
  const [sourceText, setSourceText] = useState("");
  const [summary, setSummary] = useState("");
  const [message, setMessage] = useState("");
  const [savingCells, setSavingCells] = useState(0);

  const cellMap = useMemo(() => {
    const map = new Map<string, PlanningCell>();
    matrix?.cells.forEach((cell) => map.set(`${cell.cell_date}:${cell.doctor_id}`, cell));
    return map;
  }, [matrix]);

  const loadMatrixById = useCallback(async (nextPeriodId: string) => {
    const next = await apiFetch<PlanningMatrix>(`/api/v1/matrix/${nextPeriodId}`);
    const nextNotes = await apiFetch<DoctorPeriodNote[]>(`/api/v1/matrix/${nextPeriodId}/notes`);
    setMatrix(next);
    setNotes(nextNotes);
    setActiveDoctorId(next.doctors[0]?.id ?? null);
  }, []);

  const activePeriodId = controlledPeriodId ?? periodId;

  const loadMatrix = useCallback(async () => {
    await loadMatrixById(activePeriodId);
  }, [activePeriodId, loadMatrixById]);

  async function manualSave() {
    await loadMatrix();
    setMessage(t(locale, "saved"));
  }

  useEffect(() => {
    if (controlledPeriodId) {
      void loadMatrixById(controlledPeriodId);
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
      await loadMatrixById(nextPeriodId);
    }

    void loadLatestPeriod();
  }, [controlledPeriodId, loadMatrixById]);

  async function createAndLoadPeriod(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const period = await apiFetch<PlanningPeriod>("/api/v1/planning-periods", {
      method: "POST",
      body: JSON.stringify({ year: Number(newYear), month: Number(newMonth) })
    });
    const nextPeriodId = String(period.id);
    setPeriodId(nextPeriodId);
    await loadMatrixById(nextPeriodId);
    setMessage(`${t(locale, "saved")}: ${t(locale, "periodId")} ${nextPeriodId}`);
  }

  useEffect(() => {
    const doctorId = noteDoctor?.id ?? activeDoctorId;
    const note = notes.find((item) => item.doctor_id === doctorId);
    setSourceText(note?.source_text ?? "");
    setSummary(note?.summary ?? "");
  }, [activeDoctorId, noteDoctor?.id, notes]);

  async function saveCell(doctorId: number, cellDate: string, status: PlanningStatus | "", comment?: string | null) {
    setSavingCells((count) => count + 1);
    try {
      if (!status) {
        await apiFetch(`/api/v1/matrix/${activePeriodId}/cells/clear`, {
          method: "POST",
          body: JSON.stringify({ doctor_id: doctorId, cell_date: cellDate })
        });
      } else {
        await apiFetch(`/api/v1/matrix/${activePeriodId}/cells`, {
          method: "PUT",
          body: JSON.stringify({ doctor_id: doctorId, cell_date: cellDate, status, comment: comment ?? null })
        });
      }
      setMessage(t(locale, "autosaved"));
      await onChanged?.();
    } finally {
      setSavingCells((count) => Math.max(0, count - 1));
    }
  }

  async function saveNote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const doctorId = noteDoctor?.id ?? activeDoctorId;
    if (!doctorId) return;
    await apiFetch(`/api/v1/matrix/${activePeriodId}/notes`, {
      method: "PUT",
      body: JSON.stringify({ doctor_id: doctorId, source_text: sourceText, summary })
    });
    setNotes(await apiFetch<DoctorPeriodNote[]>(`/api/v1/matrix/${activePeriodId}/notes`));
    setMessage(t(locale, "saved"));
    await onChanged?.();
  }

  return (
    <div className="grid gap-5">
      {!compact ? (
        <Card>
          <div className="grid gap-5">
            <div>
              <h1 className="text-2xl font-semibold text-ink">{t(locale, "matrixEditor")}</h1>
              <p className="mt-2 max-w-3xl text-sm text-slate-600">{t(locale, "matrixHelp")}</p>
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
                onClick={loadMatrix}
              >
                <RefreshCw size={17} />
                {t(locale, "loadMatrix")}
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
                href={`${API_BASE_URL}/api/v1/exports/matrix/${activePeriodId}.csv`}
              >
                <Download size={17} />
                {t(locale, "matrixCsvExport")}
              </a>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-3 text-sm">
            {savingCells > 0 ? <p className="text-slate-600">{t(locale, "saving")}</p> : null}
            {message ? <p className="text-emerald-700">{message}</p> : null}
          </div>
        </Card>
      ) : (
        <div className="flex flex-wrap gap-3 text-sm">
          {savingCells > 0 ? <p className="text-slate-600">{t(locale, "saving")}</p> : null}
          {message ? <p className="text-emerald-700">{message}</p> : null}
        </div>
      )}

      {matrix ? (
        <>
          <DesktopMatrix matrix={matrix} cellMap={cellMap} onSave={saveCell} locale={locale} onOpenNote={setNoteDoctor} />
          <MobileMatrix matrix={matrix} cellMap={cellMap} onSave={saveCell} locale={locale} onOpenNote={setNoteDoctor} />
          <DoctorNoteModal
            doctor={noteDoctor}
            sourceText={sourceText}
            summary={summary}
            onSourceTextChange={setSourceText}
            onSummaryChange={setSummary}
            onClose={() => setNoteDoctor(null)}
            onSubmit={saveNote}
            locale={locale}
          />
        </>
      ) : (
        <Card>
          <p className="text-sm text-slate-500">{t(locale, "noData")}</p>
        </Card>
      )}
    </div>
  );
}

function DesktopMatrix({
  matrix,
  cellMap,
  onSave,
  onOpenNote,
  locale
}: {
  matrix: PlanningMatrix;
  cellMap: Map<string, PlanningCell>;
  onSave: (doctorId: number, cellDate: string, status: PlanningStatus | "", comment?: string | null) => Promise<void>;
  onOpenNote: (doctor: MatrixDoctor) => void;
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
            {matrix.doctors.map((doctor) => (
              <th key={doctor.id} className="sticky top-0 z-10 min-w-52 border-b border-slate-200 bg-white p-3 text-left font-semibold text-slate-700">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate">{doctor.name}</span>
                  <button
                    className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-coral shadow-sm hover:bg-coral/10"
                    onClick={() => onOpenNote(doctor)}
                    title={t(locale, "doctorPeriodNotes")}
                    type="button"
                  >
                    <MessageSquareText aria-hidden size={16} />
                  </button>
                </div>
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
              {matrix.doctors.map((doctor) => {
                const cell = cellMap.get(`${day.date}:${doctor.id}`);
                return (
                  <td key={doctor.id} className="border-b border-slate-100 p-2 align-top">
                    <MatrixCell cell={cell} doctorId={doctor.id} cellDate={day.date} onSave={onSave} locale={locale} />
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

function MobileMatrix({
  matrix,
  cellMap,
  onSave,
  onOpenNote,
  locale
}: {
  matrix: PlanningMatrix;
  cellMap: Map<string, PlanningCell>;
  onSave: (doctorId: number, cellDate: string, status: PlanningStatus | "", comment?: string | null) => Promise<void>;
  onOpenNote: (doctor: MatrixDoctor) => void;
  locale: Locale;
}) {
  return (
    <div className="grid gap-4 lg:hidden">
      {matrix.days.map((day) => (
        <Card key={day.date}>
          <h2 className="mb-3 text-base font-semibold text-ink">{formatDate(locale, day.date)}</h2>
          <div className="grid gap-3">
            {matrix.doctors.map((doctor) => (
              <div key={doctor.id} className="grid gap-2 rounded-lg border border-slate-200 p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-slate-700">{doctor.name}</p>
                  <button
                    className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-coral shadow-sm"
                    onClick={() => onOpenNote(doctor)}
                    title={t(locale, "doctorPeriodNotes")}
                    type="button"
                  >
                    <MessageSquareText aria-hidden size={16} />
                  </button>
                </div>
                <MatrixCell
                  cell={cellMap.get(`${day.date}:${doctor.id}`)}
                  doctorId={doctor.id}
                  cellDate={day.date}
                  onSave={onSave}
                  locale={locale}
                />
              </div>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}

function DoctorNoteModal({
  doctor,
  sourceText,
  summary,
  onSourceTextChange,
  onSummaryChange,
  onClose,
  onSubmit,
  locale
}: {
  doctor: MatrixDoctor | null;
  sourceText: string;
  summary: string;
  onSourceTextChange: (value: string) => void;
  onSummaryChange: (value: string) => void;
  onClose: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  locale: Locale;
}) {
  if (!doctor) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 px-4 py-6 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="doctor-note-title">
      <div className="max-h-[90vh] w-full max-w-3xl overflow-auto rounded-xl bg-white shadow-soft ring-1 ring-slate-200">
        <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div>
            <h2 id="doctor-note-title" className="text-lg font-semibold text-ink">{doctor.name}</h2>
            <p className="mt-1 text-sm text-slate-600">{t(locale, "doctorPeriodNotes")}</p>
          </div>
          <button
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 shadow-sm hover:bg-slate-50"
            onClick={onClose}
            title={t(locale, "close")}
            type="button"
          >
            <X aria-hidden size={17} />
          </button>
        </div>
        <form className="grid gap-4 p-5" onSubmit={onSubmit}>
          <Field label={t(locale, "sourceEmail")}>
            <textarea
              className="min-h-48 rounded-lg border border-slate-200 p-3 text-sm"
              value={sourceText}
              onChange={(event) => onSourceTextChange(event.target.value)}
            />
          </Field>
          <Field label={t(locale, "summary")}>
            <textarea
              className="min-h-28 rounded-lg border border-slate-200 p-3 text-sm"
              value={summary}
              onChange={(event) => onSummaryChange(event.target.value)}
            />
          </Field>
          <div className="flex flex-wrap justify-end gap-2">
            <button
              className="inline-flex h-11 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700"
              onClick={onClose}
              type="button"
            >
              {t(locale, "close")}
            </button>
            <button className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white">
              <Save size={17} />
              {t(locale, "save")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function MatrixCell({
  cell,
  doctorId,
  cellDate,
  onSave,
  locale
}: {
  cell?: PlanningCell;
  doctorId: number;
  cellDate: string;
  onSave: (doctorId: number, cellDate: string, status: PlanningStatus | "", comment?: string | null) => Promise<void>;
  locale: Locale;
}) {
  const [status, setStatus] = useState<PlanningStatus | "">(cell?.status ?? "");
  const [comment, setComment] = useState(cell?.comment ?? "");
  const meta = statusMeta(status);
  const [isDirty, setIsDirty] = useState(false);

  useEffect(() => {
    setStatus(cell?.status ?? "");
    setComment(cell?.comment ?? "");
    setIsDirty(false);
  }, [cell?.status, cell?.comment]);

  useEffect(() => {
    if (!isDirty) {
      return;
    }
    const timeout = window.setTimeout(() => {
      void onSave(doctorId, cellDate, status, comment);
      setIsDirty(false);
    }, 650);
    return () => window.clearTimeout(timeout);
  }, [cellDate, comment, doctorId, isDirty, onSave, status]);

  return (
    <div className="grid gap-2">
      <select
        className="min-w-0 rounded-lg border border-slate-200 bg-white px-2 py-2 text-xs font-medium"
        value={status}
        onChange={(event) => {
          const nextStatus = event.target.value as PlanningStatus | "";
          setStatus(nextStatus);
          setIsDirty(false);
          void onSave(doctorId, cellDate, nextStatus, comment);
        }}
      >
        <option value="">{t(locale, "emptyValue")}</option>
        {STATUSES.map((item) => (
          <option key={item.value} value={item.value}>
            {t(locale, item.label)}
          </option>
        ))}
      </select>
      {meta ? (
        <span className={`inline-flex w-fit rounded-full px-2 py-1 text-xs font-semibold ring-1 ${meta.color}`}>
          {t(locale, meta.label)}
        </span>
      ) : null}
      <textarea
        className="min-h-16 resize-y rounded-lg border border-slate-200 p-2 text-xs"
        placeholder={t(locale, "cellComment")}
        value={comment}
        onChange={(event) => {
          setComment(event.target.value);
          setIsDirty(true);
        }}
        onBlur={() => {
          if (isDirty) {
            void onSave(doctorId, cellDate, status, comment);
            setIsDirty(false);
          }
        }}
      />
    </div>
  );
}
