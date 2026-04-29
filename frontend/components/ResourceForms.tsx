"use client";

import { FormEvent, ReactNode, useCallback, useEffect, useState } from "react";
import { AlertTriangle, MoreVertical, Plus, RefreshCw, Save, Trash2, X } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { t, type Locale, type TranslationKey } from "@/lib/i18n";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";

type AnyRecord = Record<string, unknown>;
type ShiftTemplateCategory = "bereitschaftsdienst" | "rufdienst" | "spaetdienst" | "other";
type DayClass = "any" | "weekday" | "weekend" | "holiday";
type ShiftVariantRecord = {
  id: number;
  label: string;
  start_day_class: DayClass;
  end_day_class: DayClass | null;
  starts_at: string;
  ends_at: string;
  end_day_offset: number;
  required_count: number;
  is_active: boolean;
};

type ShiftTemplateRecord = {
  id: number;
  code: string;
  name_de: string;
  name_en: string;
  category: ShiftTemplateCategory;
  display_order: number;
  is_active: boolean;
  variants?: ShiftVariantRecord[];
};

const SHIFT_TEMPLATE_CATEGORIES: { value: ShiftTemplateCategory; label: TranslationKey }[] = [
  { value: "bereitschaftsdienst", label: "onCallDutyCategory" },
  { value: "rufdienst", label: "standbyDutyCategory" },
  { value: "spaetdienst", label: "lateDutyCategory" },
  { value: "other", label: "other" }
];

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
  note: "note",
  manual_override: "manualOverride",
  message: "validationMessage",
  severity: "severity",
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

function isShiftTemplateRecord(row: AnyRecord): row is ShiftTemplateRecord {
  return (
    typeof row.id === "number" &&
    typeof row.code === "string" &&
    typeof row.name_de === "string" &&
    typeof row.name_en === "string" &&
    typeof row.category === "string" &&
    Array.isArray(row.variants)
  );
}

function categoryLabel(locale: Locale, category: string): string {
  const match = SHIFT_TEMPLATE_CATEGORIES.find((entry) => entry.value === category);
  return match ? t(locale, match.label) : category;
}

function dayClassLabel(locale: Locale, dayClass: DayClass | null): string {
  if (!dayClass) {
    return t(locale, "emptyValue");
  }
  const labels: Record<DayClass, TranslationKey> = {
    any: "anyDay",
    weekday: "weekday",
    weekend: "weekend",
    holiday: "holiday"
  };
  return t(locale, labels[dayClass]);
}

function dayClassPillClass(dayClass: DayClass | null): string {
  if (dayClass === "weekday") {
    return "bg-sky-50 text-sky-800 ring-sky-200";
  }
  if (dayClass === "weekend") {
    return "bg-violet-50 text-violet-800 ring-violet-200";
  }
  if (dayClass === "holiday") {
    return "bg-rose-50 text-rose-800 ring-rose-200";
  }
  return "bg-slate-50 text-slate-700 ring-slate-200";
}

function DayClassPill({ dayClass }: { dayClass: DayClass | null }) {
  const { locale } = useLocale();
  return (
    <span className={`inline-flex rounded-full px-2 py-1 text-xs font-semibold ring-1 ${dayClassPillClass(dayClass)}`}>
      {dayClassLabel(locale, dayClass)}
    </span>
  );
}

function formatVariantTime(variant: ShiftVariantRecord): string {
  const suffix = variant.end_day_offset > 0 ? ` +${variant.end_day_offset}` : "";
  return `${formatScalar("de", variant.starts_at)}-${formatScalar("de", variant.ends_at)}${suffix}`;
}

function inferEndDayOffset(startsAt: FormDataEntryValue | null, endsAt: FormDataEntryValue | null): number {
  const start = String(startsAt ?? "");
  const end = String(endsAt ?? "");
  return start && end && end <= start ? 1 : 0;
}

function dayClassOptions(locale: Locale) {
  return ([
    ["any", "anyDay"],
    ["weekday", "weekday"],
    ["weekend", "weekend"],
    ["holiday", "holiday"]
  ] as const).map(([value, label]) => (
    <option key={value} value={value}>{t(locale, label)}</option>
  ));
}

