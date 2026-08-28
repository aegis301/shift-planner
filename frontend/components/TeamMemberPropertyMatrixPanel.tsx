"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Plus, RefreshCw } from "lucide-react";
import { Card } from "@/components/Card";
import {
  emptyTeamMemberPropertyDefinitionDraft,
  TeamMemberPropertyDefinitionModal
} from "@/components/TeamMemberPropertyDefinitionModal";
import { TeamMemberPropertyCellEditor } from "@/components/TeamMemberPropertyCellEditor";
import { useLocale } from "@/components/LocaleProvider";
import { ApiError, apiFetch } from "@/lib/api";
import { dataTableScrollShellClassName } from "@/lib/dataTableLayout";
import { t } from "@/lib/i18n";
import {
  TEAM_MEMBER_PROPERTY_TYPE_KEYS,
  type TeamMemberPropertyDefinition
} from "@/lib/teamMemberProperties";

type PropertyMatrixMember = {
  id: number;
  first_name: string;
  last_name: string;
  nickname: string | null;
  is_active: boolean;
};

type PropertyMatrixValue = {
  team_member_id: number;
  property_definition_id: number;
  value: unknown;
};

type PropertyMatrix = {
  definitions: TeamMemberPropertyDefinition[];
  members: PropertyMatrixMember[];
  values: PropertyMatrixValue[];
};

type SaveStatus = "saving" | "saved" | "error";

function valueKey(teamMemberId: number, definitionId: number): string {
  return `${teamMemberId}:${definitionId}`;
}

