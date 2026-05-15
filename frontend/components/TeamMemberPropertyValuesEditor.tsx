"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Field, inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";
import { ApiError, apiFetch } from "@/lib/api";
import { t, type TranslationKey } from "@/lib/i18n";

type PropertyType = "number" | "date" | "select" | "multi_select" | "text";

type PropertyValueRow = {
  property_definition_id: number;
  value: unknown;
  name: string;
  type: PropertyType;
  options: string[];
  editable_by_team_member: boolean;
  is_active: boolean;
};

const PROPERTY_TYPE_KEYS: Record<PropertyType, TranslationKey> = {
  number: "teamMemberPropertyTypeNumber",
  date: "teamMemberPropertyTypeDate",
  select: "teamMemberPropertyTypeSelect",
  multi_select: "teamMemberPropertyTypeMultiSelect",
  text: "teamMemberPropertyTypeText"
};

function formatDisplayValue(row: PropertyValueRow): string {
  if (row.value === null || row.value === undefined || row.value === "") {
    return "—";
  }
  if (row.type === "multi_select" && Array.isArray(row.value)) {
    return row.value.join(", ");
  }
  return String(row.value);
}

function buildPayload(rows: PropertyValueRow[]) {
  return {
    values: rows.map((row) => ({
      property_definition_id: row.property_definition_id,
      value: row.value === "" ? null : row.value
    }))
  };
}

