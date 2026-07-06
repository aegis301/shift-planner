"use client";

import { FormEvent, useEffect, useState } from "react";
import { Clock, Download, Eye, History, Save, X } from "lucide-react";
import { API_BASE_URL, apiFetch } from "@/lib/api";
import { t, type Locale } from "@/lib/i18n";

export type PlanVersion = {
  id: number;
  planning_period_id: number;
  shift_group_id: number;
  major_version: number;
  minor_version: number;
  lifecycle_phase: "preliminary" | "published";
  trigger: string;
  note: string | null;
  created_at: string;
};

export type PlanVersionList = {
  working_major_version: number | null;
  working_minor_version: number | null;
  versions: PlanVersion[];
};

type SuggestedVersion = {
  major_version: number;
  minor_version: number;
  label: string;
};

type PlanVersionPanelProps = {
  locale: Locale;
  periodId: string;
  shiftGroupId: string;
  status: "draft" | "preliminary" | "published" | null;
  onVersionsChange?: () => void;
  onViewVersion?: (versionId: number | null) => void;
  viewingVersionId?: number | null;
};

function versionLabel(major: number | null | undefined, minor: number | null | undefined): string {
  if (major == null || minor == null) {
    return "—";
  }
  return `${major}.${minor}`;
}

export function PlanVersionPanel({
  locale,
  periodId,
  shiftGroupId,
  status,
  onVersionsChange,
  onViewVersion,
  viewingVersionId
}: PlanVersionPanelProps) {
  const [versions, setVersions] = useState<PlanVersionList | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [saveOpen, setSaveOpen] = useState(false);
  const [majorVersion, setMajorVersion] = useState("");
  const [minorVersion, setMinorVersion] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  async function loadVersions() {
    if (!periodId || !shiftGroupId) {
      setVersions(null);
      return;
    }
    const data = await apiFetch<PlanVersionList>(
      `/api/v1/planning-periods/${periodId}/versions?shift_group_id=${encodeURIComponent(shiftGroupId)}`
    );
    setVersions(data);
  }

  useEffect(() => {
    void loadVersions().catch(() => setVersions(null));
  }, [periodId, shiftGroupId, status]);

  async function openSaveModal() {
    const suggested = await apiFetch<SuggestedVersion>(
      `/api/v1/planning-periods/${periodId}/versions/suggest?shift_group_id=${encodeURIComponent(shiftGroupId)}&trigger=manual_save`
    );
    setMajorVersion(String(suggested.major_version));
    setMinorVersion(String(suggested.minor_version));
    setNote("");
    setSaveOpen(true);
  }

  async function submitSave(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    try {
      await apiFetch(`/api/v1/planning-periods/${periodId}/versions?shift_group_id=${encodeURIComponent(shiftGroupId)}`, {
        method: "POST",
        body: JSON.stringify({
          major_version: Number(majorVersion),
          minor_version: Number(minorVersion),
          note: note.trim() || null
        })
      });
      setSaveOpen(false);
      await loadVersions();
      onVersionsChange?.();
    } finally {
      setSaving(false);
    }
  }

  const workingLabel = versionLabel(versions?.working_major_version, versions?.working_minor_version);
  const statusLabel =
    status === "published"
      ? t(locale, "periodStatusPublished")
      : status === "preliminary"
        ? t(locale, "periodStatusPreliminary")
        : t(locale, "periodStatusDraft");

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1 rounded-full border border-violet-200 bg-violet-50 px-2.5 py-1 text-xs font-semibold text-violet-900">
          v{workingLabel} · {statusLabel}
        </span>
        {status === "preliminary" ? (
          <button
            type="button"
            onClick={() => void openSaveModal()}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-800 shadow-sm hover:bg-slate-50"
          >
            <Save className="h-3.5 w-3.5" />
            {t(locale, "planVersionSave")}
          </button>
        ) : null}
        <button
          type="button"
          onClick={() => setHistoryOpen(true)}
          className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-800 shadow-sm hover:bg-slate-50"
        >
          <History className="h-3.5 w-3.5" />
          {t(locale, "planVersionHistory")}
        </button>
        {viewingVersionId ? (
          <button
            type="button"
            onClick={() => onViewVersion?.(null)}
            className="inline-flex items-center gap-1 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-xs font-medium text-amber-900"
          >
            <X className="h-3.5 w-3.5" />
            {t(locale, "planVersionBackToCurrent")}
          </button>
        ) : null}
      </div>

      {saveOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
          <form
            onSubmit={(event) => void submitSave(event)}
            className="w-full max-w-md rounded-2xl bg-white p-5 shadow-xl ring-1 ring-slate-200"
          >
            <h3 className="text-lg font-semibold text-ink">{t(locale, "planVersionSaveTitle")}</h3>
            <p className="mt-1 text-sm text-slate-600">{t(locale, "planVersionSaveHelp")}</p>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <label className="grid gap-1 text-sm">
                <span>{t(locale, "planVersionMajor")}</span>
                <input
                  value={majorVersion}
                  onChange={(event) => setMajorVersion(event.target.value)}
                  className="rounded-lg border border-slate-200 px-3 py-2"
                  required
                />
              </label>
              <label className="grid gap-1 text-sm">
                <span>{t(locale, "planVersionMinor")}</span>
                <input
                  value={minorVersion}
                  onChange={(event) => setMinorVersion(event.target.value)}
                  className="rounded-lg border border-slate-200 px-3 py-2"
                  required
                />
              </label>
            </div>
            <label className="mt-3 grid gap-1 text-sm">
              <span>{t(locale, "planVersionNote")}</span>
              <textarea
                value={note}
                onChange={(event) => setNote(event.target.value)}
                className="min-h-20 rounded-lg border border-slate-200 px-3 py-2"
              />
            </label>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setSaveOpen(false)}
                className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
              >
                {t(locale, "cancel")}
              </button>
              <button
                type="submit"
                disabled={saving}
                className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white"
              >
                {t(locale, "planVersionSave")}
              </button>
            </div>
          </form>
        </div>
      ) : null}

      {historyOpen ? (
        <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/30">
          <div className="flex h-full w-full max-w-md flex-col bg-white shadow-2xl ring-1 ring-slate-200">
            <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
              <h3 className="text-lg font-semibold text-ink">{t(locale, "planVersionHistory")}</h3>
              <button type="button" onClick={() => setHistoryOpen(false)} className="rounded-lg p-2 hover:bg-slate-100">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              {!versions?.versions.length ? (
                <p className="text-sm text-slate-600">{t(locale, "planVersionHistoryEmpty")}</p>
              ) : (
                <ul className="grid gap-3">
                  {versions.versions.map((version) => (
                    <li key={version.id} className="rounded-xl border border-slate-200 p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <p className="font-semibold text-ink">
                            v{version.major_version}.{version.minor_version}
                          </p>
                          <p className="text-xs text-slate-600">
                            {version.lifecycle_phase === "published"
                              ? t(locale, "periodStatusPublished")
                              : t(locale, "periodStatusPreliminary")}
                          </p>
                        </div>
                        <div className="flex gap-1">
                          <button
                            type="button"
                            title={t(locale, "planVersionView")}
                            onClick={() => {
                              onViewVersion?.(version.id);
                              setHistoryOpen(false);
                            }}
                            className="rounded-lg border border-slate-200 p-2 hover:bg-slate-50"
                          >
                            <Eye className="h-4 w-4" />
                          </button>
                          <a
                            href={`${API_BASE_URL}/api/v1/planning-periods/${periodId}/versions/${version.id}/export/roster-matrix.csv`}
                            className="rounded-lg border border-slate-200 p-2 hover:bg-slate-50"
                            title={t(locale, "exportRosterCsv")}
                          >
                            <Download className="h-4 w-4" />
                          </a>
                        </div>
                      </div>
                      {version.note ? <p className="mt-2 text-sm text-slate-700">{version.note}</p> : null}
                      <p className="mt-2 inline-flex items-center gap-1 text-xs text-slate-500">
                        <Clock className="h-3 w-3" />
                        {new Date(version.created_at).toLocaleString()}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
