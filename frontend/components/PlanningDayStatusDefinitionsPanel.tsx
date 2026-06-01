"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Pencil, Plus, Trash2, X } from "lucide-react";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";
import { ApiError, apiFetch } from "@/lib/api";
import { t } from "@/lib/i18n";
import {
  PLANNING_DAY_STATUS_COLOR_PRESETS,
  planningDayStatusBadgeClass,
  planningDayStatusLabel,
  sortPlanningDayStatusDefinitions,
  type PlanningDayStatusColorPreset,
  type PlanningDayStatusDefinition
} from "@/lib/planningDayStatus";

type Draft = {
  code: string;
  label: string;
  color_preset: PlanningDayStatusColorPreset;
  blocks_roster_assignment: boolean;
  is_active: boolean;
};

function emptyDraft(): Draft {
  return {
    code: "",
    label: "",
    color_preset: "emerald",
    blocks_roster_assignment: true,
    is_active: true
  };
}

function DayStatusModal({
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
  const isCreate = definitionId === null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    try {
      if (isCreate) {
        await apiFetch("/api/v1/planning-day-status-definitions", {
          method: "POST",
          body: JSON.stringify({
            code: draft.code.trim().toLowerCase(),
            label: draft.label.trim(),
            color_preset: draft.color_preset,
            blocks_roster_assignment: draft.blocks_roster_assignment,
            is_active: draft.is_active
          })
        });
      } else {
        await apiFetch(`/api/v1/planning-day-status-definitions/${definitionId}`, {
          method: "PATCH",
          body: JSON.stringify({
            label: draft.label.trim(),
            color_preset: draft.color_preset,
            blocks_roster_assignment: draft.blocks_roster_assignment,
            is_active: draft.is_active
          })
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 px-3 py-6 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-xl bg-white p-5 shadow-soft ring-1 ring-slate-200">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-ink">
            {isCreate ? t(locale, "planningDayStatusAdd") : t(locale, "planningDayStatusEdit")}
          </h2>
          <button type="button" className="rounded-lg p-2 text-slate-600 hover:bg-slate-100" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <form className="grid gap-3" onSubmit={(event) => void submit(event)}>
          {isCreate ? (
            <Field label={t(locale, "planningDayStatusCode")}>
              <input
                className={inputClass}
                required
                pattern="[a-z][a-z0-9_]*"
                value={draft.code}
                onChange={(event) => setDraft((prev) => ({ ...prev, code: event.target.value }))}
              />
            </Field>
          ) : (
            <Field label={t(locale, "planningDayStatusCode")}>
              <input className={inputClass} disabled value={draft.code} />
            </Field>
          )}
          <Field label={t(locale, "name")}>
            <input
              className={inputClass}
              required
              value={draft.label}
              onChange={(event) => setDraft((prev) => ({ ...prev, label: event.target.value }))}
            />
          </Field>
          <Field label={t(locale, "planningDayStatusColor")}>
            <div className="grid grid-cols-4 gap-2 sm:grid-cols-6">
              {PLANNING_DAY_STATUS_COLOR_PRESETS.map((preset) => (
                <button
                  key={preset}
                  type="button"
                  className={`rounded-lg px-2 py-2 text-xs font-semibold ring-2 ${planningDayStatusBadgeClass(preset)} ${
                    draft.color_preset === preset ? "ring-ink" : "ring-transparent"
                  }`}
                  onClick={() => setDraft((prev) => ({ ...prev, color_preset: preset }))}
                >
                  {preset}
                </button>
              ))}
            </div>
          </Field>
          <label className="inline-flex items-center gap-2 text-sm font-medium text-slate-700">
            <input
              type="checkbox"
              checked={draft.blocks_roster_assignment}
              onChange={(event) =>
                setDraft((prev) => ({ ...prev, blocks_roster_assignment: event.target.checked }))
              }
            />
            {t(locale, "planningDayStatusBlocksRoster")}
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

export function PlanningDayStatusDefinitionsPanel() {
  const { locale } = useLocale();
  const [rows, setRows] = useState<PlanningDayStatusDefinition[]>([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState<{ id: number | null; draft: Draft } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const next = await apiFetch<PlanningDayStatusDefinition[]>("/api/v1/planning-day-status-definitions");
      setRows(sortPlanningDayStatusDefinitions(next));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function removeDefinition(id: number) {
    try {
      await apiFetch(`/api/v1/planning-day-status-definitions/${id}`, { method: "DELETE" });
      await load();
    } catch (e) {
      if (e instanceof ApiError && typeof e.detail === "string") {
        window.alert(e.detail);
      }
    }
  }

  return (
    <Card>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-ink">{t(locale, "planningDayStatusDefinitionsTitle")}</h1>
          <p className="mt-1 text-sm text-slate-600">{t(locale, "planningDayStatusDefinitionsHelp")}</p>
        </div>
        <button
          type="button"
          className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white"
          onClick={() => setModal({ id: null, draft: emptyDraft() })}
        >
          <Plus size={16} />
          {t(locale, "planningDayStatusAdd")}
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
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ${planningDayStatusBadgeClass(row.color_preset)}`}
              >
                {planningDayStatusLabel(row, locale)}
              </span>
              <p className="text-xs text-slate-500">
                <span className="font-mono">{row.code}</span>
                {row.blocks_roster_assignment
                  ? ` · ${t(locale, "planningDayStatusBlocksRosterShort")}`
                  : ` · ${t(locale, "planningDayStatusAllowsRosterShort")}`}
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
                      code: row.code,
                      label: row.label,
                      color_preset: row.color_preset,
                      blocks_roster_assignment: row.blocks_roster_assignment,
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
        <DayStatusModal initial={modal.draft} definitionId={modal.id} onClose={() => setModal(null)} onSaved={load} />
      ) : null}
    </Card>
  );
}
