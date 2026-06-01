"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Download, ListChecks, MessageSquarePlus, MessageSquareText, RefreshCw, Save, X } from "lucide-react";
import { API_BASE_URL, apiFetch } from "@/lib/api";
import { dataTableScrollShellClassName } from "@/lib/dataTableLayout";
import { teamMemberPlanningDisplayName } from "@/lib/teamMemberDisplay";
import { t, type Locale } from "@/lib/i18n";
import {
  activePlanningDayStatusDefinitions,
  badgeClassForPlanningDayStatusCode,
  labelForPlanningDayStatusCode,
  planningDayStatusBadgeClass,
  planningDayStatusByCode,
  planningDayStatusLabel,
  type PlanningDayStatusDefinition
} from "@/lib/planningDayStatus";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";

type PlanningShiftIntentKind = "wish" | "no_go";

type SaveMatrixIntentFn = (
  memberId: number,
  cellDate: string,
  templateId: number,
  kind: PlanningShiftIntentKind | null,
  intentShiftGroupId?: number
) => Promise<void>;

type TemplateSlotDay = { cell_date: string; shift_template_id: number; shift_group_id?: number | null };

type IntentTemplateRow = { templateId: number; shiftGroupId: number };

type MatrixShiftTemplate = {
  id: number;
  code: string;
  name: string;
  category: string;
  display_order: number;
  is_active: boolean;
};

type MatrixTeamMember = {
  id: number;
  first_name: string;
  last_name: string;
  nickname?: string | null;
  email: string;
  employment_percentage: number;
  planning_preferences?: string | null;
};

type MatrixDay = {
  date: string;
  weekday: string;
};

type PlanningCell = {
  id: number;
  planning_period_id: number;
  team_member_id: number;
  cell_date: string;
  status: string;
  comment: string | null;
};

type MatrixShiftIntent = {
  id: number;
  planning_period_id: number;
  team_member_id: number;
  cell_date: string;
  shift_group_id: number;
  shift_template_id: number;
  kind: PlanningShiftIntentKind;
  source: string;
};

type PlanningMatrix = {
  planning_period: { id: number; year: number; month: number; status: string };
  team_members: MatrixTeamMember[];
  days: MatrixDay[];
  cells: PlanningCell[];
  day_status_definitions: PlanningDayStatusDefinition[];
  shift_templates: MatrixShiftTemplate[];
  shift_intents: MatrixShiftIntent[];
  template_slot_days: TemplateSlotDay[];
};

type TeamMemberIntentStats = { wish: number; noGo: number };

type PlanningPeriod = {
  id: number;
  year: number;
  month: number;
  status: string;
};

type TeamMemberPeriodNote = {
  id: number;
  planning_period_id: number;
  team_member_id: number;
  summary: string | null;
  wishes_response_received?: boolean;
};

function formatPlanningMonthTitle(locale: Locale, year: number, month: number) {
  return new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-US", {
    month: "long",
    year: "numeric"
  }).format(new Date(year, month - 1, 1));
}

function normalizePlanningStatus(value: string | undefined, definitions: PlanningDayStatusDefinition[]): string {
  if (!value) {
    return "";
  }
  return planningDayStatusByCode(definitions).has(value) ? value : "";
}

function statusMeta(status: string, definitions: PlanningDayStatusDefinition[], locale: Locale) {
  const row = planningDayStatusByCode(definitions).get(status);
  if (!row) {
    return null;
  }
  return {
    value: row.code,
    label: planningDayStatusLabel(row, locale),
    color: planningDayStatusBadgeClass(row.color_preset)
  };
}

function intentTemplateRowsForDate(matrix: PlanningMatrix, cellDate: string): IntentTemplateRow[] {
  const seen = new Set<string>();
  const out: IntentTemplateRow[] = [];
  for (const row of matrix.template_slot_days ?? []) {
    if (row.cell_date !== cellDate || row.shift_group_id == null) {
      continue;
    }
    const key = `${row.shift_template_id}:${row.shift_group_id}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    out.push({ templateId: row.shift_template_id, shiftGroupId: row.shift_group_id });
  }
  out.sort((a, b) => a.templateId - b.templateId || a.shiftGroupId - b.shiftGroupId);
  return out;
}

function templateLabel(matrix: PlanningMatrix, templateId: number, locale: Locale): string {
  const template = matrix.shift_templates?.find((item) => item.id === templateId);
  if (!template) {
    return `#${templateId}`;
  }
  return template.name;
}

function formatDate(locale: Locale, value: string) {
  return new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-GB", {
    weekday: "short",
    day: "2-digit",
    month: "2-digit"
  }).format(new Date(`${value}T12:00:00`));
}

function teamMemberLabel(member: MatrixTeamMember): string {
  return teamMemberPlanningDisplayName(member);
}

function shiftGroupQuery(shiftGroupId?: string) {
  if (!shiftGroupId) {
    return "";
  }
  return `?shift_group_id=${encodeURIComponent(shiftGroupId)}`;
}