export function TeamMemberPropertyValuesEditor({
  teamMemberId,
  adminMode = false
}: {
  teamMemberId: number;
  adminMode?: boolean;
}) {
  const { locale } = useLocale();
  const [rows, setRows] = useState<PropertyValueRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const rowsRef = useRef<PropertyValueRow[]>([]);
  const persistTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  rowsRef.current = rows;

  const flushPersist = useCallback(async () => {
    const editableRows = rowsRef.current.filter((row) => adminMode || row.editable_by_team_member);
    if (editableRows.length === 0) {
      return;
    }
    try {
      const saved = await apiFetch<PropertyValueRow[]>(
        `/api/v1/team-members/${teamMemberId}/property-values`,
        {
          method: "PUT",
          body: JSON.stringify(buildPayload(editableRows))
        }
      );
      const mapped = saved.map((row) => ({
        property_definition_id: row.property_definition_id,
        value: row.value,
        name: row.name,
        type: row.type,
        options: row.options ?? [],
        editable_by_team_member: row.editable_by_team_member,
        is_active: row.is_active
      }));
      rowsRef.current = mapped;
      setRows(mapped);
      setMessage("");
    } catch (e) {
      if (e instanceof ApiError && typeof e.detail === "string") {
        setMessage(e.detail);
      } else {
        setMessage(t(locale, "orgManagementInviteError"));
      }
    }
  }, [teamMemberId, locale, adminMode]);

  const flushPersistRef = useRef(flushPersist);
  flushPersistRef.current = flushPersist;

  const schedulePersist = useCallback(() => {
    if (persistTimerRef.current) {
      clearTimeout(persistTimerRef.current);
    }
    persistTimerRef.current = setTimeout(() => {
      persistTimerRef.current = null;
      void flushPersist();
    }, 400);
  }, [flushPersist]);

  useEffect(() => {
    return () => {
      const hadPending = persistTimerRef.current !== null;
      if (persistTimerRef.current) {
        clearTimeout(persistTimerRef.current);
        persistTimerRef.current = null;
      }
      if (hadPending) {
        void flushPersistRef.current();
      }
    };
  }, []);

  const loadValues = useCallback(async () => {
    setLoading(true);
    try {
      const next = await apiFetch<PropertyValueRow[]>(
        `/api/v1/team-members/${teamMemberId}/property-values?active_definitions_only=true`
      );
      const mapped = next.map((row) => ({
        property_definition_id: row.property_definition_id,
        value: row.value,
        name: row.name,
        type: row.type,
        options: row.options ?? [],
        editable_by_team_member: row.editable_by_team_member,
        is_active: row.is_active
      }));
      rowsRef.current = mapped;
      setRows(mapped);
    } finally {
      setLoading(false);
    }
  }, [teamMemberId]);

  useEffect(() => {
    void loadValues();
  }, [loadValues]);

  function commitRows(next: PropertyValueRow[]) {
    rowsRef.current = next;
    setRows(next);
    schedulePersist();
  }

  function updateRow(definitionId: number, value: unknown) {
    commitRows(
      rowsRef.current.map((row) =>
        row.property_definition_id === definitionId ? { ...row, value } : row
      )
    );
  }

  function toggleMultiOption(definitionId: number, option: string) {
    const row = rowsRef.current.find((r) => r.property_definition_id === definitionId);
    if (!row || row.type !== "multi_select") {
      return;
    }
    const current = Array.isArray(row.value) ? (row.value as string[]) : [];
    const next = current.includes(option)
      ? current.filter((item) => item !== option)
      : [...current, option];
    updateRow(definitionId, next);
  }

  const activeRows = rows.filter((row) => row.is_active);

  return (
    <section className="grid gap-4">
      <div>
        <h2 className="text-lg font-semibold text-ink">{t(locale, "teamMemberPropertiesTitle")}</h2>
        <p className="mt-1 text-sm text-slate-600">{t(locale, "teamMemberPropertiesHelp")}</p>
      </div>
      {loading ? <p className="text-sm text-slate-600">{t(locale, "planningSessionLoading")}</p> : null}
      {!loading && activeRows.length === 0 ? (
        <p className="text-sm text-slate-600">{t(locale, "teamMemberPropertiesEmpty")}</p>
      ) : null}
      <div className="grid gap-3">
        {activeRows.map((row) => {
          const fieldReadOnly = !adminMode && !row.editable_by_team_member;
          return (
            <div
              key={row.property_definition_id}
              className="rounded-lg border border-slate-200 bg-slate-50/60 p-4"
            >
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <p className="text-sm font-semibold text-slate-800">{row.name}</p>
                <span className="text-xs text-slate-500">{t(locale, PROPERTY_TYPE_KEYS[row.type])}</span>
                {fieldReadOnly ? (
                  <span className="text-xs font-medium text-slate-500">
                    {t(locale, "teamMemberPropertyAdminOnly")}
                  </span>
                ) : null}
              </div>
              {fieldReadOnly ? (
                <p className="text-sm text-slate-700">{formatDisplayValue(row)}</p>
              ) : row.type === "number" ? (
                <Field label={row.name}>
                  <input
                    className={inputClass}
                    type="number"
                    value={row.value === null || row.value === undefined ? "" : String(row.value)}
                    onChange={(event) =>
                      updateRow(
                        row.property_definition_id,
                        event.target.value === "" ? null : Number(event.target.value)
                      )
                    }
                  />
                </Field>
              ) : row.type === "date" ? (
                <Field label={row.name}>
                  <input
                    className={inputClass}
                    type="date"
                    value={typeof row.value === "string" ? row.value : ""}
                    onChange={(event) =>
                      updateRow(row.property_definition_id, event.target.value || null)
                    }
                  />
                </Field>
              ) : row.type === "text" ? (
                <Field label={row.name}>
                  <input
                    className={inputClass}
                    type="text"
                    value={typeof row.value === "string" ? row.value : ""}
                    onChange={(event) =>
                      updateRow(row.property_definition_id, event.target.value || null)
                    }
                  />
                </Field>
              ) : row.type === "select" ? (
                <Field label={row.name}>
                  <select
                    className={inputClass}
                    value={typeof row.value === "string" ? row.value : ""}
                    onChange={(event) =>
                      updateRow(row.property_definition_id, event.target.value || null)
                    }
                  >
                    <option value="">{t(locale, "teamMemberPropertySelectEmpty")}</option>
                    {row.options.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </Field>
              ) : (
                <div>
                  <p className="mb-2 text-sm font-medium text-slate-700">{row.name}</p>
                  <div className="flex flex-wrap gap-2">
                    {row.options.map((option) => {
                      const selected =
                        Array.isArray(row.value) && (row.value as string[]).includes(option);
                      return (
                        <button
                          key={option}
                          type="button"
                          className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 ${
                            selected
                              ? "bg-ink text-white ring-ink"
                              : "bg-white text-slate-700 ring-slate-200"
                          }`}
                          onClick={() => toggleMultiOption(row.property_definition_id, option)}
                        >
                          {option}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
      {message ? <p className="text-sm text-red-600">{message}</p> : null}
    </section>
  );
}