"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Pencil, Plus, Trash2, X } from "lucide-react";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";
import { teamMemberLabel } from "@/components/ResourceForms";
import { ApiError, apiFetch } from "@/lib/api";
import { dataTableScrollShellClassName } from "@/lib/dataTableLayout";
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

type MatrixCell = {
  property_definition_id: number;
  value: unknown;
};

type MatrixMember = {
  id: number;
  first_name: string;
  last_name: string;
  nickname?: string | null;
  is_active: boolean;
  values: MatrixCell[];
};

type MatrixPayload = {
  definitions: PropertyDefinition[];
  members: MatrixMember[];
};

const PROPERTY_TYPES: PropertyType[] = ["number", "date", "select", "multi_select", "text"];

const PROPERTY_TYPE_KEYS: Record<PropertyType, TranslationKey> = {
  number: "teamMemberPropertyTypeNumber",
  date: "teamMemberPropertyTypeDate",
  select: "teamMemberPropertyTypeSelect",
  multi_select: "teamMemberPropertyTypeMultiSelect",
  text: "teamMemberPropertyTypeText"
};

const cellInputClass =
  "h-9 w-full min-w-[7rem] rounded-md border border-slate-200 bg-white px-2 text-sm text-slate-800 outline-none ring-mint/20 transition focus:ring-4";

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