export function MatrixEditor({
  periodId: controlledPeriodId,
  compact = false,
  shiftGroupId,
  editableMemberId,
  readOnly = false,
  dayFeedbackAlwaysVisible = false,
  onChanged
}: {
  periodId?: string;
  compact?: boolean;
  shiftGroupId?: string;
  editableMemberId?: number;
  readOnly?: boolean;
  dayFeedbackAlwaysVisible?: boolean;
  onChanged?: () => void | Promise<void>;
} = {}) {
  const { locale } = useLocale();
  const currentDate = new Date();
  const [periodId, setPeriodId] = useState("1");
  const [newYear, setNewYear] = useState(String(currentDate.getFullYear()));
  const [newMonth, setNewMonth] = useState(String(currentDate.getMonth() + 1));
  const [matrix, setMatrix] = useState<PlanningMatrix | null>(null);
  const [activeMemberId, setActiveMemberId] = useState<number | null>(null);
  const [notes, setNotes] = useState<TeamMemberPeriodNote[]>([]);
  const [noteMember, setNoteMember] = useState<MatrixTeamMember | null>(null);
  const [preferencesDraft, setPreferencesDraft] = useState("");
  const [summary, setSummary] = useState("");
  const [message, setMessage] = useState("");
  const [savingCells, setSavingCells] = useState(0);
  const [isMemberCommentModalOpen, setIsMemberCommentModalOpen] = useState(false);

  const groupQuery = useMemo(() => shiftGroupQuery(shiftGroupId), [shiftGroupId]);
  const emphasizeStoredDayComments = editableMemberId == null;

  const cellMap = useMemo(() => {
    const map = new Map<string, PlanningCell>();
    matrix?.cells.forEach((cell) => map.set(`${cell.cell_date}:${cell.team_member_id}`, cell));
    return map;
  }, [matrix]);

  const intentStatsByMember = useMemo(() => {
    const out = new Map<number, TeamMemberIntentStats>();
    for (const member of matrix?.team_members ?? []) {
      out.set(member.id, { wish: 0, noGo: 0 });
    }
    for (const row of matrix?.shift_intents ?? []) {
      const entry = out.get(row.team_member_id);
      if (!entry) {
        continue;
      }
      if (row.kind === "wish") {
        entry.wish += 1;
      } else if (row.kind === "no_go") {
        entry.noGo += 1;
      }
    }
    return out;
  }, [matrix?.team_members, matrix?.shift_intents]);

  const loadMatrixById = useCallback(async (nextPeriodId: string) => {
    const next = await apiFetch<PlanningMatrix>(`/api/v1/matrix/${nextPeriodId}${groupQuery}`);
    const nextNotes = await apiFetch<TeamMemberPeriodNote[]>(`/api/v1/matrix/${nextPeriodId}/notes${groupQuery}`);
    setMatrix({
      ...next,
      shift_templates: next.shift_templates ?? [],
      shift_intents: next.shift_intents ?? [],
      template_slot_days: next.template_slot_days ?? []
    });
    setNotes(nextNotes);
    setActiveMemberId(next.team_members[0]?.id ?? null);
  }, [groupQuery]);

  const activePeriodId = controlledPeriodId ?? periodId;

  const loadMatrix = useCallback(async () => {
    await loadMatrixById(activePeriodId);
  }, [activePeriodId, loadMatrixById]);

  async function manualSave() {
    await loadMatrix();
    setMessage(t(locale, "saved"));
  }

  useEffect(() => {
    if (controlledPeriodId) {
      void loadMatrixById(controlledPeriodId);
      return;
    }

    async function loadLatestPeriod() {
      const periods = await apiFetch<PlanningPeriod[]>("/api/v1/planning-periods");
      const latest = periods[0];
      if (!latest) {
        return;
      }
      const nextPeriodId = String(latest.id);
      setPeriodId(nextPeriodId);
      await loadMatrixById(nextPeriodId);
    }

    void loadLatestPeriod();
  }, [controlledPeriodId, loadMatrixById, groupQuery]);

  async function createAndLoadPeriod(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const period = await apiFetch<PlanningPeriod>("/api/v1/planning-periods", {
      method: "POST",
      body: JSON.stringify({ year: Number(newYear), month: Number(newMonth) })
    });
    const nextPeriodId = String(period.id);
    setPeriodId(nextPeriodId);
    await loadMatrixById(nextPeriodId);
    setMessage(`${t(locale, "saved")}: ${t(locale, "periodId")} ${nextPeriodId}`);
  }

  useEffect(() => {
    const memberId = noteMember?.id ?? activeMemberId;
    const note = notes.find((item) => item.team_member_id === memberId);
    const memberRow = matrix?.team_members.find((item) => item.id === memberId);
    setPreferencesDraft(memberRow?.planning_preferences ?? "");
    setSummary(note?.summary ?? "");
  }, [activeMemberId, noteMember?.id, notes, matrix?.team_members]);

  useEffect(() => {
    if (editableMemberId != null) {
      setActiveMemberId(editableMemberId);
    }
  }, [editableMemberId]);

  async function saveCell(memberId: number, cellDate: string, status: string, comment?: string | null) {
    setSavingCells((count) => count + 1);
    try {
      if (!status) {
        await apiFetch(`/api/v1/matrix/${activePeriodId}/cells/clear`, {
          method: "POST",
          body: JSON.stringify({ team_member_id: memberId, cell_date: cellDate })
        });
      } else {
        await apiFetch(`/api/v1/matrix/${activePeriodId}/cells`, {
          method: "PUT",
          body: JSON.stringify({ team_member_id: memberId, cell_date: cellDate, status, comment: comment ?? null })
        });
      }
      setMessage(t(locale, "autosaved"));
      await onChanged?.();
    } finally {
      setSavingCells((count) => Math.max(0, count - 1));
    }
  }

  const saveIntent = useCallback<SaveMatrixIntentFn>(
    async (memberId, cellDate, templateId, kind, intentShiftGroupId) => {
      const gid = intentShiftGroupId ?? (shiftGroupId ? Number(shiftGroupId) : undefined);
      if (gid == null || Number.isNaN(gid)) {
        return;
      }
      setSavingCells((count) => count + 1);
      try {
        await apiFetch(`/api/v1/matrix/${activePeriodId}/shift-intents/bulk`, {
          method: "PUT",
          body: JSON.stringify({
            intents: [
              {
                team_member_id: memberId,
                cell_date: cellDate,
                shift_group_id: gid,
                shift_template_id: templateId,
                kind
              }
            ]
          })
        });
        setMessage(t(locale, "autosaved"));
        await loadMatrixById(activePeriodId);
        await onChanged?.();
      } finally {
        setSavingCells((count) => Math.max(0, count - 1));
      }
    },
    [activePeriodId, loadMatrixById, locale, onChanged, shiftGroupId]
  );

  async function persistNote(memberId: number, monthlyCommentOnly = false) {
    if (!memberId) return;
    const prev = notes.find((item) => item.team_member_id === memberId);
    const body: Record<string, unknown> = {
      team_member_id: memberId,
      summary,
      wishes_response_received: prev?.wishes_response_received ?? false
    };
    if (!monthlyCommentOnly) {
      body.planning_preferences = preferencesDraft.trim() === "" ? null : preferencesDraft;
      body.sync_planning_preferences = true;
    }
    await apiFetch(`/api/v1/matrix/${activePeriodId}/notes`, {
      method: "PUT",
      body: JSON.stringify(body)
    });
    setNotes(await apiFetch<TeamMemberPeriodNote[]>(`/api/v1/matrix/${activePeriodId}/notes${groupQuery}`));
    if (!monthlyCommentOnly) {
      setMatrix((prev) => {
        if (!prev) {
          return prev;
        }
        const nextPrefs = preferencesDraft.trim() === "" ? null : preferencesDraft;
        return {
          ...prev,
          team_members: prev.team_members.map((m) => (m.id === memberId ? { ...m, planning_preferences: nextPrefs } : m))
        };
      });
    }
    setMessage(t(locale, "saved"));
    await onChanged?.();
  }

  const toggleWishesAcknowledged = useCallback(
    async (memberId: number) => {
      const prev = notes.find((item) => item.team_member_id === memberId);
      const next = !(prev?.wishes_response_received ?? false);
      setSavingCells((count) => count + 1);
      try {
        await apiFetch(`/api/v1/matrix/${activePeriodId}/notes`, {
          method: "PUT",
          body: JSON.stringify({
            team_member_id: memberId,
            summary: prev?.summary ?? null,
            wishes_response_received: next
          })
        });
        setNotes(await apiFetch<TeamMemberPeriodNote[]>(`/api/v1/matrix/${activePeriodId}/notes${groupQuery}`));
        setMessage(t(locale, "saved"));
        await onChanged?.();
      } finally {
        setSavingCells((count) => Math.max(0, count - 1));
      }
    },
    [activePeriodId, groupQuery, locale, notes, onChanged]
  );

  async function saveNote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const memberId = noteMember?.id ?? activeMemberId;
    if (!memberId) {
      return;
    }
    await persistNote(memberId);
  }

  return (
    <div className="grid gap-5">
      {!compact ? (
        <Card>
          <div className="grid gap-5">
            <div>
              <h1 className="text-2xl font-semibold text-ink">{t(locale, "matrixEditor")}</h1>
              <p className="mt-2 max-w-3xl text-sm text-slate-600">{t(locale, "matrixHelp")}</p>
            </div>
            <form className="flex flex-wrap items-end gap-2 rounded-lg bg-slate-50 p-3 ring-1 ring-slate-200" onSubmit={createAndLoadPeriod}>
              <Field label={t(locale, "year")}>
                <input className={`${inputClass} w-28`} value={newYear} onChange={(event) => setNewYear(event.target.value)} type="number" min="2020" max="2100" />
              </Field>
              <Field label={t(locale, "month")}>
                <input className={`${inputClass} w-24`} value={newMonth} onChange={(event) => setNewMonth(event.target.value)} type="number" min="1" max="12" />
              </Field>
              <button className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-mint px-4 text-sm font-semibold text-ink">
                <Save size={17} />
                {t(locale, "createAndLoadPeriod")}
              </button>
            </form>
            <div className="flex flex-wrap items-end gap-2">
              <label className="grid gap-1 text-sm font-medium text-slate-700">
                {t(locale, "periodId")}
                <input className={`${inputClass} w-24`} value={periodId} onChange={(event) => setPeriodId(event.target.value)} />
              </label>
              <button
                className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white"
                onClick={loadMatrix}
              >
                <RefreshCw size={17} />
                {t(locale, "loadMatrix")}
              </button>
              <button
                className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-mint px-4 text-sm font-semibold text-ink"
                onClick={manualSave}
                title={t(locale, "saveNowHint")}
                type="button"
              >
                <Save size={17} />
                {t(locale, "saveNow")}
              </button>
              <a
                className="inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700"
                href={`${API_BASE_URL}/api/v1/exports/matrix/${activePeriodId}.csv${groupQuery}`}
              >
                <Download size={17} />
                {t(locale, "matrixCsvExport")}
              </a>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-3 text-sm">
            {savingCells > 0 ? <p className="text-slate-600">{t(locale, "saving")}</p> : null}
            {message ? <p className="text-emerald-700">{message}</p> : null}
          </div>
        </Card>
      ) : (
        <div className="flex flex-wrap gap-3 text-sm">
          {editableMemberId != null ? (
            <button
              type="button"
              className={`inline-flex h-10 items-center justify-center gap-2 rounded-lg border px-4 text-sm font-semibold shadow-sm ${
                dayFeedbackAlwaysVisible && !readOnly
                  ? "border-mint bg-mint/20 text-ink ring-1 ring-mint/50 hover:bg-mint/30"
                  : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
              }`}
              disabled={readOnly}
              onClick={() => setIsMemberCommentModalOpen(true)}
            >
              <MessageSquareText size={16} />
              {t(locale, "monthlyComment")}
            </button>
          ) : null}
          {savingCells > 0 ? <p className="text-slate-600">{t(locale, "saving")}</p> : null}
          {message ? <p className="text-emerald-700">{message}</p> : null}
        </div>
      )}

      {matrix ? (
        <>
          {compact ? (
            <PlanningDenseMatrix
              matrix={matrix}
              cellMap={cellMap}
              onSave={saveCell}
              locale={locale}
              onOpenNote={setNoteMember}
              onSaveIntent={saveIntent}
              editableMemberId={editableMemberId}
              readOnly={readOnly}
              emphasizeStoredDayComments={emphasizeStoredDayComments}
              dayFeedbackAlwaysVisible={dayFeedbackAlwaysVisible}
              intentStatsByMember={intentStatsByMember}
              wishesResponseToggleEnabled={editableMemberId == null}
              wishesResponseReceived={(memberId) => notes.find((item) => item.team_member_id === memberId)?.wishes_response_received ?? false}
              onToggleWishesResponse={toggleWishesAcknowledged}
              hasMonthlyComment={(memberId) => Boolean(notes.find((item) => item.team_member_id === memberId)?.summary?.trim())}
            />
          ) : (
            <>
              <DesktopMatrix
                matrix={matrix}
                cellMap={cellMap}
                onSave={saveCell}
                locale={locale}
                onOpenNote={setNoteMember}
                onSaveIntent={saveIntent}
                editableMemberId={editableMemberId}
                readOnly={readOnly}
                emphasizeStoredDayComments={emphasizeStoredDayComments}
                dayFeedbackAlwaysVisible={dayFeedbackAlwaysVisible}
                intentStatsByMember={intentStatsByMember}
                wishesResponseToggleEnabled={editableMemberId == null}
                wishesResponseReceived={(memberId) => notes.find((item) => item.team_member_id === memberId)?.wishes_response_received ?? false}
                onToggleWishesResponse={toggleWishesAcknowledged}
                hasMonthlyComment={(memberId) => Boolean(notes.find((item) => item.team_member_id === memberId)?.summary?.trim())}
              />
              <MobileMatrix
                matrix={matrix}
                cellMap={cellMap}
                onSave={saveCell}
                locale={locale}
                onOpenNote={setNoteMember}
                onSaveIntent={saveIntent}
                editableMemberId={editableMemberId}
                readOnly={readOnly}
                emphasizeStoredDayComments={emphasizeStoredDayComments}
                dayFeedbackAlwaysVisible={dayFeedbackAlwaysVisible}
                intentStatsByMember={intentStatsByMember}
                hasMonthlyComment={(memberId) => Boolean(notes.find((item) => item.team_member_id === memberId)?.summary?.trim())}
              />
            </>
          )}
          <TeamMemberNoteModal
            member={noteMember}
            monthLabel={
              matrix
                ? formatPlanningMonthTitle(locale, matrix.planning_period.year, matrix.planning_period.month)
                : ""
            }
            preferencesDraft={preferencesDraft}
            summary={summary}
            onPreferencesDraftChange={setPreferencesDraft}
            onSummaryChange={setSummary}
            onClose={() => setNoteMember(null)}
            onSubmit={saveNote}
            locale={locale}
          />
          {editableMemberId != null && isMemberCommentModalOpen && matrix ? (
            <MonthlyCommentModal
              monthLabel={formatPlanningMonthTitle(locale, matrix.planning_period.year, matrix.planning_period.month)}
              value={summary}
              locale={locale}
              onClose={() => setIsMemberCommentModalOpen(false)}
              onChange={setSummary}
              onSubmit={async (event) => {
                event.preventDefault();
                await persistNote(editableMemberId, true);
                setIsMemberCommentModalOpen(false);
              }}
            />
          ) : null}
        </>
      ) : (
        <Card>
          <p className="text-sm text-slate-500">{t(locale, "noData")}</p>
        </Card>
      )}
    </div>
  );
}

