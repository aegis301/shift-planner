"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Download, MessageSquareText, RefreshCw, Save, X } from "lucide-react";
import { API_BASE_URL, apiFetch } from "@/lib/api";
import { t, type Locale, type TranslationKey } from "@/lib/i18n";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";

type PlanningStatus = "urlaub" | "forschung" | "lehre" | "frei";

type PlanningShiftIntentKind = "wish" | "no_go";

type TemplateSlotDay = { cell_date: string; shift_template_id: number };

type MatrixShiftTemplate = {
  id: number;
  code: string;
  name_de: string;
  name_en: string;
  category: string;
  display_order: number;
  is_active: boolean;
};

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
  status: string;
  comment: string | null;
};

type MatrixShiftIntent = {
  id: number;
  planning_period_id: number;
  doctor_id: number;
  cell_date: string;
  shift_group_id: number;
  shift_template_id: number;
  kind: PlanningShiftIntentKind;
  source: string;
};

type PlanningMatrix = {
  planning_period: { id: number; year: number; month: number; status: string };
  doctors: MatrixDoctor[];
  days: MatrixDay[];
  cells: PlanningCell[];
  shift_templates: MatrixShiftTemplate[];
  shift_intents: MatrixShiftIntent[];
  template_slot_days: TemplateSlotDay[];
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
  { value: "urlaub", label: "urlaub", color: "bg-rose-100 text-rose-800 ring-rose-200" },
  { value: "forschung", label: "forschung", color: "bg-violet-100 text-violet-800 ring-violet-200" },
  { value: "lehre", label: "lehre", color: "bg-amber-100 text-amber-800 ring-amber-200" },
  { value: "frei", label: "frei", color: "bg-slate-100 text-slate-700 ring-slate-200" }
];

function statusMeta(status: PlanningStatus | "") {
  return STATUSES.find((item) => item.value === status);
}

function normalizePlanningStatus(value: string | undefined): PlanningStatus | "" {
  if (!value) {
    return "";
  }
  if (STATUSES.some((item) => item.value === value)) {
    return value as PlanningStatus;
  }
  return "";
}

function templateIdsForDate(matrix: PlanningMatrix, cellDate: string): number[] {
  const ids = new Set<number>();
  for (const row of matrix.template_slot_days ?? []) {
    if (row.cell_date === cellDate) {
      ids.add(row.shift_template_id);
    }
  }
  return [...ids].sort((a, b) => a - b);
}

function templateLabel(matrix: PlanningMatrix, templateId: number, locale: Locale): string {
  const template = matrix.shift_templates?.find((item) => item.id === templateId);
  if (!template) {
    return `#${templateId}`;
  }
  return locale === "de" ? template.name_de : template.name_en;
}

function formatDate(locale: Locale, value: string) {
  return new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-GB", {
    weekday: "short",
    day: "2-digit",
    month: "2-digit"
  }).format(new Date(`${value}T12:00:00`));
}

function shiftGroupQuery(shiftGroupId?: string) {
  if (!shiftGroupId) {
    return "";
  }
  return `?shift_group_id=${encodeURIComponent(shiftGroupId)}`;
}

export function MatrixEditor({
  periodId: controlledPeriodId,
  compact = false,
  shiftGroupId,
  onChanged
}: {
  periodId?: string;
  compact?: boolean;
  shiftGroupId?: string;
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

  const groupQuery = useMemo(() => shiftGroupQuery(shiftGroupId), [shiftGroupId]);

  const cellMap = useMemo(() => {
    const map = new Map<string, PlanningCell>();
    matrix?.cells.forEach((cell) => map.set(`${cell.cell_date}:${cell.doctor_id}`, cell));
    return map;
  }, [matrix]);

  const loadMatrixById = useCallback(async (nextPeriodId: string) => {
    const next = await apiFetch<PlanningMatrix>(`/api/v1/matrix/${nextPeriodId}${groupQuery}`);
    const nextNotes = await apiFetch<DoctorPeriodNote[]>(`/api/v1/matrix/${nextPeriodId}/notes${groupQuery}`);
    setMatrix({
      ...next,
      shift_templates: next.shift_templates ?? [],
      shift_intents: next.shift_intents ?? [],
      template_slot_days: next.template_slot_days ?? []
    });
    setNotes(nextNotes);
    setActiveDoctorId(next.doctors[0]?.id ?? null);
  }, [groupQuery]);

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
  }, [controlledPeriodId, loadMatrixById, groupQuery]);

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

  const saveIntent = useCallback(
    async (doctorId: number, cellDate: string, templateId: number, kind: PlanningShiftIntentKind | null) => {
      if (!shiftGroupId) {
        return;
      }
      setSavingCells((count) => count + 1);
      try {
        await apiFetch(`/api/v1/matrix/${activePeriodId}/shift-intents/bulk`, {
          method: "PUT",
          body: JSON.stringify({
            intents: [
              {
                doctor_id: doctorId,
                cell_date: cellDate,
                shift_group_id: Number(shiftGroupId),
                shift_template_id: templateId,
                kind
              }
            ]
          })
        });
        setMessage(t(locale, "autosaved"));
        await loadMatrixById(activePeriodId);
        await onChanged?.();
      } finally {
        setSavingCells((count) => Math.max(0, count - 1));
      }
    },
    [activePeriodId, loadMatrixById, locale, onChanged, shiftGroupId]
  );

  async function saveNote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const doctorId = noteDoctor?.id ?? activeDoctorId;
    if (!doctorId) return;
    await apiFetch(`/api/v1/matrix/${activePeriodId}/notes`, {
      method: "PUT",
      body: JSON.stringify({ doctor_id: doctorId, source_text: sourceText, summary })
    });
    setNotes(await apiFetch<DoctorPeriodNote[]>(`/api/v1/matrix/${activePeriodId}/notes${groupQuery}`));
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
                href={`${API_BASE_URL}/api/v1/exports/matrix/${activePeriodId}.csv${groupQuery}`}
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
          {compact ? (
            <PlanningDenseMatrix
              matrix={matrix}
              cellMap={cellMap}
              onSave={saveCell}
              locale={locale}
              onOpenNote={setNoteDoctor}
              shiftGroupId={shiftGroupId}
              onSaveIntent={saveIntent}
            />
          ) : (
            <>
              <DesktopMatrix
                matrix={matrix}
                cellMap={cellMap}
                onSave={saveCell}
                locale={locale}
                onOpenNote={setNoteDoctor}
                shiftGroupId={shiftGroupId}
                onSaveIntent={saveIntent}
              />
              <MobileMatrix
                matrix={matrix}
                cellMap={cellMap}
                onSave={saveCell}
                locale={locale}
                onOpenNote={setNoteDoctor}
                shiftGroupId={shiftGroupId}
                onSaveIntent={saveIntent}
              />
            </>
          )}
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

