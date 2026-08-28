"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { TeamMemberPropertyCellEditor } from "@/components/TeamMemberPropertyCellEditor";
import { useLocale } from "@/components/LocaleProvider";
import { ApiError, apiFetch } from "@/lib/api";
import { t } from "@/lib/i18n";
import {
  buildTeamMemberPropertyValuesPayload,
  TEAM_MEMBER_PROPERTY_TYPE_KEYS,
  type TeamMemberPropertyValueRow
} from "@/lib/teamMemberProperties";

export function TeamMemberPropertyValuesEditor({
  teamMemberId,
  adminMode = false
}: {
  teamMemberId: number;
  adminMode?: boolean;
}) {
  const { locale } = useLocale();
  const [rows, setRows] = useState<TeamMemberPropertyValueRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const rowsRef = useRef<TeamMemberPropertyValueRow[]>([]);
  const persistTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  rowsRef.current = rows;

  const flushPersist = useCallback(async () => {
    const editableRows = rowsRef.current.filter(
      (row) => adminMode || row.editable_by_team_member
    );
    if (editableRows.length === 0) {
      return;
    }
    try {
      const saved = await apiFetch<TeamMemberPropertyValueRow[]>(
        `/api/v1/team-members/${teamMemberId}/property-values`,
        {
          method: "PUT",
          body: JSON.stringify(buildTeamMemberPropertyValuesPayload(editableRows))
        }
      );
      rowsRef.current = saved;
      setRows(saved);
      setMessage("");
    } catch (error) {
      setMessage(
        error instanceof ApiError && typeof error.detail === "string"
          ? error.detail
          : t(locale, "orgManagementInviteError")
      );
    }
  }, [adminMode, locale, teamMemberId]);

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
      const hadPendingChanges = persistTimerRef.current !== null;
      if (persistTimerRef.current) {
        clearTimeout(persistTimerRef.current);
        persistTimerRef.current = null;
      }
      if (hadPendingChanges) {
        void flushPersistRef.current();
      }
    };
  }, []);

  const loadValues = useCallback(async () => {
    setLoading(true);
    try {
      const next = await apiFetch<TeamMemberPropertyValueRow[]>(
        `/api/v1/team-members/${teamMemberId}/property-values?active_definitions_only=true`
      );
      rowsRef.current = next;
      setRows(next);
    } finally {
      setLoading(false);
    }
  }, [teamMemberId]);

  useEffect(() => {
    void loadValues();
  }, [loadValues]);

  function updateRow(definitionId: number, value: unknown) {
    const next = rowsRef.current.map((row) =>
      row.property_definition_id === definitionId ? { ...row, value } : row
    );
    rowsRef.current = next;
    setRows(next);
    schedulePersist();
  }

  const activeRows = rows.filter((row) => row.is_active);
  return (
    <section className="grid gap-4">
      <div>
        <h2 className="text-lg font-semibold text-ink">
          {t(locale, "teamMemberPropertiesTitle")}
        </h2>
        <p className="mt-1 text-sm text-slate-600">
          {t(locale, "teamMemberPropertiesHelp")}
        </p>
      </div>
      {loading ? (
        <p className="text-sm text-slate-600">{t(locale, "planningSessionLoading")}</p>
      ) : null}
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
                <span className="text-xs text-slate-500">
                  {t(locale, TEAM_MEMBER_PROPERTY_TYPE_KEYS[row.type])}
                </span>
                {fieldReadOnly ? (
                  <span className="text-xs font-medium text-slate-500">
                    {t(locale, "teamMemberPropertyAdminOnly")}
                  </span>
                ) : null}
              </div>
              <TeamMemberPropertyCellEditor
                definition={row}
                value={row.value}
                onChange={(value) => updateRow(row.property_definition_id, value)}
                readOnly={fieldReadOnly}
              />
            </div>
          );
        })}
      </div>
      {message ? <p className="text-sm text-red-600">{message}</p> : null}
    </section>
  );
}
