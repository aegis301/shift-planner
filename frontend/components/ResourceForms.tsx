"use client";

import { FormEvent, ReactNode, useCallback, useEffect, useState } from "react";
import { Plus, RefreshCw } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { t, type Locale, type TranslationKey } from "@/lib/i18n";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";

type AnyRecord = Record<string, unknown>;

const FIELD_LABEL_MAP: Partial<Record<string, TranslationKey>> = {
  id: "id",
  name: "name",
  email: "email",
  employment_percentage: "employment",
  notes: "notes",
  is_active: "isActive",
  created_at: "createdAt",
  code: "code",
  name_de: "germanName",
  name_en: "englishName",
  starts_at: "start",
  ends_at: "end",
  category: "category",
  doctor_id: "doctorId",
  planning_period_id: "planningPeriodId",
  shift_type_id: "shiftTypeId",
  request_date: "requestDate",
  request_type: "requestType",
  note: "note",
  assignment_date: "assignmentDate",
  manual_override: "manualOverride",
  message: "validationMessage",
  severity: "severity",
  assignment_id: "assignmentId",
  request_id: "requestRecordId",
  date: "date",
  details: "details",
  status: "status"
};

const FIELD_PRIORITY = [
  "id",
  "name",
  "message",
  "code",
  "email",
  "severity",
  "request_type",
  "category",
  "employment_percentage",
  "is_active"
];

function sortedRowKeys(keys: string[]): string[] {
  const set = new Set(keys);
  const primary = FIELD_PRIORITY.filter((k) => set.has(k));
  const rest = keys.filter((k) => !FIELD_PRIORITY.includes(k)).sort((a, b) => a.localeCompare(b));
  return [...primary, ...rest];
}

function fieldLabel(locale: Locale, key: string): string {
  const mapped = FIELD_LABEL_MAP[key];
  return mapped ? t(locale, mapped) : key;
}

function formatScalar(locale: Locale, value: unknown): string {
  if (value === null || value === undefined) {
    return t(locale, "emptyValue");
  }
  if (value === "") {
    return t(locale, "emptyValue");
  }
  if (typeof value === "boolean") {
    return value ? t(locale, "yes") : t(locale, "no");
  }
  if (typeof value === "number") {
    return String(value);
  }
  if (typeof value === "string") {
    if (/^\d{4}-\d{2}-\d{2}T/.test(value)) {
      return new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-GB", {
        dateStyle: "medium",
        timeStyle: "short"
      }).format(new Date(value));
    }
    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
      return new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-GB", { dateStyle: "medium" }).format(new Date(`${value}T12:00:00`));
    }
    if (/^\d{2}:\d{2}(:\d{2})?$/.test(value)) {
      return value.slice(0, 5);
    }
    return value;
  }
  return JSON.stringify(value);
}

function formatFieldValue(locale: Locale, value: unknown): ReactNode {
  if (value !== null && typeof value === "object") {
    const text = JSON.stringify(value, null, 2);
    return (
      <pre className="mt-0.5 max-h-36 overflow-auto whitespace-pre-wrap break-words rounded-md bg-slate-100/90 p-2 font-mono text-xs text-slate-700 ring-1 ring-slate-200/80">
        {text}
      </pre>
    );
  }
  return <span className="text-sm font-medium text-ink">{formatScalar(locale, value)}</span>;
}

function cardTitle(row: AnyRecord, locale: Locale): string {
  if (typeof row.name === "string" && row.name.trim()) {
    return row.name;
  }
  const de = row.name_de;
  const en = row.name_en;
  if (typeof de === "string" && de.trim()) {
    if (locale === "de") {
      return de;
    }
    if (typeof en === "string" && en.trim()) {
      return en;
    }
    return de;
  }
  if (typeof en === "string" && en.trim()) {
    return en;
  }
  if (typeof row.message === "string" && row.message.trim()) {
    return row.message;
  }
  if (typeof row.code === "string" && row.code.trim()) {
    return row.code;
  }
  return `${t(locale, "id")} ${formatScalar(locale, row.id)}`;
}

function RecordCard({ row }: { row: AnyRecord }) {
  const { locale } = useLocale();
  const keysAll = Object.keys(row);
  const detailBlock = row.details;
  const keys = sortedRowKeys(keysAll.filter((k) => k !== "details"));
  const hasDetails =
    detailBlock !== null &&
    detailBlock !== undefined &&
    typeof detailBlock === "object" &&
    !Array.isArray(detailBlock) &&
    Object.keys(detailBlock as object).length > 0;

  return (
    <article className="overflow-hidden rounded-xl border border-slate-200/90 bg-white shadow-soft ring-1 ring-slate-100/80">
      <div className="border-b border-mint/25 bg-gradient-to-r from-mint/10 via-white to-sky-50/40 px-4 py-3">
        <h2 className="truncate text-sm font-semibold text-ink">{cardTitle(row, locale)}</h2>
      </div>
      <div className="p-4">
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
          {keys.map((key) => (
            <div key={key} className="min-w-0">
              <dt className="text-[0.65rem] font-semibold uppercase tracking-wide text-slate-500">{fieldLabel(locale, key)}</dt>
              <dd className="mt-1 min-w-0">{formatFieldValue(locale, row[key])}</dd>
            </div>
          ))}
        </dl>
        {hasDetails ? (
          <div className="mt-4 border-t border-slate-100 pt-4">
            <p className="mb-2 text-[0.65rem] font-semibold uppercase tracking-wide text-slate-500">{t(locale, "details")}</p>
            {formatFieldValue(locale, detailBlock)}
          </div>
        ) : null}
      </div>
    </article>
  );
}