function categoryOptions(locale: Locale) {
  return SHIFT_TEMPLATE_CATEGORIES.map((category) => (
    <option key={category.value} value={category.value}>{t(locale, category.label)}</option>
  ));
}

function VariantEditFields({ variant }: { variant: ShiftVariantRecord }) {
  const { locale } = useLocale();

  return (
    <div className="grid gap-3 rounded-lg bg-slate-50 p-3 ring-1 ring-slate-200 lg:grid-cols-[minmax(16rem,1fr)_10rem_10rem_8rem_8rem_6rem_8rem]">
      <Field label={t(locale, "name")}><input className={inputClass} name={`variant_${variant.id}_label`} defaultValue={variant.label} required /></Field>
      <Field label={t(locale, "startDayClass")}><select className={`${inputClass} w-full`} name={`variant_${variant.id}_start_day_class`} defaultValue={variant.start_day_class}>{dayClassOptions(locale)}</select></Field>
      <Field label={t(locale, "endDayClass")}>
        <select className={`${inputClass} w-full`} name={`variant_${variant.id}_end_day_class`} defaultValue={variant.end_day_class ?? ""}>
          <option value="">{t(locale, "emptyValue")}</option>
          {dayClassOptions(locale)}
        </select>
      </Field>
      <Field label={t(locale, "start")}><input className={`${inputClass} w-full`} name={`variant_${variant.id}_starts_at`} type="time" defaultValue={formatScalar(locale, variant.starts_at)} required /></Field>
      <Field label={t(locale, "end")}><input className={`${inputClass} w-full`} name={`variant_${variant.id}_ends_at`} type="time" defaultValue={formatScalar(locale, variant.ends_at)} required /></Field>
      <Field label={t(locale, "requiredCount")}><input className={`${inputClass} w-full`} name={`variant_${variant.id}_required_count`} type="number" min="1" max="20" defaultValue={variant.required_count} /></Field>
      <label className="flex h-11 items-center gap-2 self-end rounded-lg bg-white px-3 text-sm font-semibold text-slate-700 ring-1 ring-slate-200">
        <input name={`variant_${variant.id}_is_active`} type="checkbox" defaultChecked={variant.is_active} />
        {t(locale, "isActive")}
      </label>
    </div>
  );
}