function MonthlyCommentModal({
  monthLabel,
  value,
  onChange,
  onClose,
  onSubmit,
  locale
}: {
  monthLabel: string;
  value: string;
  onChange: (value: string) => void;
  onClose: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  locale: Locale;
}) {
  const title = t(locale, "monthPlanningNoteForMatrix", { month: monthLabel });
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 px-4 py-6 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="monthly-comment-title">
      <div className="w-full max-w-2xl rounded-xl bg-white p-5 shadow-soft ring-1 ring-slate-200">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 id="monthly-comment-title" className="text-lg font-semibold text-ink">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600"
            aria-label={t(locale, "close")}
          >
            <X size={17} />
          </button>
        </div>
        <form className="grid gap-4" onSubmit={onSubmit}>
          <Field label={title}>
            <textarea
              className="min-h-40 rounded-lg border border-slate-200 p-3 text-sm"
              value={value}
              onChange={(event) => onChange(event.target.value)}
            />
          </Field>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700"
            >
              {t(locale, "close")}
            </button>
            <button className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white" type="submit">
              <Save size={16} />
              {t(locale, "save")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function PlanningDenseMatrix({
  matrix,
  cellMap,
  onSave,
  onOpenNote,
  locale,
  onSaveIntent,
  editableMemberId,
  readOnly,
  emphasizeStoredDayComments,
  dayFeedbackAlwaysVisible,
  intentStatsByMember,
  wishesResponseToggleEnabled,
  wishesResponseReceived,
  onToggleWishesResponse,
  hasMonthlyComment,
}: {
  matrix: PlanningMatrix;
  cellMap: Map<string, PlanningCell>;
  onSave: (memberId: number, cellDate: string, status: string, comment?: string | null) => Promise<void>;
  onOpenNote: (member: MatrixTeamMember) => void;
  locale: Locale;
  onSaveIntent: SaveMatrixIntentFn;
  editableMemberId?: number;
  readOnly: boolean;
  emphasizeStoredDayComments: boolean;
  dayFeedbackAlwaysVisible: boolean;
  intentStatsByMember: Map<number, TeamMemberIntentStats>;
  wishesResponseToggleEnabled: boolean;
  wishesResponseReceived: (memberId: number) => boolean;
  onToggleWishesResponse: (memberId: number) => void | Promise<void>;
  hasMonthlyComment: (memberId: number) => boolean;
}) {
  const singleMemberColumn = matrix.team_members.length === 1;

  return (
    <div className={`${dataTableScrollShellClassName} rounded-lg border border-slate-200 bg-white shadow-soft`}>
      <table className={`${singleMemberColumn ? "min-w-full" : "min-w-max"} border-separate border-spacing-0 text-sm`}>
        <thead>
          <tr>
            <th className="sticky left-0 top-0 z-30 border-b border-r border-slate-200 bg-white p-2 text-left text-xs font-semibold text-slate-700">
              {t(locale, "date")}
            </th>
            {matrix.team_members.map((member) => (
              <th
                key={member.id}
                className={`sticky top-0 z-20 border-b border-slate-200 bg-white p-2 text-left align-bottom ${
                  singleMemberColumn ? "w-full" : "min-w-[10rem]"
                }`}
              >
                <div className={`flex items-start justify-between gap-1 ${singleMemberColumn ? "w-full" : "max-w-[12rem]"}`}>
                  <div className="min-w-0 flex-1">
                    <span className="block truncate text-xs font-semibold text-ink">{teamMemberLabel(member)}</span>
                    {(() => {
                      const stats = intentStatsByMember.get(member.id);
                      if (!stats || (!stats.wish && !stats.noGo)) {
                        return null;
                      }
                      return (
                        <div className="mt-1 flex flex-wrap gap-1">
                          <span className="rounded bg-sky-50 px-1.5 py-0.5 text-[0.6rem] font-semibold text-sky-900 ring-1 ring-sky-200">
                            {t(locale, "wishShort")}: {stats.wish}
                          </span>
                          <span className="rounded bg-rose-50 px-1.5 py-0.5 text-[0.6rem] font-semibold text-rose-900 ring-1 ring-rose-200">
                            {t(locale, "noGoShort")}: {stats.noGo}
                          </span>
                        </div>
                      );
                    })()}
                  </div>
                  <div className="flex shrink-0 items-start gap-0.5">
                    {wishesResponseToggleEnabled ? (
                      <button
                        type="button"
                        className={`inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border shadow-sm disabled:cursor-not-allowed disabled:opacity-40 ${
                          wishesResponseReceived(member.id)
                            ? "border-emerald-300 bg-emerald-50 text-emerald-800"
                            : "border-slate-200 bg-white text-slate-500 hover:bg-slate-50"
                        }`}
                        disabled={editableMemberId != null && member.id !== editableMemberId}
                        onClick={() => void onToggleWishesResponse(member.id)}
                        title={t(locale, "wishesResponseAcknowledgedHint")}
                        aria-label={t(locale, "wishesResponseAcknowledged")}
                        aria-pressed={wishesResponseReceived(member.id)}
                      >
                        <ListChecks aria-hidden size={14} />
                      </button>
                    ) : null}
                    <button
                      className={`inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border shadow-sm hover:bg-coral/10 disabled:cursor-not-allowed disabled:opacity-40 ${
                        hasMonthlyComment(member.id)
                          ? "border-amber-300 bg-amber-50 text-amber-800"
                          : "border-slate-200 bg-white text-coral"
                      }`}
                      disabled={readOnly || (editableMemberId != null && member.id !== editableMemberId)}
                      onClick={() => onOpenNote(member)}
                      title={t(locale, "teamMemberPeriodNotes")}
                      type="button"
                    >
                      <MessageSquareText aria-hidden size={14} />
                    </button>
                  </div>
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.days.map((day) => (
            <tr key={day.date}>
              <td className="sticky left-0 z-10 border-r border-slate-200 bg-white p-2 align-top text-xs font-medium text-slate-800">
                {formatDate(locale, day.date)}
              </td>
              {matrix.team_members.map((member) => (
                <td key={member.id} className="border-b border-slate-100 p-1.5 align-top">
                  <MatrixCell
                    dense
                    matrix={matrix}
                    cell={cellMap.get(`${day.date}:${member.id}`)}
                    memberId={member.id}
                    cellDate={day.date}
                    onSave={onSave}
                    locale={locale}
                    onSaveIntent={onSaveIntent}
                    readOnly={readOnly || (editableMemberId != null && member.id !== editableMemberId)}
                    emphasizeStoredDayComments={emphasizeStoredDayComments}
                    dayFeedbackAlwaysVisible={dayFeedbackAlwaysVisible}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DesktopMatrix({
  matrix,
  cellMap,
  onSave,
  onOpenNote,
  locale,
  onSaveIntent,
  editableMemberId,
  readOnly,
  emphasizeStoredDayComments,
  dayFeedbackAlwaysVisible,
  intentStatsByMember,
  wishesResponseToggleEnabled,
  wishesResponseReceived,
  onToggleWishesResponse,
  hasMonthlyComment,
}: {
  matrix: PlanningMatrix;
  cellMap: Map<string, PlanningCell>;
  onSave: (memberId: number, cellDate: string, status: string, comment?: string | null) => Promise<void>;
  onOpenNote: (member: MatrixTeamMember) => void;
  locale: Locale;
  onSaveIntent: SaveMatrixIntentFn;
  editableMemberId?: number;
  readOnly: boolean;
  emphasizeStoredDayComments: boolean;
  dayFeedbackAlwaysVisible: boolean;
  intentStatsByMember: Map<number, TeamMemberIntentStats>;
  wishesResponseToggleEnabled: boolean;
  wishesResponseReceived: (memberId: number) => boolean;
  onToggleWishesResponse: (memberId: number) => void | Promise<void>;
  hasMonthlyComment: (memberId: number) => boolean;
}) {
  const singleMemberColumn = matrix.team_members.length === 1;

  return (
    <div className={`hidden ${dataTableScrollShellClassName} rounded-lg border border-slate-200 bg-white shadow-soft lg:block`}>
      <table className="min-w-full border-separate border-spacing-0 text-sm">
        <thead>
          <tr>
            <th className="sticky left-0 top-0 z-20 border-b border-r border-slate-200 bg-white p-3 text-left font-semibold text-slate-700">
              {t(locale, "date")}
            </th>
            {matrix.team_members.map((member) => (
              <th
                key={member.id}
                className={`sticky top-0 z-10 border-b border-slate-200 bg-white p-3 text-left font-semibold text-slate-700 ${
                  singleMemberColumn ? "w-full" : "min-w-52"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <span className="block truncate">{teamMemberLabel(member)}</span>
                    {(() => {
                      const stats = intentStatsByMember.get(member.id);
                      if (!stats || (!stats.wish && !stats.noGo)) {
                        return null;
                      }
                      return (
                        <div className="mt-1 flex flex-wrap gap-1">
                          <span className="rounded bg-sky-50 px-1.5 py-0.5 text-[0.65rem] font-semibold text-sky-900 ring-1 ring-sky-200">
                            {t(locale, "wishShort")}: {stats.wish}
                          </span>
                          <span className="rounded bg-rose-50 px-1.5 py-0.5 text-[0.65rem] font-semibold text-rose-900 ring-1 ring-rose-200">
                            {t(locale, "noGoShort")}: {stats.noGo}
                          </span>
                        </div>
                      );
                    })()}
                  </div>
                  <div className="flex shrink-0 items-start gap-0.5">
                    {wishesResponseToggleEnabled ? (
                      <button
                        type="button"
                        className={`inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border shadow-sm disabled:cursor-not-allowed disabled:opacity-40 ${
                          wishesResponseReceived(member.id)
                            ? "border-emerald-300 bg-emerald-50 text-emerald-800"
                            : "border-slate-200 bg-white text-slate-500 hover:bg-slate-50"
                        }`}
                        disabled={editableMemberId != null && member.id !== editableMemberId}
                        onClick={() => void onToggleWishesResponse(member.id)}
                        title={t(locale, "wishesResponseAcknowledgedHint")}
                        aria-label={t(locale, "wishesResponseAcknowledged")}
                        aria-pressed={wishesResponseReceived(member.id)}
                      >
                        <ListChecks aria-hidden size={16} />
                      </button>
                    ) : null}
                    <button
                      className={`inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border shadow-sm hover:bg-coral/10 disabled:cursor-not-allowed disabled:opacity-40 ${
                        hasMonthlyComment(member.id)
                          ? "border-amber-300 bg-amber-50 text-amber-800"
                          : "border-slate-200 bg-white text-coral"
                      }`}
                      disabled={readOnly || (editableMemberId != null && member.id !== editableMemberId)}
                      onClick={() => onOpenNote(member)}
                      title={t(locale, "teamMemberPeriodNotes")}
                      type="button"
                    >
                      <MessageSquareText aria-hidden size={16} />
                    </button>
                  </div>
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.days.map((day) => (
            <tr key={day.date}>
              <td className="sticky left-0 z-10 border-r border-slate-200 bg-white p-3 font-medium text-slate-700">
                {formatDate(locale, day.date)}
              </td>
              {matrix.team_members.map((member) => {
                const cell = cellMap.get(`${day.date}:${member.id}`);
                return (
                  <td key={member.id} className="border-b border-slate-100 p-2 align-top">
                    <MatrixCell
                      matrix={matrix}
                      cell={cell}
                      memberId={member.id}
                      cellDate={day.date}
                      onSave={onSave}
                      locale={locale}
                      onSaveIntent={onSaveIntent}
                      readOnly={readOnly || (editableMemberId != null && member.id !== editableMemberId)}
                      emphasizeStoredDayComments={emphasizeStoredDayComments}
                      dayFeedbackAlwaysVisible={dayFeedbackAlwaysVisible}
                    />
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MobileMatrix({
  matrix,
  cellMap,
  onSave,
  onOpenNote,
  locale,
  onSaveIntent,
  editableMemberId,
  readOnly,
  emphasizeStoredDayComments,
  dayFeedbackAlwaysVisible,
  intentStatsByMember,
  hasMonthlyComment,
}: {
  matrix: PlanningMatrix;
  cellMap: Map<string, PlanningCell>;
  onSave: (memberId: number, cellDate: string, status: string, comment?: string | null) => Promise<void>;
  onOpenNote: (member: MatrixTeamMember) => void;
  locale: Locale;
  onSaveIntent: SaveMatrixIntentFn;
  editableMemberId?: number;
  readOnly: boolean;
  emphasizeStoredDayComments: boolean;
  dayFeedbackAlwaysVisible: boolean;
  intentStatsByMember: Map<number, TeamMemberIntentStats>;
  hasMonthlyComment: (memberId: number) => boolean;
}) {
  return (
    <div className="grid gap-4 lg:hidden">
      {matrix.days.map((day) => (
        <Card key={day.date}>
          <h2 className="mb-3 text-base font-semibold text-ink">{formatDate(locale, day.date)}</h2>
          <div className="grid gap-3">
            {matrix.team_members.map((member) => (
              <div key={member.id} className="grid gap-2 rounded-lg border border-slate-200 p-3">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold text-slate-700">{teamMemberLabel(member)}</p>
                    {(() => {
                      const stats = intentStatsByMember.get(member.id);
                      if (!stats || (!stats.wish && !stats.noGo)) {
                        return null;
                      }
                      return (
                        <div className="mt-1 flex flex-wrap gap-1">
                          <span className="rounded bg-sky-50 px-1.5 py-0.5 text-[0.65rem] font-semibold text-sky-900 ring-1 ring-sky-200">
                            {t(locale, "wishShort")}: {stats.wish}
                          </span>
                          <span className="rounded bg-rose-50 px-1.5 py-0.5 text-[0.65rem] font-semibold text-rose-900 ring-1 ring-rose-200">
                            {t(locale, "noGoShort")}: {stats.noGo}
                          </span>
                        </div>
                      );
                    })()}
                  </div>
                  <button
                    className={`inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border shadow-sm disabled:cursor-not-allowed disabled:opacity-40 ${
                      hasMonthlyComment(member.id)
                        ? "border-amber-300 bg-amber-50 text-amber-800"
                        : "border-slate-200 bg-white text-coral"
                    }`}
                    disabled={readOnly || (editableMemberId != null && member.id !== editableMemberId)}
                    onClick={() => onOpenNote(member)}
                    title={t(locale, "teamMemberPeriodNotes")}
                    type="button"
                  >
                    <MessageSquareText aria-hidden size={16} />
                  </button>
                </div>
                <MatrixCell
                  matrix={matrix}
                  cell={cellMap.get(`${day.date}:${member.id}`)}
                  memberId={member.id}
                  cellDate={day.date}
                  onSave={onSave}
                  locale={locale}
                  onSaveIntent={onSaveIntent}
                  readOnly={readOnly || (editableMemberId != null && member.id !== editableMemberId)}
                  emphasizeStoredDayComments={emphasizeStoredDayComments}
                  dayFeedbackAlwaysVisible={dayFeedbackAlwaysVisible}
                />
              </div>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}

function TeamMemberNoteModal({
  member,
  monthLabel,
  preferencesDraft,
  summary,
  onPreferencesDraftChange,
  onSummaryChange,
  onClose,
  onSubmit,
  locale
}: {
  member: MatrixTeamMember | null;
  monthLabel: string;
  preferencesDraft: string;
  summary: string;
  onPreferencesDraftChange: (value: string) => void;
  onSummaryChange: (value: string) => void;
  onClose: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  locale: Locale;
}) {
  if (!member) {
    return null;
  }

  const monthNoteLabel = monthLabel ? t(locale, "monthPlanningNoteForMatrix", { month: monthLabel }) : t(locale, "monthlyComment");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 px-4 py-6 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="member-note-title">
      <div className="max-h-[90vh] w-full max-w-3xl overflow-auto rounded-xl bg-white shadow-soft ring-1 ring-slate-200">
        <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div>
            <h2 id="member-note-title" className="text-lg font-semibold text-ink">{teamMemberLabel(member)}</h2>
            <p className="mt-1 text-sm text-slate-600">{t(locale, "teamMemberPeriodNotes")}</p>
          </div>
          <button
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 shadow-sm hover:bg-slate-50"
            onClick={onClose}
            title={t(locale, "close")}
            type="button"
          >
            <X aria-hidden size={17} />
          </button>
        </div>
        <form className="grid gap-4 p-5" onSubmit={onSubmit}>
          <div className="grid gap-1">
            <Field label={t(locale, "planningPreferencesField")}>
              <textarea
                className="min-h-48 rounded-lg border border-slate-200 p-3 text-sm"
                value={preferencesDraft}
                onChange={(event) => onPreferencesDraftChange(event.target.value)}
              />
            </Field>
            <p className="text-xs text-slate-500">{t(locale, "planningPreferencesMatrixHelp")}</p>
          </div>
          <Field label={monthNoteLabel}>
            <textarea
              className="min-h-28 rounded-lg border border-slate-200 p-3 text-sm"
              value={summary}
              onChange={(event) => onSummaryChange(event.target.value)}
            />
          </Field>
          <div className="flex flex-wrap justify-end gap-2">
            <button
              className="inline-flex h-11 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700"
              onClick={onClose}
              type="button"
            >
              {t(locale, "close")}
            </button>
            <button className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white">
              <Save size={17} />
              {t(locale, "save")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function MatrixCell({
  matrix,
  cell,
  memberId,
  cellDate,
  onSave,
  locale,
  dense = false,
  onSaveIntent,
  readOnly = false,
  emphasizeStoredDayComments = false,
  dayFeedbackAlwaysVisible = false
}: {
  matrix: PlanningMatrix;
  cell?: PlanningCell;
  memberId: number;
  cellDate: string;
  onSave: (memberId: number, cellDate: string, status: string, comment?: string | null) => Promise<void>;
  locale: Locale;
  dense?: boolean;
  onSaveIntent: SaveMatrixIntentFn;
  readOnly?: boolean;
  emphasizeStoredDayComments?: boolean;
  dayFeedbackAlwaysVisible?: boolean;
}) {
  const dayStatuses = activePlanningDayStatusDefinitions(matrix.day_status_definitions ?? []);
  const [status, setStatus] = useState(() => normalizePlanningStatus(cell?.status, dayStatuses));
  const [comment, setComment] = useState(cell?.comment ?? "");
  const [commentDraftOpen, setCommentDraftOpen] = useState(false);
  const meta = statusMeta(status, dayStatuses, locale);
  const [isDirty, setIsDirty] = useState(false);
  const hasComment = comment.trim().length > 0;
  const showCommentField =
    Boolean(dayFeedbackAlwaysVisible && !readOnly) || hasComment || commentDraftOpen;
  const storedDayComment = (cell?.comment ?? "").trim();
  const intentMap = useMemo(() => {
    const map = new Map<string, PlanningShiftIntentKind>();
    for (const row of matrix.shift_intents ?? []) {
      if (row.team_member_id !== memberId || row.cell_date !== cellDate) {
        continue;
      }
      map.set(`${cellDate}:${memberId}:${row.shift_template_id}:${row.shift_group_id}`, row.kind);
    }
    return map;
  }, [matrix.shift_intents, memberId, cellDate]);
  const intentRows = useMemo(() => intentTemplateRowsForDate(matrix, cellDate), [matrix, cellDate]);
  const intentOptions = useMemo(() => {
    const templateIdCounts = new Map<number, number>();
    for (const row of intentRows) {
      templateIdCounts.set(row.templateId, (templateIdCounts.get(row.templateId) ?? 0) + 1);
    }
    return intentRows.map(({ templateId, shiftGroupId }) => {
      const base = templateLabel(matrix, templateId, locale);
      const groupSuffix = (templateIdCounts.get(templateId) ?? 0) > 1 ? ` · #${shiftGroupId}` : "";
      const kind = intentMap.get(`${cellDate}:${memberId}:${templateId}:${shiftGroupId}`);
      const kindSuffix =
        kind === "wish"
          ? ` · ${t(locale, "wishShort")}`
          : kind === "no_go"
            ? ` · ${t(locale, "noGoShort")}`
            : "";
      return {
        key: `${templateId}-${shiftGroupId}`,
        templateId,
        shiftGroupId,
        label: `${base}${groupSuffix}${kindSuffix}`
      };
    });
  }, [cellDate, intentMap, intentRows, locale, matrix, memberId]);
  const [selectedIntentKey, setSelectedIntentKey] = useState("");
  const showIntents = Boolean(matrix.shift_templates?.length && intentOptions.length);
  const selectedIntent = intentOptions.find((row) => row.key === selectedIntentKey);
  const selectedIntentKind = selectedIntent
    ? intentMap.get(`${cellDate}:${memberId}:${selectedIntent.templateId}:${selectedIntent.shiftGroupId}`)
    : undefined;

  useEffect(() => {
    if (intentOptions.length === 0) {
      setSelectedIntentKey("");
      return;
    }
    if (!intentOptions.some((row) => row.key === selectedIntentKey)) {
      setSelectedIntentKey(intentOptions[0].key);
    }
  }, [intentOptions, selectedIntentKey]);

  useEffect(() => {
    setStatus(normalizePlanningStatus(cell?.status, dayStatuses));
    setComment(cell?.comment ?? "");
    setIsDirty(false);
    setCommentDraftOpen(false);
  }, [cell?.status, cell?.comment, dayStatuses]);

  useEffect(() => {
    if (readOnly || !isDirty) {
      return;
    }
    const timeout = window.setTimeout(() => {
      void onSave(memberId, cellDate, status, comment);
      setIsDirty(false);
    }, 650);
    return () => window.clearTimeout(timeout);
  }, [cellDate, comment, memberId, isDirty, onSave, readOnly, status]);

  return (
    <div className={`grid ${dense ? "gap-1" : "gap-2"} ${readOnly ? "opacity-80" : ""}`}>
      {emphasizeStoredDayComments && storedDayComment ? (
        <div
          className={`flex items-center gap-1 rounded-md border border-amber-200 bg-amber-50 font-semibold text-amber-950 ring-1 ring-amber-100 ${
            dense ? "px-1 py-0.5 text-[0.6rem]" : "px-1.5 py-0.5 text-[0.65rem]"
          }`}
          title={storedDayComment}
        >
          <MessageSquareText aria-hidden className="shrink-0" size={dense ? 12 : 14} />
          <span className="min-w-0 truncate">{t(locale, "wishesMatrixPlannerDayCommentCue")}</span>
        </div>
      ) : null}
      <select
        className={`min-w-0 rounded-lg border border-slate-200 bg-white font-medium ${dense ? "px-1.5 py-1.5 text-[0.7rem]" : "px-2 py-2 text-xs"}`}
        disabled={readOnly}
        value={status}
        onChange={(event) => {
          const nextStatus = event.target.value;
          setStatus(nextStatus);
          setIsDirty(false);
          void onSave(memberId, cellDate, nextStatus, comment);
        }}
      >
        <option value="">{t(locale, "emptyValue")}</option>
        {dayStatuses.map((item) => (
          <option key={item.code} value={item.code}>
            {planningDayStatusLabel(item, locale)}
          </option>
        ))}
      </select>
      {meta ? (
        <span
          className={`inline-flex w-fit rounded-full font-semibold ring-1 ${meta.color} ${dense ? "px-1.5 py-0.5 text-[0.65rem]" : "px-2 py-1 text-xs"}`}
        >
          {meta.label}
        </span>
      ) : null}
      {showCommentField ? (
        <>
          {dayFeedbackAlwaysVisible && !readOnly ? (
            <span className={`font-semibold text-slate-600 ${dense ? "text-[0.65rem]" : "text-xs"}`}>
              {t(locale, "wishesDayFeedbackFieldLabel")}
            </span>
          ) : null}
          <textarea
            className={`resize-y rounded-lg border border-slate-200 text-xs ${dense ? "min-h-12 p-1.5" : "min-h-16 p-2"}`}
            disabled={readOnly}
            placeholder={t(locale, "cellComment")}
            value={comment}
            onChange={(event) => {
              setComment(event.target.value);
              setIsDirty(true);
            }}
            onBlur={() => {
              if (!readOnly && isDirty) {
                void onSave(memberId, cellDate, status, comment);
                setIsDirty(false);
              }
              if (comment.trim() === "" && !dayFeedbackAlwaysVisible) {
                setCommentDraftOpen(false);
              }
            }}
          />
        </>
      ) : readOnly ? null : (
        <button
          type="button"
          className={`inline-flex w-fit items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600 shadow-sm hover:bg-slate-50 ${dense ? "h-7 w-7 p-0" : "h-9 w-9 p-0"}`}
          onClick={() => setCommentDraftOpen(true)}
          title={t(locale, "matrixCellCommentShow")}
          aria-label={t(locale, "matrixCellCommentShow")}
        >
          <MessageSquarePlus aria-hidden size={dense ? 14 : 16} />
        </button>
      )}
      {showIntents && selectedIntent ? (
        <div className={`grid ${dense ? "gap-1 pt-0.5" : "gap-1.5 pt-1"}`}>
          <select
            className={`min-w-0 rounded-lg border border-slate-200 bg-white font-medium ${dense ? "px-1.5 py-1.5 text-[0.7rem]" : "px-2 py-2 text-xs"}`}
            disabled={readOnly}
            value={selectedIntentKey}
            aria-label={t(locale, "shiftTemplate")}
            onChange={(event) => setSelectedIntentKey(event.target.value)}
          >
            {intentOptions.map((row) => (
              <option key={row.key} value={row.key}>
                {row.label}
              </option>
            ))}
          </select>
          <select
            className={`min-w-0 rounded-lg border border-slate-200 bg-white font-medium ${dense ? "px-1.5 py-1.5 text-[0.7rem]" : "px-2 py-2 text-xs"}`}
            disabled={readOnly}
            value={selectedIntentKind ?? ""}
            aria-label={t(locale, "matrixCellShiftIntent")}
            onChange={(event) => {
              const next = event.target.value;
              const kind: PlanningShiftIntentKind | null =
                next === "wish" || next === "no_go" ? next : null;
              void onSaveIntent(
                memberId,
                cellDate,
                selectedIntent.templateId,
                kind,
                selectedIntent.shiftGroupId
              );
            }}
          >
            <option value="">{t(locale, "emptyValue")}</option>
            <option value="wish">{t(locale, "wish")}</option>
            <option value="no_go">{t(locale, "noGo")}</option>
          </select>
        </div>
      ) : null}
    </div>
  );
}
