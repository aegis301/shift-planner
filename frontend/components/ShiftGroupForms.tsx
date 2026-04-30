"use client";

import type { Dispatch, SetStateAction } from "react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Pencil, Plus, RefreshCw, Save, Trash2, X } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { t, type Locale } from "@/lib/i18n";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";

type ShiftGroupRecord = {
  id: number;
  code: string;
  name_de: string;
  name_en: string;
  display_order: number;
  is_active: boolean;
  created_at: string;
  doctor_ids: number[];
  shift_template_ids: number[];
};

type DoctorOption = { id: number; first_name: string; last_name: string };
type TemplateOption = { id: number; code: string; name_de: string; name_en: string };

function doctorLabel(doctor: DoctorOption): string {
  return `${doctor.first_name} ${doctor.last_name}`.trim();
}

function groupLabel(locale: Locale, group: ShiftGroupRecord) {
  return locale === "de" ? group.name_de : group.name_en;
}

function ShiftGroupDoctorPicker({
  doctors,
  doctorIds,
  setDoctorIds,
  locale
}: {
  doctors: DoctorOption[];
  doctorIds: Set<number>;
  setDoctorIds: Dispatch<SetStateAction<Set<number>>>;
  locale: Locale;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const pool = doctors.filter((doctor) => !doctorIds.has(doctor.id));
    if (!q) {
      return [];
    }
    return pool.filter((doctor) => doctorLabel(doctor).toLowerCase().includes(q)).slice(0, 25);
  }, [doctors, doctorIds, query]);

  const selectedDoctors = useMemo(
    () =>
      doctors
        .filter((doctor) => doctorIds.has(doctor.id))
        .sort((a, b) => doctorLabel(a).localeCompare(doctorLabel(b))),
    [doctors, doctorIds]
  );

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, []);

  function addDoctor(id: number) {
    setDoctorIds((prev) => new Set([...prev, id]));
    setQuery("");
    setOpen(false);
  }

  function removeDoctor(id: number) {
    setDoctorIds((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  }

  const showList = open && query.trim().length > 0;

  return (
    <div ref={rootRef} className="grid gap-2">
      <p className="text-xs text-slate-600">{t(locale, "searchDoctorsHint")}</p>
      <div className="relative">
        <input
          type="search"
          autoComplete="off"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder={t(locale, "searchDoctorsPlaceholder")}
          className={inputClass}
        />
        {showList ? (
          <ul className="absolute z-20 mt-1 max-h-48 w-full overflow-auto rounded-lg border border-slate-200 bg-white py-1 shadow-lg ring-1 ring-slate-200/80">
            {filtered.length === 0 ? (
              <li className="px-3 py-2 text-sm text-slate-500">{t(locale, "noDoctorMatches")}</li>
            ) : (
              filtered.map((doctor) => (
                <li key={doctor.id}>
                  <button
                    type="button"
                    className="w-full px-3 py-2 text-left text-sm text-ink hover:bg-slate-50"
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => addDoctor(doctor.id)}
                  >
                    {doctorLabel(doctor)}
                  </button>
                </li>
              ))
            )}
          </ul>
        ) : null}
      </div>
      {selectedDoctors.length ? (
        <div className="flex flex-wrap gap-1.5">
          {selectedDoctors.map((doctor) => (
            <span
              key={doctor.id}
              className="inline-flex max-w-full items-center gap-1 rounded-full bg-slate-100 py-1 pl-2.5 pr-1 text-xs font-medium text-slate-800 ring-1 ring-slate-200"
            >
              <span className="truncate">{doctorLabel(doctor)}</span>
              <button
                type="button"
                className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-slate-500 hover:bg-slate-200 hover:text-slate-800"
                onClick={() => removeDoctor(doctor.id)}
                aria-label={`${t(locale, "removeFromSelection")}: ${doctorLabel(doctor)}`}
              >
                <X size={14} />
              </button>
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ShiftGroupEditorModal({
  group,
  doctors,
  templates,
  onChanged,
  onClose
}: {
  group: ShiftGroupRecord | null;
  doctors: DoctorOption[];
  templates: TemplateOption[];
  onChanged: () => Promise<void>;
  onClose: () => void;
}) {
  const { locale } = useLocale();
  const [doctorIds, setDoctorIds] = useState<Set<number>>(new Set(group?.doctor_ids ?? []));
  const [templateIds, setTemplateIds] = useState<Set<number>>(new Set(group?.shift_template_ids ?? []));

  useEffect(() => {
    setDoctorIds(new Set(group?.doctor_ids ?? []));
    setTemplateIds(new Set(group?.shift_template_ids ?? []));
  }, [group]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = {
      code: String(form.get("code")),
      name_de: String(form.get("name_de")),
      name_en: String(form.get("name_en")),
      display_order: Number(form.get("display_order")),
      is_active: form.get("is_active") === "on"
    };
    if (group) {
      await apiFetch(`/api/v1/shift-groups/${group.id}`, { method: "PATCH", body: JSON.stringify(body) });
      await apiFetch(`/api/v1/shift-groups/${group.id}/doctors`, {
        method: "PUT",
        body: JSON.stringify({ doctor_ids: [...doctorIds] })
      });
      await apiFetch(`/api/v1/shift-groups/${group.id}/shift-templates`, {
        method: "PUT",
        body: JSON.stringify({ shift_template_ids: [...templateIds] })
      });
    } else {
      const created = await apiFetch<ShiftGroupRecord>("/api/v1/shift-groups", { method: "POST", body: JSON.stringify(body) });
      await apiFetch(`/api/v1/shift-groups/${created.id}/doctors`, {
        method: "PUT",
        body: JSON.stringify({ doctor_ids: [...doctorIds] })
      });
      await apiFetch(`/api/v1/shift-groups/${created.id}/shift-templates`, {
        method: "PUT",
        body: JSON.stringify({ shift_template_ids: [...templateIds] })
      });
    }
    await onChanged();
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 px-4 py-6 backdrop-blur-sm" role="dialog" aria-modal="true">
      <form className="max-h-[90vh] w-full max-w-3xl overflow-auto rounded-xl bg-white p-5 shadow-soft ring-1 ring-slate-200" onSubmit={submit}>
        <div className="mb-4 flex items-start justify-between gap-3">
          <h2 className="text-lg font-semibold text-ink">{group ? t(locale, "editShiftGroup") : t(locale, "createShiftGroup")}</h2>
          <button type="button" onClick={onClose} className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600" aria-label={t(locale, "close")}>
            <X size={17} />
          </button>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label={t(locale, "code")}><input className={inputClass} name="code" defaultValue={group?.code ?? ""} required /></Field>
          <Field label={t(locale, "displayOrder")}><input className={inputClass} name="display_order" type="number" defaultValue={group?.display_order ?? 0} /></Field>
          <Field label={t(locale, "germanName")}><input className={inputClass} name="name_de" defaultValue={group?.name_de ?? ""} required /></Field>
          <Field label={t(locale, "englishName")}><input className={inputClass} name="name_en" defaultValue={group?.name_en ?? ""} required /></Field>
          <label className="inline-flex h-11 items-center gap-2 rounded-lg bg-white px-3 text-sm font-semibold text-slate-700 ring-1 ring-slate-200 md:col-span-2">
            <input name="is_active" type="checkbox" defaultChecked={group?.is_active ?? true} />
            {t(locale, "isActive")}
          </label>
        </div>
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <div className="rounded-lg border border-slate-200 p-3">
            <p className="text-sm font-semibold text-ink">{t(locale, "shiftGroupDoctors")}</p>
            <div className="mt-2">
              <ShiftGroupDoctorPicker doctors={doctors} doctorIds={doctorIds} setDoctorIds={setDoctorIds} locale={locale} />
            </div>
          </div>
          <div className="rounded-lg border border-slate-200 p-3">
            <p className="text-sm font-semibold text-ink">{t(locale, "shiftGroupTemplates")}</p>
            <div className="mt-2 max-h-48 space-y-2 overflow-y-auto text-sm">
              {templates.map((template) => (
                <label key={template.id} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={templateIds.has(template.id)}
                    onChange={() => {
                      setTemplateIds((prev) => {
                        const next = new Set(prev);
                        if (next.has(template.id)) {
                          next.delete(template.id);
                        } else {
                          next.add(template.id);
                        }
                        return next;
                      });
                    }}
                  />
                  <span className="font-mono text-xs">{template.code}</span>
                  <span>{locale === "de" ? template.name_de : template.name_en}</span>
                </label>
              ))}
            </div>
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700">
            {t(locale, "close")}
          </button>
          <button type="submit" className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white">
            <Save size={16} />
            {t(locale, "save")}
          </button>
        </div>
      </form>
    </div>
  );
}

export function ShiftGroupForm() {
  const { locale } = useLocale();
  const [groups, setGroups] = useState<ShiftGroupRecord[]>([]);
  const [doctors, setDoctors] = useState<DoctorOption[]>([]);
  const [templates, setTemplates] = useState<TemplateOption[]>([]);
  const [editing, setEditing] = useState<ShiftGroupRecord | "new" | null>(null);
  const [message, setMessage] = useState("");

  const refresh = useCallback(async () => {
    const [nextGroups, nextDoctors, nextTemplates] = await Promise.all([
      apiFetch<ShiftGroupRecord[]>("/api/v1/shift-groups"),
      apiFetch<Array<{ id: number; first_name: string; last_name: string }>>("/api/v1/doctors?active_only=true"),
      apiFetch<Array<{ id: number; code: string; name_de: string; name_en: string }>>("/api/v1/shift-templates")
    ]);
    setGroups(nextGroups);
    setDoctors(nextDoctors.map((d) => ({ id: d.id, first_name: d.first_name, last_name: d.last_name })));
    setTemplates(nextTemplates.map((row) => ({ id: row.id, code: row.code, name_de: row.name_de, name_en: row.name_en })));
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function deleteGroup(id: number) {
    await apiFetch(`/api/v1/shift-groups/${id}`, { method: "DELETE" });
    setMessage(t(locale, "saved"));
    await refresh();
  }

  return (
    <div className="grid gap-5">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-ink">{t(locale, "shiftGroups")}</h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-600">{t(locale, "shiftGroupsPageHelp")}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => void refresh()} className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold">
              <RefreshCw size={16} />
              {t(locale, "refresh")}
            </button>
            <button
              type="button"
              onClick={() => setEditing("new")}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white"
            >
              <Plus size={16} />
              {t(locale, "createShiftGroup")}
            </button>
          </div>
        </div>
        {message ? <p className="mt-3 text-sm text-emerald-700">{message}</p> : null}
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        {groups.map((group) => (
          <Card key={group.id}>
            <div className="flex items-start justify-between gap-2">
              <div>
                <h2 className="text-lg font-semibold text-ink">{groupLabel(locale, group)}</h2>
                <p className="mt-1 font-mono text-xs text-slate-500">{group.code}</p>
                <p className="mt-2 text-sm text-slate-600">
                  {t(locale, "shiftGroupDoctors")}: {group.doctor_ids.length} · {t(locale, "shiftGroupTemplates")}: {group.shift_template_ids.length}
                </p>
              </div>
              <div className="flex shrink-0 gap-1">
                <button
                  type="button"
                  onClick={() => setEditing(group)}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600"
                  aria-label={t(locale, "edit")}
                  title={t(locale, "edit")}
                >
                  <Pencil size={16} />
                </button>
                <button
                  type="button"
                  onClick={() => void deleteGroup(group.id)}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-rose-200 bg-rose-50 text-rose-700"
                  aria-label={t(locale, "deleteShiftGroup")}
                  title={t(locale, "deleteShiftGroup")}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          </Card>
        ))}
      </div>
      {editing ? (
        <ShiftGroupEditorModal
          group={editing === "new" ? null : editing}
          doctors={doctors}
          templates={templates}
          onChanged={refresh}
          onClose={() => setEditing(null)}
        />
      ) : null}
    </div>
  );
}
