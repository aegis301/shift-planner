"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Pencil, Plus, Trash2, X } from "lucide-react";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";
import { ApiError, apiFetch } from "@/lib/api";
import { t, type TranslationKey } from "@/lib/i18n";

type PropertyType = "number" | "date" | "select" | "multi_select" | "text";

type PropertyDefinition = {
  id: number;
  name: string;
  type: PropertyType;
  options: string[];
  editable_by_team_member: boolean;
  display_order: number;
  is_active: boolean;
};

const PROPERTY_TYPES: PropertyType[] = ["number", "date", "select", "multi_select", "text"];

const PROPERTY_TYPE_KEYS: Record<PropertyType, TranslationKey> = {
  number: "teamMemberPropertyTypeNumber",
  date: "teamMemberPropertyTypeDate",
  select: "teamMemberPropertyTypeSelect",
  multi_select: "teamMemberPropertyTypeMultiSelect",
  text: "teamMemberPropertyTypeText"
};

type Draft = {
  name: string;
  type: PropertyType;
  options: string[];
  optionInput: string;
  editable_by_team_member: boolean;
  is_active: boolean;
};

function emptyDraft(): Draft {
  return {
    name: "",
    type: "text",
    options: [],
    optionInput: "",
    editable_by_team_member: true,
    is_active: true
  };
}