export function TeamMemberPropertyMatrixPanel() {
  const { locale } = useLocale();
  const [matrix, setMatrix] = useState<PropertyMatrix>({
    definitions: [],
    members: [],
    values: []
  });
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [statuses, setStatuses] = useState<Record<string, SaveStatus>>({});
  const [showInactiveMembers, setShowInactiveMembers] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [definitionModalOpen, setDefinitionModalOpen] = useState(false);
  const persistTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setMessage("");
    try {
      const next = await apiFetch<PropertyMatrix>(
        `/api/v1/team-member-property-matrix?active_members_only=${
          showInactiveMembers ? "false" : "true"
        }`
      );
      setMatrix(next);
      setValues(
        Object.fromEntries(
          next.values.map((row) => [
            valueKey(row.team_member_id, row.property_definition_id),
            row.value
          ])
        )
      );
      setStatuses({});
    } catch (error) {
      setMessage(
        error instanceof ApiError && typeof error.detail === "string"
          ? error.detail
          : t(locale, "teamMemberPropertyMatrixLoadError")
      );
    } finally {
      setLoading(false);
    }
  }, [locale, showInactiveMembers]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const timers = persistTimers.current;
    return () => {
      Object.values(timers).forEach(clearTimeout);
    };
  }, []);

  async function persistValue(
    teamMemberId: number,
    definitionId: number,
    value: unknown
  ) {
    const key = valueKey(teamMemberId, definitionId);
    setStatuses((previous) => ({ ...previous, [key]: "saving" }));
    try {
      await apiFetch(`/api/v1/team-members/${teamMemberId}/property-values`, {
        method: "PUT",
        body: JSON.stringify({
          values: [{ property_definition_id: definitionId, value }]
        })
      });
      setStatuses((previous) => ({ ...previous, [key]: "saved" }));
      setMessage("");
    } catch (error) {
      setStatuses((previous) => ({ ...previous, [key]: "error" }));
      setMessage(
        error instanceof ApiError && typeof error.detail === "string"
          ? error.detail
          : t(locale, "teamMemberPropertyMatrixSaveError")
      );
    }
  }

  function updateValue(
    teamMemberId: number,
    definitionId: number,
    value: unknown
  ) {
    const key = valueKey(teamMemberId, definitionId);
    setValues((previous) => ({ ...previous, [key]: value }));
    setStatuses((previous) => ({ ...previous, [key]: "saving" }));
    if (persistTimers.current[key]) {
      clearTimeout(persistTimers.current[key]);
    }
    persistTimers.current[key] = setTimeout(() => {
      delete persistTimers.current[key];
      void persistValue(teamMemberId, definitionId, value);
    }, 400);
  }

  return (
    <Card>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-ink">
            {t(locale, "teamMemberPropertyMatrixTitle")}
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            {t(locale, "teamMemberPropertyMatrixHelp")}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-200 px-3 text-sm font-semibold text-slate-700"
            onClick={() => void load()}
          >
            <RefreshCw size={16} />
            {t(locale, "refresh")}
          </button>
          <button
            type="button"
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white"
            onClick={() => setDefinitionModalOpen(true)}
          >
            <Plus size={16} />
            {t(locale, "teamMemberPropertyDefinitionAdd")}
          </button>
        </div>
      </div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <label className="inline-flex items-center gap-2 text-sm font-medium text-slate-700">
          <input
            type="checkbox"
            checked={showInactiveMembers}
            onChange={(event) => setShowInactiveMembers(event.target.checked)}
          />
          {t(locale, "teamMemberPropertyMatrixShowInactiveMembers")}
        </label>
        <Link
          href="/organization/team/properties/definitions"
          className="text-sm font-semibold text-ink underline-offset-4 hover:underline"
        >
          {t(locale, "teamMemberPropertyDefinitionsNav")}
        </Link>
      </div>
      {loading ? (
        <p className="text-sm text-slate-600">{t(locale, "planningSessionLoading")}</p>
      ) : null}
      {!loading && matrix.definitions.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 p-6 text-center">
          <p className="text-sm text-slate-600">
            {t(locale, "teamMemberPropertyMatrixEmptyDefinitions")}
          </p>
          <button
            type="button"
            className="mt-3 inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white"
            onClick={() => setDefinitionModalOpen(true)}
          >
            <Plus size={16} />
            {t(locale, "teamMemberPropertyDefinitionAdd")}
          </button>
        </div>
      ) : null}
      {!loading &&
      matrix.definitions.length > 0 &&
      matrix.members.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-600">
          {t(locale, "teamMemberPropertyMatrixEmptyMembers")}
        </p>
      ) : null}
      {!loading && matrix.definitions.length > 0 && matrix.members.length > 0 ? (
        <div
          className={`${dataTableScrollShellClassName} rounded-lg border border-slate-200`}
        >
          <table className="min-w-max border-collapse text-left">
            <thead className="sticky top-0 z-20 bg-slate-50">
              <tr>
                <th className="sticky left-0 z-30 min-w-52 border-b border-r border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-600">
                  {t(locale, "teamMemberPropertyMatrixMemberColumn")}
                </th>
                {matrix.definitions.map((definition) => (
                  <th
                    key={definition.id}
                    className="min-w-44 border-b border-r border-slate-200 px-3 py-2"
                  >
                    <span className="block text-sm font-semibold text-slate-800">
                      {definition.name}
                    </span>
                    <span className="block text-xs font-normal text-slate-500">
                      {t(locale, TEAM_MEMBER_PROPERTY_TYPE_KEYS[definition.type])}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {matrix.members.map((member) => (
                <tr key={member.id} className={member.is_active ? "bg-white" : "bg-slate-50"}>
                  <th className="sticky left-0 z-10 border-b border-r border-slate-200 bg-inherit px-3 py-2">
                    <span className="block text-sm font-semibold text-slate-800">
                      {member.first_name} {member.last_name}
                    </span>
                    {member.nickname ? (
                      <span className="block text-xs font-normal text-slate-500">
                        {member.nickname}
                      </span>
                    ) : null}
                  </th>
                  {matrix.definitions.map((definition) => {
                    const key = valueKey(member.id, definition.id);
                    const status = statuses[key];
                    return (
                      <td
                        key={definition.id}
                        className="border-b border-r border-slate-200 px-2 py-2 align-top"
                      >
                        <TeamMemberPropertyCellEditor
                          definition={definition}
                          value={values[key] ?? null}
                          onChange={(value) =>
                            updateValue(member.id, definition.id, value)
                          }
                          compact
                        />
                        {status ? (
                          <span
                            className={`mt-1 block text-[11px] ${
                              status === "error" ? "text-red-600" : "text-slate-500"
                            }`}
                          >
                            {t(
                              locale,
                              status === "saving"
                                ? "teamMemberPropertyMatrixSaving"
                                : status === "saved"
                                  ? "teamMemberPropertyMatrixSaved"
                                  : "teamMemberPropertyMatrixSaveError"
                            )}
                          </span>
                        ) : null}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {message ? <p className="mt-3 text-sm text-red-600">{message}</p> : null}
      {definitionModalOpen ? (
        <TeamMemberPropertyDefinitionModal
          initial={emptyTeamMemberPropertyDefinitionDraft()}
          definitionId={null}
          onClose={() => setDefinitionModalOpen(false)}
          onSaved={load}
        />
      ) : null}
    </Card>
  );
}
