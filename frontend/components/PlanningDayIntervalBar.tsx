"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, CalendarRange, Save, X } from "lucide-react";
import { Field, inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";
import { apiFetch } from "@/lib/api";
import { t } from "@/lib/i18n";
import { expandInclusiveDateRange } from "@/lib/planningDates";
import {
  activePlanningDayStatusDefinitions,
  planningDayStatusLabel,
  planningDayStatusSelectClass,
  planningDayStatusSelectShellClass,
  type PlanningDayStatusDefinition
} from "@/lib/planningDayStatus";
import { teamMemberPlanningDisplayName } from "@/lib/teamMemberDisplay";

type MatrixTeamMember = {
  id: number;
  first_name: string;
  last_name: string;
  nickname?: string | null;
};

type MatrixDay = {
  date: string;
};

type PlanningCell = {
  team_member_id: number;
  cell_date: string;
  status: string;
  comment: string | null;
};

type PlanningMatrixMeta = {
  planning_period: { year: number; month: number };
  team_members: MatrixTeamMember[];
  days: MatrixDay[];
  cells: PlanningCell[];
};

type PendingApply = {
  cells: Array<{
    team_member_id: number;
    cell_date: string;
    status: string;
    comment: string | null;
  }>;
  overwriteCount: number;
};

export function PlanningDayIntervalBar({
  periodId,
  shiftGroupId,
  readOnly,
  teamMemberPortal,
  editableMemberId,
  dayStatusDefinitions,
  onApplied
}: {
  periodId: string;
  shiftGroupId: string;
  readOnly: boolean;
  teamMemberPortal: boolean;
  editableMemberId?: number;
  dayStatusDefinitions: PlanningDayStatusDefinition[];
  onApplied: () => void | Promise<void>;
}) {
  const { locale } = useLocale();
  const [matrixMeta, setMatrixMeta] = useState<PlanningMatrixMeta | null>(null);
  const [memberId, setMemberId] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [status, setStatus] = useState("");
  const [comment, setComment] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [pendingApply, setPendingApply] = useState<PendingApply | null>(null);

  const statusOptions = useMemo(
    () => activePlanningDayStatusDefinitions(dayStatusDefinitions),
    [dayStatusDefinitions]
  );

  const groupQuery = useMemo(() => {
    const params = new URLSearchParams();
    params.set("shift_group_id", shiftGroupId);
    if (teamMemberPortal) {
      params.set("team_member_portal", "true");
    }
    return `?${params.toString()}`;
  }, [shiftGroupId, teamMemberPortal]);

  const monthBounds = useMemo(() => {
    if (!matrixMeta?.days.length) {
      return null;
    }
    return {
      min: matrixMeta.days[0].date,
      max: matrixMeta.days[matrixMeta.days.length - 1].date
    };
  }, [matrixMeta]);

  const cellMap = useMemo(() => {
    const map = new Map<string, PlanningCell>();
    for (const cell of matrixMeta?.cells ?? []) {
      map.set(`${cell.team_member_id}:${cell.cell_date}`, cell);
    }
    return map;
  }, [matrixMeta]);

  const effectiveMemberId = teamMemberPortal && editableMemberId != null ? String(editableMemberId) : memberId;

  const loadMatrixMeta = useCallback(async () => {
    if (!periodId || !shiftGroupId) {
      setMatrixMeta(null);
      return;
    }
    try {
      const data = await apiFetch<PlanningMatrixMeta>(`/api/v1/matrix/${periodId}${groupQuery}`);
      setMatrixMeta(data);
    } catch {
      setMatrixMeta(null);
    }
  }, [groupQuery, periodId, shiftGroupId]);

  useEffect(() => {
    void loadMatrixMeta();
  }, [loadMatrixMeta]);

  useEffect(() => {
    if (teamMemberPortal && editableMemberId != null) {
      setMemberId(String(editableMemberId));
    }
  }, [editableMemberId, teamMemberPortal]);

  useEffect(() => {
    if (!monthBounds) {
      return;
    }
    if (!fromDate || fromDate < monthBounds.min || fromDate > monthBounds.max) {
      setFromDate(monthBounds.min);
    }
    if (!toDate || toDate < monthBounds.min || toDate > monthBounds.max) {
      setToDate(monthBounds.min);
    }
  }, [fromDate, monthBounds, toDate]);

  function buildApplyPayload(): PendingApply | null {
    setError("");
    if (!effectiveMemberId) {
      setError(t(locale, "planningDayIntervalSelectMember"));
      return null;
    }
    if (!status) {
      setError(t(locale, "planningDayIntervalSelectStatus"));
      return null;
    }
    if (!fromDate || !toDate || fromDate > toDate) {
      setError(t(locale, "planningDayIntervalInvalidRange"));
      return null;
    }
    if (monthBounds && (fromDate < monthBounds.min || toDate > monthBounds.max)) {
      setError(t(locale, "planningDayIntervalInvalidRange"));
      return null;
    }

    const dates = expandInclusiveDateRange(fromDate, toDate);
    if (!dates.length) {
      setError(t(locale, "planningDayIntervalInvalidRange"));
      return null;
    }

    const trimmedComment = comment.trim();
    const memberNumericId = Number(effectiveMemberId);
    let overwriteCount = 0;
    const cells = dates.map((cellDate) => {
      const existing = cellMap.get(`${memberNumericId}:${cellDate}`);
      if (existing?.status && existing.status !== status) {
        overwriteCount += 1;
      }
      return {
        team_member_id: memberNumericId,
        cell_date: cellDate,
        status,
        comment: trimmedComment ? trimmedComment : (existing?.comment ?? null)
      };
    });

    return { cells, overwriteCount };
  }

  async function submitApply(payload: PendingApply) {
    setSaving(true);
    setError("");
    try {
      await apiFetch(`/api/v1/matrix/${periodId}/cells/bulk${groupQuery}`, {
        method: "PUT",
        body: JSON.stringify({ cells: payload.cells })
      });
      setMessage(t(locale, "saved"));
      setPendingApply(null);
      await loadMatrixMeta();
      await onApplied();
    } catch {
      setError(t(locale, "planningDayIntervalApplyFailed"));
    } finally {
      setSaving(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (readOnly || saving) {
      return;
    }
    const payload = buildApplyPayload();
    if (!payload) {
      return;
    }
    if (payload.overwriteCount > 0) {
      setPendingApply(payload);
      return;
    }
    void submitApply(payload);
  }

  if (!periodId || !shiftGroupId || readOnly) {
    return null;
  }

  const selectedMember = matrixMeta?.team_members.find((member) => String(member.id) === effectiveMemberId);

  return (
    <>
      <div className="border-t border-slate-100 pt-3">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <CalendarRange className="text-slate-500" size={16} aria-hidden />
          <p className="text-xs font-medium text-slate-700">{t(locale, "planningDayIntervalTitle")}</p>
        </div>
        <p className="mb-3 text-xs text-slate-600">{t(locale, "planningDayIntervalHelp")}</p>
        <form className="flex flex-wrap items-end gap-2" onSubmit={handleSubmit}>
          {teamMemberPortal ? (
            <Field label={t(locale, "planningDayIntervalMember")}>
              <input
                className={`${inputClass} min-w-40 bg-slate-50`}
                readOnly
                type="text"
                value={selectedMember ? teamMemberPlanningDisplayName(selectedMember) : ""}
              />
            </Field>
          ) : (
            <Field label={t(locale, "planningDayIntervalMember")}>
              <select
                className={`${inputClass} min-w-44`}
                disabled={saving}
                onChange={(event) => setMemberId(event.target.value)}
                value={memberId}
              >
                <option value="">{t(locale, "emptyValue")}</option>
                {(matrixMeta?.team_members ?? []).map((member) => (
                  <option key={member.id} value={member.id}>
                    {teamMemberPlanningDisplayName(member)}
                  </option>
                ))}
              </select>
            </Field>
          )}
          <Field label={t(locale, "planningDayIntervalFrom")}>
            <input
              className={`${inputClass} min-w-36`}
              disabled={saving || !monthBounds}
              max={monthBounds?.max}
              min={monthBounds?.min}
              onChange={(event) => setFromDate(event.target.value)}
              type="date"
              value={fromDate}
            />
          </Field>
          <Field label={t(locale, "planningDayIntervalTo")}>
            <input
              className={`${inputClass} min-w-36`}
              disabled={saving || !monthBounds}
              max={monthBounds?.max}
              min={monthBounds?.min}
              onChange={(event) => setToDate(event.target.value)}
              type="date"
              value={toDate}
            />
          </Field>
          <Field label={t(locale, "planningDayIntervalStatus")}>
            <select
              className={`${planningDayStatusSelectShellClass} min-w-40 ${planningDayStatusSelectClass(status, dayStatusDefinitions)}`}
              disabled={saving}
              onChange={(event) => setStatus(event.target.value)}
              value={status}
            >
              <option value="">{t(locale, "emptyValue")}</option>
              {statusOptions.map((item) => (
                <option key={item.code} value={item.code}>
                  {planningDayStatusLabel(item, locale)}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t(locale, "planningDayIntervalComment")}>
            <input
              className={`${inputClass} min-w-48`}
              disabled={saving}
              onChange={(event) => setComment(event.target.value)}
              placeholder={t(locale, "emptyValue")}
              type="text"
              value={comment}
            />
          </Field>
          <button
            className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-mint px-4 text-sm font-semibold text-ink disabled:cursor-not-allowed disabled:opacity-40"
            disabled={saving || !matrixMeta}
            type="submit"
          >
            <Save size={16} />
            {saving ? t(locale, "saving") : t(locale, "planningDayIntervalApply")}
          </button>
        </form>
        {error ? <p className="mt-2 text-xs text-rose-700">{error}</p> : null}
        {message ? <p className="mt-2 text-xs text-emerald-700">{message}</p> : null}
      </div>

      {pendingApply ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 px-4 py-6 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-labelledby="day-interval-overwrite-title"
        >
          <div className="w-full max-w-md rounded-xl bg-white p-5 shadow-soft ring-1 ring-amber-200">
            <div className="mb-4 flex items-start justify-between gap-3">
              <div className="flex gap-3">
                <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-amber-50 text-amber-700 ring-1 ring-amber-200">
                  <AlertTriangle size={19} />
                </span>
                <div>
                  <h2 id="day-interval-overwrite-title" className="text-lg font-semibold text-ink">
                    {t(locale, "planningDayIntervalOverwriteTitle")}
                  </h2>
                  <p className="mt-1 text-sm text-slate-600">
                    {t(locale, "planningDayIntervalOverwriteBody", {
                      count: String(pendingApply.overwriteCount)
                    })}
                  </p>
                </div>
              </div>
              <button
                aria-label={t(locale, "close")}
                className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600"
                onClick={() => setPendingApply(null)}
                type="button"
              >
                <X size={17} />
              </button>
            </div>
            <div className="mt-5 flex flex-wrap justify-end gap-2">
              <button
                className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700"
                onClick={() => setPendingApply(null)}
                type="button"
              >
                {t(locale, "close")}
              </button>
              <button
                className="inline-flex h-10 items-center justify-center rounded-lg bg-mint px-4 text-sm font-semibold text-ink disabled:opacity-40"
                disabled={saving}
                onClick={() => void submitApply(pendingApply)}
                type="button"
              >
                {saving ? t(locale, "saving") : t(locale, "confirm")}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