function VariantRows({ variants }: { variants: ShiftVariantRecord[] }) {
  const { locale } = useLocale();
  if (!variants.length) {
    return <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-500 ring-1 ring-slate-100">{t(locale, "noVariants")}</p>;
  }
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200">
      <div className="hidden grid-cols-[minmax(7rem,1.4fr)_minmax(9rem,1.2fr)_minmax(6rem,0.8fr)_4rem_4rem] gap-3 bg-slate-50 px-3 py-2 text-[0.65rem] font-semibold uppercase tracking-wide text-slate-500 sm:grid">
        <span>{t(locale, "name")}</span>
        <span>{t(locale, "applicability")}</span>
        <span>{t(locale, "timeRange")}</span>
        <span>{t(locale, "count")}</span>
        <span>{t(locale, "status")}</span>
      </div>
      <div className="divide-y divide-slate-100">
        {variants.map((variant) => (
          <div key={variant.id} className="grid gap-2 px-3 py-3 text-sm sm:grid-cols-[minmax(7rem,1.4fr)_minmax(9rem,1.2fr)_minmax(6rem,0.8fr)_4rem_4rem] sm:items-center sm:gap-3">
            <div className="font-semibold text-ink">{variant.label}</div>
            <div className="flex flex-wrap items-center gap-1.5">
              <DayClassPill dayClass={variant.start_day_class} />
              {variant.end_day_class ? (
                <>
                  <span className="text-xs text-slate-400">-&gt;</span>
                  <DayClassPill dayClass={variant.end_day_class} />
                </>
              ) : null}
            </div>
            <div className="font-mono text-xs text-slate-700 sm:text-sm">{formatVariantTime(variant)}</div>
            <div className="text-slate-700">{variant.required_count}</div>
            <div>
              <span className={`rounded-full px-2 py-1 text-xs font-semibold ring-1 ${variant.is_active ? "bg-emerald-50 text-emerald-700 ring-emerald-200" : "bg-slate-100 text-slate-500 ring-slate-200"}`}>
                {variant.is_active ? t(locale, "yes") : t(locale, "no")}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ShiftTemplateEditorModal({
  template,
  onChanged,
  onClose
}: {
  template: ShiftTemplateRecord;
  onChanged: () => Promise<void>;
  onClose: () => void;
}) {
  const { locale } = useLocale();
  const title = locale === "de" ? template.name_de : template.name_en;
  const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState(false);

  async function deleteTemplate() {
    await apiFetch(`/api/v1/shift-templates/${template.id}`, { method: "DELETE" });
    setIsDeleteConfirmOpen(false);
    await onChanged();
    onClose();
  }

  async function submitEditor(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await apiFetch(`/api/v1/shift-templates/${template.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        code: form.get("code"),
        name_de: form.get("name_de"),
        name_en: form.get("name_en"),
        category: form.get("category"),
        is_active: form.get("is_active") === "on"
      })
    });
    for (const variant of template.variants ?? []) {
      const startsAt = form.get(`variant_${variant.id}_starts_at`);
      const endsAt = form.get(`variant_${variant.id}_ends_at`);
      await apiFetch(`/api/v1/shift-templates/variants/${variant.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          label: form.get(`variant_${variant.id}_label`),
          start_day_class: form.get(`variant_${variant.id}_start_day_class`),
          end_day_class: form.get(`variant_${variant.id}_end_day_class`) || null,
          starts_at: startsAt,
          ends_at: endsAt,
          end_day_offset: inferEndDayOffset(startsAt, endsAt),
          required_count: Number(form.get(`variant_${variant.id}_required_count`)),
          is_active: form.get(`variant_${variant.id}_is_active`) === "on"
        })
      });
    }
    await onChanged();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 px-4 py-6 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby={`shift-template-edit-${template.id}`}>
      <form className="max-h-[90vh] w-full max-w-6xl overflow-auto rounded-xl bg-white p-5 shadow-soft ring-1 ring-slate-200" onSubmit={submitEditor}>
        <div className="mb-5 flex items-start justify-between gap-3">
          <div>
            <h2 id={`shift-template-edit-${template.id}`} className="text-lg font-semibold text-ink">{t(locale, "editShiftTemplate")}</h2>
            <p className="mt-1 text-sm text-slate-500">{template.code} · {title}</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              aria-label={t(locale, "deleteShiftTemplate")}
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-rose-200 bg-rose-50 text-rose-700"
              onClick={() => setIsDeleteConfirmOpen(true)}
              title={t(locale, "deleteShiftTemplate")}
              type="button"
            >
              <Trash2 size={17} />
            </button>
            <button
              aria-label={t(locale, "save")}
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-ink text-white"
              title={t(locale, "save")}
              type="submit"
            >
              <Save size={17} />
            </button>
            <button
              aria-label={t(locale, "close")}
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600"
              onClick={onClose}
              type="button"
            >
              <X size={17} />
            </button>
          </div>
        </div>
        <div className="grid gap-3 rounded-lg bg-slate-50 p-3 ring-1 ring-slate-200 md:grid-cols-[8rem_minmax(14rem,1fr)_minmax(14rem,1fr)_14rem_auto]">
          <Field label={t(locale, "code")}><input className={`${inputClass} w-full`} name="code" defaultValue={template.code} required /></Field>
          <Field label={t(locale, "germanName")}><input className={`${inputClass} w-full`} name="name_de" defaultValue={template.name_de} required /></Field>
          <Field label={t(locale, "englishName")}><input className={`${inputClass} w-full`} name="name_en" defaultValue={template.name_en} required /></Field>
          <Field label={t(locale, "category")}><select className={`${inputClass} w-full`} name="category" defaultValue={template.category}>{categoryOptions(locale)}</select></Field>
          <label className="flex h-11 items-center gap-2 self-end rounded-lg bg-white px-3 text-sm font-semibold text-slate-700 ring-1 ring-slate-200">
            <input name="is_active" type="checkbox" defaultChecked={template.is_active} />
            {t(locale, "isActive")}
          </label>
        </div>
        <div className="mt-5 grid gap-3">
          <h3 className="text-sm font-semibold text-ink">{t(locale, "editVariants")}</h3>
          {template.variants?.length ? (
            template.variants.map((variant) => (
              <VariantEditFields key={variant.id} variant={variant} />
            ))
          ) : (
            <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-500 ring-1 ring-slate-100">{t(locale, "noVariants")}</p>
          )}
        </div>
        {isDeleteConfirmOpen ? (
          <div className="mt-5 rounded-xl bg-rose-50 p-4 ring-1 ring-rose-200">
            <div className="flex gap-3">
              <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-white text-rose-700 ring-1 ring-rose-200">
                <AlertTriangle size={19} />
              </span>
              <div>
                <h3 className="text-sm font-semibold text-rose-950">{t(locale, "deleteShiftTemplate")}</h3>
                <p className="mt-1 text-sm text-rose-900">{t(locale, "deleteShiftTemplateWarning")}</p>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap justify-end gap-2">
              <button
                className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700"
                onClick={() => setIsDeleteConfirmOpen(false)}
                type="button"
              >
                {t(locale, "close")}
              </button>
              <button
                className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-rose-700 px-4 text-sm font-semibold text-white"
                onClick={deleteTemplate}
                type="button"
              >
                <Trash2 size={16} />
                {t(locale, "confirm")}
              </button>
            </div>
          </div>
        ) : null}
      </form>
    </div>
  );
}

function ShiftTemplateCard({ template, onChanged }: { template: ShiftTemplateRecord; onChanged: () => Promise<void> }) {
  const { locale } = useLocale();
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const title = locale === "de" ? template.name_de : template.name_en;
  const subtitle = locale === "de" ? template.name_en : template.name_de;

  return (
    <>
    <article className="overflow-hidden rounded-xl border border-slate-200/90 bg-white shadow-soft ring-1 ring-slate-100/80">
      <div className="border-b border-mint/25 bg-gradient-to-r from-mint/10 via-white to-sky-50/40 px-4 py-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-md bg-ink px-2 py-1 font-mono text-xs font-semibold text-white">{template.code}</span>
              <h2 className="truncate text-sm font-semibold text-ink">{title}</h2>
            </div>
            <p className="mt-1 text-xs text-slate-500">{subtitle}</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-sky-50 px-2.5 py-1 text-xs font-semibold text-sky-800 ring-1 ring-sky-200">
              {categoryLabel(locale, template.category)}
            </span>
            <button
              type="button"
              onClick={() => setIsEditorOpen(true)}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 shadow-sm hover:bg-slate-50"
              aria-label={t(locale, "edit")}
              title={t(locale, "edit")}
            >
              <MoreVertical size={17} />
            </button>
          </div>
        </div>
      </div>
      <div className="grid gap-4 p-4">
        <div className="flex flex-wrap gap-2 text-xs text-slate-600">
          <span className={`rounded-full px-2.5 py-1 font-semibold ring-1 ${template.is_active ? "bg-emerald-50 text-emerald-700 ring-emerald-200" : "bg-slate-100 text-slate-500 ring-slate-200"}`}>
            {t(locale, "isActive")}: {template.is_active ? t(locale, "yes") : t(locale, "no")}
          </span>
        </div>
        <VariantRows variants={template.variants ?? []} />
      </div>
    </article>
    {isEditorOpen ? <ShiftTemplateEditorModal template={template} onChanged={onChanged} onClose={() => setIsEditorOpen(false)} /> : null}
    </>
  );
}

function ShiftTemplateList({ rows, onChanged }: { rows: AnyRecord[]; onChanged: () => Promise<void> }) {
  const templates = rows.filter(isShiftTemplateRecord);
  if (templates.length !== rows.length) {
    return <DataList rows={rows} />;
  }
  if (!templates.length) {
    return <DataList rows={[]} />;
  }
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      {templates.map((template) => (
        <ShiftTemplateCard key={template.id} template={template} onChanged={onChanged} />
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

export function ShiftTemplateForm() {
  const { locale } = useLocale();
  const [rows, setRows] = useState<AnyRecord[]>([]);
  const [activeTemplateId, setActiveTemplateId] = useState<number | null>(null);
  const [previewRows, setPreviewRows] = useState<AnyRecord[]>([]);
  const currentDate = new Date();
  const [previewYear, setPreviewYear] = useState(String(currentDate.getFullYear()));
  const [previewMonth, setPreviewMonth] = useState(String(currentDate.getMonth() + 1));

  const refresh = useCallback(async () => {
    const nextRows = await apiFetch<AnyRecord[]>("/api/v1/shift-templates");
    setRows(nextRows);
    if (!activeTemplateId && nextRows[0]?.id) {
      setActiveTemplateId(Number(nextRows[0].id));
    }
  }, [activeTemplateId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function submitTemplate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const template = await apiFetch<AnyRecord>("/api/v1/shift-templates", {
      method: "POST",
      body: JSON.stringify({
        code: form.get("code"),
        name_de: form.get("name_de"),
        name_en: form.get("name_en"),
        category: form.get("category")
      })
    });
    if (template.id) {
      setActiveTemplateId(Number(template.id));
    }
    event.currentTarget.reset();
    await refresh();
  }

  async function submitVariant(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!activeTemplateId) return;
    const form = new FormData(event.currentTarget);
    const startsAt = form.get("starts_at");
    const endsAt = form.get("ends_at");
    await apiFetch(`/api/v1/shift-templates/${activeTemplateId}/variants`, {
      method: "POST",
      body: JSON.stringify({
        label: form.get("label"),
        start_day_class: form.get("start_day_class"),
        end_day_class: form.get("end_day_class") || null,
        starts_at: startsAt,
        ends_at: endsAt,
        end_day_offset: inferEndDayOffset(startsAt, endsAt),
        required_count: Number(form.get("required_count"))
      })
    });
    event.currentTarget.reset();
    await refresh();
  }

  async function addPreset(preset: "weekday_on_call" | "weekend_day" | "weekend_night" | "full_day") {
    if (!activeTemplateId) return;
    const payloads = {
      weekday_on_call: [
        { label: "Wochentag Bereitschaftsdienst", start_day_class: "weekday", end_day_class: null, starts_at: "15:45", ends_at: "07:30", end_day_offset: 1, required_count: 1 }
      ],
      weekend_day: [
        { label: "Wochenende/Feiertag Tag", start_day_class: "weekend", end_day_class: null, starts_at: "09:00", ends_at: "20:00", end_day_offset: 0, required_count: 1 },
        { label: "Feiertag Tag", start_day_class: "holiday", end_day_class: null, starts_at: "09:00", ends_at: "20:00", end_day_offset: 0, required_count: 1 }
      ],
      weekend_night: [
        { label: "Wochenende/Feiertag Nacht", start_day_class: "weekend", end_day_class: null, starts_at: "20:00", ends_at: "09:00", end_day_offset: 1, required_count: 1 },
        { label: "Feiertag Nacht", start_day_class: "holiday", end_day_class: null, starts_at: "20:00", ends_at: "09:00", end_day_offset: 1, required_count: 1 }
      ],
      full_day: [
        { label: "24 Stunden", start_day_class: "any", end_day_class: null, starts_at: "09:00", ends_at: "09:00", end_day_offset: 1, required_count: 1 }
      ]
    }[preset];
    for (const payload of payloads) {
      await apiFetch(`/api/v1/shift-templates/${activeTemplateId}/variants`, {
        method: "POST",
        body: JSON.stringify(payload)
      });
    }
    await refresh();
  }

  async function loadPreview() {
    setPreviewRows(await apiFetch<AnyRecord[]>("/api/v1/shift-templates/preview", {
      method: "POST",
      body: JSON.stringify({ year: Number(previewYear), month: Number(previewMonth) })
    }));
  }

  const activeTemplate = rows.find((row) => Number(row.id) === activeTemplateId);
  const activeShiftTemplate = activeTemplate && isShiftTemplateRecord(activeTemplate) ? activeTemplate : null;

  return (
    <div className="grid gap-5">
    <Card>
      <form className="grid gap-4 md:grid-cols-2" onSubmit={submitTemplate}>
        <h1 className="md:col-span-2 text-2xl font-semibold text-ink">{t(locale, "shiftTemplateBuilder")}</h1>
        <Field label={t(locale, "code")}><input className={inputClass} name="code" required /></Field>
        <Field label={t(locale, "category")}>
          <select className={inputClass} name="category" defaultValue="bereitschaftsdienst">
            {SHIFT_TEMPLATE_CATEGORIES.map((category) => (
              <option key={category.value} value={category.value}>{t(locale, category.label)}</option>
            ))}
          </select>
        </Field>
        <Field label={t(locale, "germanName")}><input className={inputClass} name="name_de" required /></Field>
        <Field label={t(locale, "englishName")}><input className={inputClass} name="name_en" required /></Field>
        <button className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white"><Plus size={17} />{t(locale, "save")}</button>
        <button type="button" onClick={refresh} className="inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold"><RefreshCw size={17} />{t(locale, "refresh")}</button>
      </form>
    </Card>
    <Card>
      <form className="grid gap-4 md:grid-cols-3" onSubmit={submitVariant}>
        <h2 className="md:col-span-3 text-lg font-semibold text-ink">{t(locale, "shiftVariants")}</h2>
        <Field label={t(locale, "shiftTemplate")}>
          <select className={inputClass} value={activeTemplateId ?? ""} onChange={(event) => setActiveTemplateId(Number(event.target.value))}>
            {rows.map((row) => <option key={String(row.id)} value={String(row.id)}>{String(row.code)} · {String(row.name_de)}</option>)}
          </select>
        </Field>
        <Field label={t(locale, "name")}><input className={inputClass} name="label" required /></Field>
        <Field label={t(locale, "startDayClass")}><select className={inputClass} name="start_day_class">{dayClassOptions(locale)}</select></Field>
        <Field label={t(locale, "endDayClass")}><select className={inputClass} name="end_day_class"><option value="">{t(locale, "emptyValue")}</option>{dayClassOptions(locale)}</select></Field>
        <Field label={t(locale, "start")}><input className={inputClass} name="starts_at" type="time" required /></Field>
        <Field label={t(locale, "end")}><input className={inputClass} name="ends_at" type="time" required /></Field>
        <Field label={t(locale, "requiredCount")}><input className={inputClass} name="required_count" type="number" min="1" max="20" defaultValue="1" /></Field>
        <button className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white"><Plus size={17} />{t(locale, "save")}</button>
      </form>
      <div className="mt-4 flex flex-wrap gap-2">
        {(["weekday_on_call", "weekend_day", "weekend_night", "full_day"] as const).map((preset) => (
          <button key={preset} type="button" onClick={() => addPreset(preset)} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700">
            {t(locale, preset)}
          </button>
        ))}
      </div>
      {activeShiftTemplate ? <div className="mt-5"><ShiftTemplateCard template={activeShiftTemplate} onChanged={refresh} /></div> : null}
    </Card>
    <Card>
      <div className="grid gap-4 md:grid-cols-3">
        <h2 className="md:col-span-3 text-lg font-semibold text-ink">{t(locale, "slotPreview")}</h2>
        <Field label={t(locale, "year")}><input className={inputClass} value={previewYear} onChange={(event) => setPreviewYear(event.target.value)} type="number" /></Field>
        <Field label={t(locale, "month")}><input className={inputClass} value={previewMonth} onChange={(event) => setPreviewMonth(event.target.value)} type="number" min="1" max="12" /></Field>
        <button type="button" onClick={loadPreview} className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white"><RefreshCw size={17} />{t(locale, "refresh")}</button>
      </div>
      <div className="mt-5"><DataList rows={previewRows.slice(0, 24)} /></div>
    </Card>
    <Card>
      <h2 className="text-lg font-semibold text-ink">{t(locale, "shiftTemplates")}</h2>
      <div className="mt-5"><ShiftTemplateList rows={rows} onChanged={refresh} /></div>
    </Card>
    </div>
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