function PlanningDenseMatrix({
  matrix,
  cellMap,
  onSave,
  onOpenNote,
  locale,
  shiftGroupId,
  onSaveIntent
}: {
  matrix: PlanningMatrix;
  cellMap: Map<string, PlanningCell>;
  onSave: (doctorId: number, cellDate: string, status: PlanningStatus | "", comment?: string | null) => Promise<void>;
  onOpenNote: (doctor: MatrixDoctor) => void;
  locale: Locale;
  shiftGroupId?: string;
  onSaveIntent: (doctorId: number, cellDate: string, templateId: number, kind: PlanningShiftIntentKind | null) => Promise<void>;
}) {
  return (
    <div className="overflow-auto rounded-lg border border-slate-200 bg-white shadow-soft">
      <table className="min-w-max border-separate border-spacing-0 text-sm">
        <thead>
          <tr>
            <th className="sticky left-0 top-0 z-30 border-b border-r border-slate-200 bg-white p-2 text-left text-xs font-semibold text-slate-700">
              {t(locale, "date")}
            </th>
            {matrix.doctors.map((doctor) => (
              <th key={doctor.id} className="sticky top-0 z-20 min-w-[10rem] border-b border-slate-200 bg-white p-2 text-left align-bottom">
                <div className="flex max-w-[12rem] items-start justify-between gap-1">
                  <span className="truncate text-xs font-semibold text-ink">{doctor.name}</span>
                  <button
                    className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-coral shadow-sm hover:bg-coral/10"
                    onClick={() => onOpenNote(doctor)}
                    title={t(locale, "doctorPeriodNotes")}
                    type="button"
                  >
                    <MessageSquareText aria-hidden size={14} />
                  </button>
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.days.map((day) => (
            <tr key={day.date}>
              <td className="sticky left-0 z-10 border-r border-slate-200 bg-white p-2 align-top text-xs font-medium text-slate-800">
                {formatDate(locale, day.date)}
              </td>
              {matrix.doctors.map((doctor) => (
                <td key={doctor.id} className="border-b border-slate-100 p-1.5 align-top">
                  <MatrixCell
                    dense
                    matrix={matrix}
                    cell={cellMap.get(`${day.date}:${doctor.id}`)}
                    doctorId={doctor.id}
                    cellDate={day.date}
                    onSave={onSave}
                    locale={locale}
                    shiftGroupId={shiftGroupId}
                    onSaveIntent={onSaveIntent}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DesktopMatrix({
  matrix,
  cellMap,
  onSave,
  onOpenNote,
  locale,
  shiftGroupId,
  onSaveIntent
}: {
  matrix: PlanningMatrix;
  cellMap: Map<string, PlanningCell>;
  onSave: (doctorId: number, cellDate: string, status: PlanningStatus | "", comment?: string | null) => Promise<void>;
  onOpenNote: (doctor: MatrixDoctor) => void;
  locale: Locale;
  shiftGroupId?: string;
  onSaveIntent: (doctorId: number, cellDate: string, templateId: number, kind: PlanningShiftIntentKind | null) => Promise<void>;
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
                    <MatrixCell
                      matrix={matrix}
                      cell={cell}
                      doctorId={doctor.id}
                      cellDate={day.date}
                      onSave={onSave}
                      locale={locale}
                      shiftGroupId={shiftGroupId}
                      onSaveIntent={onSaveIntent}
                    />
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
  locale,
  shiftGroupId,
  onSaveIntent
}: {
  matrix: PlanningMatrix;
  cellMap: Map<string, PlanningCell>;
  onSave: (doctorId: number, cellDate: string, status: PlanningStatus | "", comment?: string | null) => Promise<void>;
  onOpenNote: (doctor: MatrixDoctor) => void;
  locale: Locale;
  shiftGroupId?: string;
  onSaveIntent: (doctorId: number, cellDate: string, templateId: number, kind: PlanningShiftIntentKind | null) => Promise<void>;
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
                  matrix={matrix}
                  cell={cellMap.get(`${day.date}:${doctor.id}`)}
                  doctorId={doctor.id}
                  cellDate={day.date}
                  onSave={onSave}
                  locale={locale}
                  shiftGroupId={shiftGroupId}
                  onSaveIntent={onSaveIntent}
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
  matrix,
  cell,
  doctorId,
  cellDate,
  onSave,
  locale,
  dense = false,
  shiftGroupId,
  onSaveIntent
}: {
  matrix: PlanningMatrix;
  cell?: PlanningCell;
  doctorId: number;
  cellDate: string;
  onSave: (doctorId: number, cellDate: string, status: PlanningStatus | "", comment?: string | null) => Promise<void>;
  locale: Locale;
  dense?: boolean;
  shiftGroupId?: string;
  onSaveIntent: (doctorId: number, cellDate: string, templateId: number, kind: PlanningShiftIntentKind | null) => Promise<void>;
}) {
  const [status, setStatus] = useState<PlanningStatus | "">(() => normalizePlanningStatus(cell?.status));
  const [comment, setComment] = useState(cell?.comment ?? "");
  const meta = statusMeta(status);
  const [isDirty, setIsDirty] = useState(false);
  const intentMap = useMemo(() => {
    const map = new Map<string, PlanningShiftIntentKind>();
    for (const row of matrix.shift_intents ?? []) {
      if (row.doctor_id !== doctorId || row.cell_date !== cellDate) {
        continue;
      }
      map.set(`${cellDate}:${doctorId}:${row.shift_template_id}`, row.kind);
    }
    return map;
  }, [matrix.shift_intents, doctorId, cellDate]);
  const templateIds = useMemo(() => templateIdsForDate(matrix, cellDate), [matrix, cellDate]);
  const showIntents = Boolean(shiftGroupId && matrix.shift_templates?.length && templateIds.length);

  useEffect(() => {
    setStatus(normalizePlanningStatus(cell?.status));
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
    <div className={`grid ${dense ? "gap-1" : "gap-2"}`}>
      <select
        className={`min-w-0 rounded-lg border border-slate-200 bg-white font-medium ${dense ? "px-1.5 py-1.5 text-[0.7rem]" : "px-2 py-2 text-xs"}`}
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
        <span
          className={`inline-flex w-fit rounded-full font-semibold ring-1 ${meta.color} ${dense ? "px-1.5 py-0.5 text-[0.65rem]" : "px-2 py-1 text-xs"}`}
        >
          {t(locale, meta.label)}
        </span>
      ) : null}
      <textarea
        className={`resize-y rounded-lg border border-slate-200 text-xs ${dense ? "min-h-12 p-1.5" : "min-h-16 p-2"}`}
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
      {showIntents ? (
        <div className={`grid gap-1.5 ${dense ? "pt-0.5" : "pt-1"}`}>
          <p className={`font-medium text-slate-600 ${dense ? "text-[0.6rem]" : "text-[0.65rem]"}`}>{t(locale, "shiftIntentsHeading")}</p>
          {templateIds.map((templateId) => {
            const current = intentMap.get(`${cellDate}:${doctorId}:${templateId}`);
            const label = templateLabel(matrix, templateId, locale);
            return (
              <div key={templateId} className="flex flex-wrap items-center gap-1">
                <span className={`max-w-[9rem] truncate text-slate-600 ${dense ? "text-[0.6rem]" : "text-xs"}`}>{label}</span>
                <button
                  type="button"
                  title={t(locale, "wish")}
                  className={`rounded-md font-semibold ring-1 ring-sky-200 ${
                    current === "wish" ? "bg-sky-200 text-sky-950" : "bg-sky-50 text-sky-900"
                  } ${dense ? "px-1 py-0.5 text-[0.6rem]" : "px-1.5 py-0.5 text-[0.65rem]"}`}
                  onClick={() => void onSaveIntent(doctorId, cellDate, templateId, current === "wish" ? null : "wish")}
                >
                  {t(locale, "wishShort")}
                </button>
                <button
                  type="button"
                  title={t(locale, "noGo")}
                  className={`rounded-md font-semibold ring-1 ring-rose-200 ${
                    current === "no_go" ? "bg-rose-200 text-rose-950" : "bg-rose-50 text-rose-900"
                  } ${dense ? "px-1 py-0.5 text-[0.6rem]" : "px-1.5 py-0.5 text-[0.65rem]"}`}
                  onClick={() => void onSaveIntent(doctorId, cellDate, templateId, current === "no_go" ? null : "no_go")}
                >
                  {t(locale, "noGoShort")}
                </button>
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
