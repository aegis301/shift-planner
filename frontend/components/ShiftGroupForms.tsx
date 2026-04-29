"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
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

type DoctorOption = { id: number; name: string };
type TemplateOption = { id: number; code: string; name_de: string; name_en: string };

function groupLabel(locale: Locale, group: ShiftGroupRecord) {
  return locale === "de" ? group.name_de : group.name_en;
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
            <div className="mt-2 max-h-48 space-y-2 overflow-y-auto text-sm">
              {doctors.map((doctor) => (
                <label key={doctor.id} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={doctorIds.has(doctor.id)}
                    onChange={() => {
                      setDoctorIds((prev) => {
                        const next = new Set(prev);
                        if (next.has(doctor.id)) {
                          next.delete(doctor.id);
                        } else {
                          next.add(doctor.id);
                        }
                        return next;
                      });
                    }}
                  />
                  {doctor.name}
                </label>
              ))}
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
      apiFetch<Array<{ id: number; name: string }>>("/api/v1/doctors?active_only=true"),
      apiFetch<Array<{ id: number; code: string; name_de: string; name_en: string }>>("/api/v1/shift-templates")
    ]);
    setGroups(nextGroups);
    setDoctors(nextDoctors.map((d) => ({ id: d.id, name: d.name })));
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
