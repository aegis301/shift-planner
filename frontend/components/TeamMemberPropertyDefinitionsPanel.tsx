"use client";

import { useCallback, useEffect, useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { Card } from "@/components/Card";
import {
  emptyTeamMemberPropertyDefinitionDraft,
  TeamMemberPropertyDefinitionModal,
  teamMemberPropertyDefinitionDraft,
  type TeamMemberPropertyDefinitionDraft
} from "@/components/TeamMemberPropertyDefinitionModal";
import { useLocale } from "@/components/LocaleProvider";
import { apiFetch } from "@/lib/api";
import { t } from "@/lib/i18n";
import {
  TEAM_MEMBER_PROPERTY_TYPE_KEYS,
  type TeamMemberPropertyDefinition
} from "@/lib/teamMemberProperties";

export function TeamMemberPropertyDefinitionsPanel() {
  const { locale } = useLocale();
  const [rows, setRows] = useState<TeamMemberPropertyDefinition[]>([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState<{
    id: number | null;
    draft: TeamMemberPropertyDefinitionDraft;
  } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const next = await apiFetch<TeamMemberPropertyDefinition[]>(
        "/api/v1/team-member-property-definitions"
      );
      setRows(
        [...next].sort((first, second) =>
          first.name.localeCompare(second.name, undefined, { sensitivity: "base" })
        )
      );
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
          <h1 className="text-xl font-semibold text-ink">
            {t(locale, "teamMemberPropertyDefinitionsTitle")}
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            {t(locale, "teamMemberPropertyDefinitionsHelp")}
          </p>
        </div>
        <button
          type="button"
          className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white"
          onClick={() =>
            setModal({ id: null, draft: emptyTeamMemberPropertyDefinitionDraft() })
          }
        >
          <Plus size={16} />
          {t(locale, "teamMemberPropertyDefinitionAdd")}
        </button>
      </div>
      {loading ? (
        <p className="text-sm text-slate-600">{t(locale, "planningSessionLoading")}</p>
      ) : null}
      <div className="grid gap-2">
        {rows.map((row) => (
          <div
            key={row.id}
            className={`flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3 ${
              row.is_active
                ? "border-slate-200 bg-white"
                : "border-slate-100 bg-slate-50 opacity-70"
            }`}
          >
            <div>
              <p className="font-semibold text-slate-800">{row.name}</p>
              <p className="text-xs text-slate-500">
                {t(locale, TEAM_MEMBER_PROPERTY_TYPE_KEYS[row.type])}
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
                    draft: teamMemberPropertyDefinitionDraft(row)
                  })
                }
                aria-label={t(locale, "teamMemberPropertyDefinitionEdit")}
              >
                <Pencil size={16} />
              </button>
              <button
                type="button"
                className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-rose-200 bg-rose-50 text-rose-700"
                onClick={() => void removeDefinition(row.id)}
                aria-label={t(locale, "teamMemberPropertyDefinitionDelete")}
              >
                <Trash2 size={16} />
              </button>
            </div>
          </div>
        ))}
      </div>
      {modal ? (
        <TeamMemberPropertyDefinitionModal
          initial={modal.draft}
          definitionId={modal.id}
          onClose={() => setModal(null)}
          onSaved={load}
        />
      ) : null}
    </Card>
  );
}