function PropertyDefinitionModal({
  initial,
  definitionId,
  onClose,
  onSaved
}: {
  initial: Draft;
  definitionId: number | null;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const { locale } = useLocale();
  const [draft, setDraft] = useState<Draft>(initial);
  const [message, setMessage] = useState("");
  const isSelectType = draft.type === "select" || draft.type === "multi_select";

  async function submit(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    const body = {
      name: draft.name.trim(),
      type: draft.type,
      options: isSelectType ? draft.options : [],
      editable_by_team_member: draft.editable_by_team_member,
      is_active: draft.is_active
    };
    try {
      if (definitionId === null) {
        await apiFetch("/api/v1/team-member-property-definitions", {
          method: "POST",
          body: JSON.stringify(body)
        });
      } else {
        await apiFetch(`/api/v1/team-member-property-definitions/${definitionId}`, {
          method: "PATCH",
          body: JSON.stringify(body)
        });
      }
      await onSaved();
      onClose();
    } catch (e) {
      if (e instanceof ApiError && typeof e.detail === "string") {
        setMessage(e.detail);
      } else {
        setMessage(t(locale, "orgManagementInviteError"));
      }
    }
  }

  function addOption() {
    const next = draft.optionInput.trim();
    if (!next || draft.options.includes(next)) {
      return;
    }
    setDraft((prev) => ({ ...prev, options: [...prev.options, next], optionInput: "" }));
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 px-3 py-6 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-xl bg-white p-5 shadow-soft ring-1 ring-slate-200">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-ink">
            {definitionId === null
              ? t(locale, "teamMemberPropertyDefinitionAdd")
              : t(locale, "teamMemberPropertyDefinitionEdit")}
          </h2>
          <button type="button" className="rounded-lg p-2 text-slate-600 hover:bg-slate-100" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <form className="grid gap-3" onSubmit={(event) => void submit(event)}>
          <Field label={t(locale, "teamMemberPropertyDefinitionName")}>
            <input
              className={inputClass}
              required
              value={draft.name}
              onChange={(event) => setDraft((prev) => ({ ...prev, name: event.target.value }))}
            />
          </Field>
          <Field label={t(locale, "teamMemberPropertyDefinitionType")}>
            <select
              className={inputClass}
              value={draft.type}
              onChange={(event) =>
                setDraft((prev) => ({
                  ...prev,
                  type: event.target.value as PropertyType,
                  options: event.target.value === "select" || event.target.value === "multi_select" ? prev.options : []
                }))
              }
            >
              {PROPERTY_TYPES.map((type) => (
                <option key={type} value={type}>
                  {t(locale, PROPERTY_TYPE_KEYS[type])}
                </option>
              ))}
            </select>
          </Field>
          {isSelectType ? (
            <div className="grid gap-2">
              <Field label={t(locale, "teamMemberPropertyDefinitionOptions")}>
                <div className="flex gap-2">
                  <input
                    className={inputClass}
                    value={draft.optionInput}
                    onChange={(event) => setDraft((prev) => ({ ...prev, optionInput: event.target.value }))}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        addOption();
                      }
                    }}
                  />
                  <button
                    type="button"
                    className="inline-flex h-11 shrink-0 items-center justify-center rounded-lg border border-slate-200 px-3 text-sm font-semibold text-slate-700"
                    onClick={addOption}
                  >
                    {t(locale, "teamMemberPropertyDefinitionAddOption")}
                  </button>
                </div>
              </Field>
              <div className="flex flex-wrap gap-2">
                {draft.options.map((option) => (
                  <button
                    key={option}
                    type="button"
                    className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700"
                    onClick={() =>
                      setDraft((prev) => ({
                        ...prev,
                        options: prev.options.filter((item) => item !== option)
                      }))
                    }
                  >
                    {option}
                    <X size={12} />
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          <label className="inline-flex items-center gap-2 text-sm font-medium text-slate-700">
            <input
              type="checkbox"
              checked={draft.editable_by_team_member}
              onChange={(event) =>
                setDraft((prev) => ({ ...prev, editable_by_team_member: event.target.checked }))
              }
            />
            {t(locale, "teamMemberPropertyDefinitionEditableByMember")}
          </label>
          <label className="inline-flex items-center gap-2 text-sm font-medium text-slate-700">
            <input
              type="checkbox"
              checked={draft.is_active}
              onChange={(event) => setDraft((prev) => ({ ...prev, is_active: event.target.checked }))}
            />
            {t(locale, "teamMemberPropertyDefinitionActive")}
          </label>
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 px-4 text-sm font-semibold text-slate-700"
              onClick={onClose}
            >
              {t(locale, "orgStaffModalCancel")}
            </button>
            <button
              type="submit"
              className="inline-flex h-10 items-center justify-center rounded-lg bg-ink px-4 text-sm font-semibold text-white"
            >
              {t(locale, "save")}
            </button>
          </div>
          {message ? <p className="text-sm text-red-600">{message}</p> : null}
        </form>
      </div>
    </div>
  );
}

export function TeamMemberPropertyDefinitionsPanel() {
  const { locale } = useLocale();
  const [rows, setRows] = useState<PropertyDefinition[]>([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState<{ id: number | null; draft: Draft } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const next = await apiFetch<PropertyDefinition[]>("/api/v1/team-member-property-definitions");
      setRows([...next].sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" })));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function removeDefinition(id: number) {
    await apiFetch(`/api/v1/team-member-property-definitions/${id}`, { method: "DELETE" });
    await load();
  }

  return (
    <Card>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-ink">{t(locale, "teamMemberPropertyDefinitionsTitle")}</h1>
          <p className="mt-1 text-sm text-slate-600">{t(locale, "teamMemberPropertyDefinitionsHelp")}</p>
        </div>
        <button
          type="button"
          className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white"
          onClick={() => setModal({ id: null, draft: emptyDraft() })}
        >
          <Plus size={16} />
          {t(locale, "teamMemberPropertyDefinitionAdd")}
        </button>
      </div>
      {loading ? <p className="text-sm text-slate-600">{t(locale, "planningSessionLoading")}</p> : null}
      <div className="grid gap-2">
        {rows.map((row) => (
          <div
            key={row.id}
            className={`flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3 ${
              row.is_active ? "border-slate-200 bg-white" : "border-slate-100 bg-slate-50 opacity-70"
            }`}
          >
            <div>
              <p className="font-semibold text-slate-800">{row.name}</p>
              <p className="text-xs text-slate-500">
                {t(locale, PROPERTY_TYPE_KEYS[row.type])}
                {row.options.length ? ` · ${row.options.join(", ")}` : ""}
                {row.editable_by_team_member
                  ? ` · ${t(locale, "teamMemberPropertyDefinitionEditableByMemberShort")}`
                  : ` · ${t(locale, "teamMemberPropertyAdminOnly")}`}
              </p>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-slate-700"
                onClick={() =>
                  setModal({
                    id: row.id,
                    draft: {
                      name: row.name,
                      type: row.type,
                      options: [...row.options],
                      optionInput: "",
                      editable_by_team_member: row.editable_by_team_member,
                      is_active: row.is_active
                    }
                  })
                }
              >
                <Pencil size={16} />
              </button>
              <button
                type="button"
                className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-rose-200 bg-rose-50 text-rose-700"
                onClick={() => void removeDefinition(row.id)}
              >
                <Trash2 size={16} />
              </button>
            </div>
          </div>
        ))}
      </div>
      {modal ? (
        <PropertyDefinitionModal
          initial={modal.draft}
          definitionId={modal.id}
          onClose={() => setModal(null)}
          onSaved={load}
        />
      ) : null}
    </Card>
  );
}