function DataList({ rows }: { rows: AnyRecord[] }) {
  const { locale } = useLocale();
  if (!rows.length) {
    return <p className="text-sm text-slate-500">{t(locale, "noData")}</p>;
  }
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {rows.map((row, index) => (
        <RecordCard key={String(row.id ?? index)} row={row} />
      ))}
    </div>
  );
}

export function DoctorForm() {
  const { locale } = useLocale();
  const [rows, setRows] = useState<AnyRecord[]>([]);
  const [message, setMessage] = useState("");

  const refresh = useCallback(async () => {
    setRows(await apiFetch<AnyRecord[]>("/api/v1/doctors"));
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await apiFetch("/api/v1/doctors", {
      method: "POST",
      body: JSON.stringify({
        name: form.get("name"),
        email: form.get("email"),
        employment_percentage: Number(form.get("employment_percentage")),
        notes: form.get("notes")
      })
    });
    setMessage(t(locale, "created"));
    await refresh();
  }

  return (
    <Card>
      <form className="grid gap-4 md:grid-cols-2" onSubmit={submit}>
        <h1 className="md:col-span-2 text-2xl font-semibold text-ink">{t(locale, "addDoctor")}</h1>
        <Field label={t(locale, "name")}><input className={inputClass} name="name" required /></Field>
        <Field label={t(locale, "email")}><input className={inputClass} name="email" type="email" required /></Field>
        <Field label={t(locale, "employment")}><input className={inputClass} name="employment_percentage" type="number" min="1" max="100" defaultValue="100" /></Field>
        <Field label={t(locale, "notes")}><input className={inputClass} name="notes" /></Field>
        <button className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white"><Plus size={17} />{t(locale, "save")}</button>
        <button type="button" onClick={refresh} className="inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold"><RefreshCw size={17} />{t(locale, "refresh")}</button>
      </form>
      {message ? <p className="mt-4 text-sm text-emerald-700">{message}</p> : null}
      <div className="mt-5"><DataList rows={rows} /></div>
    </Card>
  );
}

export function ShiftTypeForm() {
  const { locale } = useLocale();
  const [rows, setRows] = useState<AnyRecord[]>([]);

  const refresh = useCallback(async () => {
    setRows(await apiFetch<AnyRecord[]>("/api/v1/shift-types"));
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await apiFetch("/api/v1/shift-types", {
      method: "POST",
      body: JSON.stringify({
        code: form.get("code"),
        name_de: form.get("name_de"),
        name_en: form.get("name_en"),
        starts_at: form.get("starts_at"),
        ends_at: form.get("ends_at"),
        category: form.get("category")
      })
    });
    await refresh();
  }

  return (
    <Card>
      <form className="grid gap-4 md:grid-cols-2" onSubmit={submit}>
        <h1 className="md:col-span-2 text-2xl font-semibold text-ink">{t(locale, "addShiftType")}</h1>
        <Field label={t(locale, "code")}><input className={inputClass} name="code" required /></Field>
        <Field label={t(locale, "category")}><select className={inputClass} name="category"><option value="day">{t(locale, "day")}</option><option value="night">{t(locale, "night")}</option><option value="on_call">{t(locale, "onCall")}</option><option value="other">{t(locale, "other")}</option></select></Field>
        <Field label={t(locale, "germanName")}><input className={inputClass} name="name_de" required /></Field>
        <Field label={t(locale, "englishName")}><input className={inputClass} name="name_en" required /></Field>
        <Field label={t(locale, "start")}><input className={inputClass} name="starts_at" type="time" required /></Field>
        <Field label={t(locale, "end")}><input className={inputClass} name="ends_at" type="time" required /></Field>
        <button className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white"><Plus size={17} />{t(locale, "save")}</button>
        <button type="button" onClick={refresh} className="inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold"><RefreshCw size={17} />{t(locale, "refresh")}</button>
      </form>
      <div className="mt-5"><DataList rows={rows} /></div>
    </Card>
  );
}

export function PeriodForm() {
  const { locale } = useLocale();
  return (
    <form className="grid gap-4 md:grid-cols-2" onSubmit={async (event) => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      await apiFetch("/api/v1/planning-periods", {
        method: "POST",
        body: JSON.stringify({ year: Number(form.get("year")), month: Number(form.get("month")) })
      });
    }}>
      <h2 className="md:col-span-2 text-lg font-semibold">{t(locale, "createPeriod")}</h2>
      <Field label={t(locale, "year")}><input className={inputClass} name="year" type="number" defaultValue="2026" /></Field>
      <Field label={t(locale, "month")}><input className={inputClass} name="month" type="number" min="1" max="12" defaultValue="5" /></Field>
      <button className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white"><Plus size={17} />{t(locale, "save")}</button>
    </form>
  );
}

export function RequestForm() {
  const { locale } = useLocale();
  const [rows, setRows] = useState<AnyRecord[]>([]);

  const refresh = useCallback(async () => {
    setRows(await apiFetch<AnyRecord[]>("/api/v1/requests"));
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await apiFetch("/api/v1/requests", {
      method: "POST",
      body: JSON.stringify({
        doctor_id: Number(form.get("doctor_id")),
        planning_period_id: Number(form.get("planning_period_id")),
        request_date: form.get("request_date"),
        request_type: form.get("request_type"),
        note: form.get("note")
      })
    });
    await refresh();
  }
  return (
    <Card>
      <form className="grid gap-4 md:grid-cols-2" onSubmit={submit}>
        <h1 className="md:col-span-2 text-2xl font-semibold text-ink">{t(locale, "addRequest")}</h1>
        <Field label={t(locale, "doctorId")}><input className={inputClass} name="doctor_id" type="number" required /></Field>
        <Field label={t(locale, "planningPeriod")}><input className={inputClass} name="planning_period_id" type="number" required /></Field>
        <Field label={t(locale, "date")}><input className={inputClass} name="request_date" type="date" required /></Field>
        <Field label={t(locale, "requestType")}><select className={inputClass} name="request_type"><option value="wish">{t(locale, "wish")}</option><option value="no_go">{t(locale, "noGo")}</option><option value="preference">{t(locale, "preference")}</option></select></Field>
        <Field label={t(locale, "notes")}><input className={inputClass} name="note" /></Field>
        <button className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white"><Plus size={17} />{t(locale, "save")}</button>
        <button type="button" onClick={refresh} className="inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold"><RefreshCw size={17} />{t(locale, "refresh")}</button>
      </form>
      <div className="mt-5"><DataList rows={rows} /></div>
    </Card>
  );
}

export function RosterForm() {
  const { locale } = useLocale();
  const [rows, setRows] = useState<AnyRecord[]>([]);

  const refresh = useCallback(async () => {
    setRows(await apiFetch<AnyRecord[]>("/api/v1/roster"));
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await apiFetch("/api/v1/roster", {
      method: "POST",
      body: JSON.stringify({
        doctor_id: Number(form.get("doctor_id")),
        planning_period_id: Number(form.get("planning_period_id")),
        shift_type_id: Number(form.get("shift_type_id")),
        assignment_date: form.get("assignment_date"),
        note: form.get("note"),
        manual_override: true
      })
    });
    await refresh();
  }
  return (
    <Card>
      <form className="grid gap-4 md:grid-cols-2" onSubmit={submit}>
        <h1 className="md:col-span-2 text-2xl font-semibold text-ink">{t(locale, "addAssignment")}</h1>
        <Field label={t(locale, "doctorId")}><input className={inputClass} name="doctor_id" type="number" required /></Field>
        <Field label={t(locale, "planningPeriod")}><input className={inputClass} name="planning_period_id" type="number" required /></Field>
        <Field label={t(locale, "shiftTypeId")}><input className={inputClass} name="shift_type_id" type="number" required /></Field>
        <Field label={t(locale, "date")}><input className={inputClass} name="assignment_date" type="date" required /></Field>
        <Field label={t(locale, "notes")}><input className={inputClass} name="note" /></Field>
        <button className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white"><Plus size={17} />{t(locale, "save")}</button>
        <button type="button" onClick={refresh} className="inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold"><RefreshCw size={17} />{t(locale, "refresh")}</button>
      </form>
      <div className="mt-5"><DataList rows={rows} /></div>
    </Card>
  );
}

export function ValidationPanel() {
  const { locale } = useLocale();
  const [rows, setRows] = useState<AnyRecord[]>([]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setRows(await apiFetch<AnyRecord[]>(`/api/v1/validation/${form.get("planning_period_id")}`));
  }
  return (
    <Card>
      <form className="grid gap-4 md:grid-cols-2" onSubmit={submit}>
        <h1 className="md:col-span-2 text-2xl font-semibold text-ink">{t(locale, "warnings")}</h1>
        <Field label={t(locale, "planningPeriod")}><input className={inputClass} name="planning_period_id" type="number" required /></Field>
        <button className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white"><RefreshCw size={17} />{t(locale, "refresh")}</button>
      </form>
      <div className="mt-5"><DataList rows={rows} /></div>
    </Card>
  );
}