function valuesMap(member: MatrixMember): Record<number, unknown> {
  const out: Record<number, unknown> = {};
  for (const cell of member.values) {
    out[cell.property_definition_id] = cell.value;
  }
  return out;
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

function PropertyCellEditor({
  definition,
  value,
  onChange
}: {
  definition: PropertyDefinition;
  value: unknown;
  onChange: (next: unknown) => void;
}) {
  const { locale } = useLocale();

  if (definition.type === "number") {
    return (
      <input
        className={cellInputClass}
        type="number"
        value={value === null || value === undefined ? "" : String(value)}
        onChange={(event) => onChange(event.target.value === "" ? null : Number(event.target.value))}
        aria-label={definition.name}
      />
    );
  }
  if (definition.type === "date") {
    return (
      <input
        className={cellInputClass}
        type="date"
        value={typeof value === "string" ? value : ""}
        onChange={(event) => onChange(event.target.value || null)}
        aria-label={definition.name}
      />
    );
  }
  if (definition.type === "text") {
    return (
      <input
        className={cellInputClass}
        type="text"
        value={typeof value === "string" ? value : ""}
        onChange={(event) => onChange(event.target.value || null)}
        aria-label={definition.name}
      />
    );
  }
  if (definition.type === "select") {
    return (
      <select
        className={cellInputClass}
        value={typeof value === "string" ? value : ""}
        onChange={(event) => onChange(event.target.value || null)}
        aria-label={definition.name}
      >
        <option value="">{t(locale, "teamMemberPropertySelectEmpty")}</option>
        {definition.options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    );
  }

  const selected = Array.isArray(value) ? (value as string[]) : [];
  return (
    <div className="flex min-w-[10rem] flex-wrap gap-1" role="group" aria-label={definition.name}>
      {definition.options.map((option) => {
        const isOn = selected.includes(option);
        return (
          <button
            key={option}
            type="button"
            className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ${
              isOn ? "bg-ink text-white ring-ink" : "bg-white text-slate-700 ring-slate-200"
            }`}
            onClick={() => {
              const next = isOn ? selected.filter((item) => item !== option) : [...selected, option];
              onChange(next.length ? next : null);
            }}
          >
            {option}
          </button>
        );
      })}
    </div>
  );
}

export function TeamMemberPropertyDefinitionsPanel() {
  const { locale } = useLocale();
  const [definitions, setDefinitions] = useState<PropertyDefinition[]>([]);
  const [members, setMembers] = useState<MatrixMember[]>([]);
  const [cellValues, setCellValues] = useState<Record<number, Record<number, unknown>>>({});
  const [loading, setLoading] = useState(true);
  const [showInactiveMembers, setShowInactiveMembers] = useState(false);
  const [showInactiveDefinitions, setShowInactiveDefinitions] = useState(false);
  const [message, setMessage] = useState("");
  const [modal, setModal] = useState<{ id: number | null; draft: Draft } | null>(null);
  const cellValuesRef = useRef(cellValues);
  const dirtyRef = useRef<Record<number, Set<number>>>({});
  const persistTimersRef = useRef<Record<number, ReturnType<typeof setTimeout>>>({});

  cellValuesRef.current = cellValues;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        active_definitions_only: String(!showInactiveDefinitions),
        active_members_only: String(!showInactiveMembers)
      });
      const next = await apiFetch<MatrixPayload>(`/api/v1/team-member-property-values/matrix?${params}`);
      const sortedDefs = [...next.definitions].sort((a, b) =>
        a.name.localeCompare(b.name, undefined, { sensitivity: "base" })
      );
      setDefinitions(sortedDefs);
      setMembers(next.members);
      const mapped: Record<number, Record<number, unknown>> = {};
      for (const member of next.members) {
        mapped[member.id] = valuesMap(member);
      }
      cellValuesRef.current = mapped;
      setCellValues(mapped);
      dirtyRef.current = {};
      setMessage("");
    } finally {
      setLoading(false);
    }
  }, [showInactiveDefinitions, showInactiveMembers]);

  useEffect(() => {
    void load();
  }, [load]);

  const flushMember = useCallback(
    async (memberId: number) => {
      const dirty = dirtyRef.current[memberId];
      if (!dirty || dirty.size === 0) {
        return;
      }
      const definitionIds = [...dirty];
      dirtyRef.current[memberId] = new Set();
      const memberValues = cellValuesRef.current[memberId] ?? {};
      try {
        await apiFetch(`/api/v1/team-members/${memberId}/property-values`, {
          method: "PUT",
          body: JSON.stringify({
            values: definitionIds.map((property_definition_id) => ({
              property_definition_id,
              value: memberValues[property_definition_id] === "" ? null : memberValues[property_definition_id]
            }))
          })
        });
        setMessage("");
      } catch (e) {
        for (const id of definitionIds) {
          dirtyRef.current[memberId] = dirtyRef.current[memberId] ?? new Set();
          dirtyRef.current[memberId].add(id);
        }
        if (e instanceof ApiError && typeof e.detail === "string") {
          setMessage(e.detail);
        } else {
          setMessage(t(locale, "orgManagementInviteError"));
        }
      }
    },
    [locale]
  );

  const flushMemberRef = useRef(flushMember);
  flushMemberRef.current = flushMember;

  const schedulePersist = useCallback(
    (memberId: number) => {
      const existing = persistTimersRef.current[memberId];
      if (existing) {
        clearTimeout(existing);
      }
      persistTimersRef.current[memberId] = setTimeout(() => {
        delete persistTimersRef.current[memberId];
        void flushMember(memberId);
      }, 400);
    },
    [flushMember]
  );

  useEffect(() => {
    return () => {
      const timers = persistTimersRef.current;
      const pendingIds = Object.keys(timers).map(Number);
      for (const timer of Object.values(timers)) {
        clearTimeout(timer);
      }
      persistTimersRef.current = {};
      for (const memberId of pendingIds) {
        void flushMemberRef.current(memberId);
      }
    };
  }, []);

  function updateCell(memberId: number, definitionId: number, value: unknown) {
    setCellValues((prev) => {
      const next = {
        ...prev,
        [memberId]: {
          ...(prev[memberId] ?? {}),
          [definitionId]: value
        }
      };
      cellValuesRef.current = next;
      return next;
    });
    dirtyRef.current[memberId] = dirtyRef.current[memberId] ?? new Set();
    dirtyRef.current[memberId].add(definitionId);
    schedulePersist(memberId);
  }

  async function removeDefinition(id: number) {
    await apiFetch(`/api/v1/team-member-property-definitions/${id}`, { method: "DELETE" });
    await load();
  }

  const visibleDefinitions = useMemo(
    () => (showInactiveDefinitions ? definitions : definitions.filter((row) => row.is_active)),
    [definitions, showInactiveDefinitions]
  );

  return (
    <Card>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-ink">{t(locale, "teamMemberPropertyDefinitionsTitle")}</h1>
          <p className="mt-1 text-sm text-slate-600">{t(locale, "teamMemberPropertiesTableHelp")}</p>
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
      <div className="mb-3 flex flex-wrap gap-4 text-sm text-slate-700">
        <label className="inline-flex items-center gap-2">
          <input
            type="checkbox"
            checked={showInactiveMembers}
            onChange={(event) => setShowInactiveMembers(event.target.checked)}
          />
          {t(locale, "teamMemberPropertiesShowInactiveMembers")}
        </label>
        <label className="inline-flex items-center gap-2">
          <input
            type="checkbox"
            checked={showInactiveDefinitions}
            onChange={(event) => setShowInactiveDefinitions(event.target.checked)}
          />
          {t(locale, "teamMemberPropertiesShowInactiveDefinitions")}
        </label>
      </div>
      {loading ? <p className="text-sm text-slate-600">{t(locale, "planningSessionLoading")}</p> : null}
      {!loading && visibleDefinitions.length === 0 ? (
        <p className="text-sm text-slate-600">{t(locale, "teamMemberPropertiesEmpty")}</p>
      ) : null}
      {!loading && visibleDefinitions.length > 0 ? (
        <div className={`${dataTableScrollShellClassName} rounded-lg border border-slate-200`}>
          <table className="w-full min-w-max border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs font-semibold uppercase tracking-wide text-slate-500">
                <th className="sticky left-0 z-20 bg-white px-3 py-3">
                  {t(locale, "teamMemberPropertiesMemberColumn")}
                </th>
                {visibleDefinitions.map((definition) => (
                  <th
                    key={definition.id}
                    className={`min-w-[10rem] px-3 py-3 align-bottom ${
                      definition.is_active ? "" : "opacity-60"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2 normal-case">
                      <div>
                        <p className="text-sm font-semibold text-slate-800">{definition.name}</p>
                        <p className="mt-0.5 text-[11px] font-medium text-slate-500">
                          {t(locale, PROPERTY_TYPE_KEYS[definition.type])}
                          {definition.editable_by_team_member
                            ? ` · ${t(locale, "teamMemberPropertyDefinitionEditableByMemberShort")}`
                            : ` · ${t(locale, "teamMemberPropertyAdminOnly")}`}
                        </p>
                      </div>
                      <div className="flex shrink-0 gap-1">
                        <button
                          type="button"
                          className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 text-slate-700 hover:bg-slate-50"
                          aria-label={t(locale, "teamMemberPropertyDefinitionEdit")}
                          onClick={() =>
                            setModal({
                              id: definition.id,
                              draft: {
                                name: definition.name,
                                type: definition.type,
                                options: [...definition.options],
                                optionInput: "",
                                editable_by_team_member: definition.editable_by_team_member,
                                is_active: definition.is_active
                              }
                            })
                          }
                        >
                          <Pencil size={14} />
                        </button>
                        <button
                          type="button"
                          className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100"
                          aria-label={t(locale, "teamMemberPropertyDefinitionDelete")}
                          onClick={() => void removeDefinition(definition.id)}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {members.length === 0 ? (
                <tr>
                  <td
                    className="px-3 py-4 text-sm text-slate-600"
                    colSpan={visibleDefinitions.length + 1}
                  >
                    {t(locale, "teamMemberPropertiesNoMembers")}
                  </td>
                </tr>
              ) : (
                members.map((member) => (
                  <tr
                    key={member.id}
                    className={`border-b border-slate-100 ${member.is_active ? "bg-white" : "bg-slate-50 opacity-80"}`}
                  >
                    <td
                      className={`sticky left-0 z-10 px-3 py-2 font-medium text-slate-800 ${
                        member.is_active ? "bg-white" : "bg-slate-50"
                      }`}
                    >
                      {teamMemberLabel(member)}
                      {!member.is_active ? (
                        <span className="ml-2 text-xs font-medium text-slate-500">
                          {t(locale, "teamMemberPropertiesInactiveBadge")}
                        </span>
                      ) : null}
                    </td>
                    {visibleDefinitions.map((definition) => (
                      <td key={definition.id} className="px-3 py-2 align-middle">
                        <PropertyCellEditor
                          definition={definition}
                          value={cellValues[member.id]?.[definition.id] ?? null}
                          onChange={(next) => updateCell(member.id, definition.id, next)}
                        />
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      ) : null}
      {message ? <p className="mt-3 text-sm text-red-600">{message}</p> : null}
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
