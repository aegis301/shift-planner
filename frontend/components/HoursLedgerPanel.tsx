"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale, useSession, type MeUser } from "@/components/LocaleProvider";
import { apiFetch } from "@/lib/api";
import { dataTableScrollShellClassName } from "@/lib/dataTableLayout";
import {
  formatLedgerMinutes,
  shouldShowDerived,
  snapshotNumber,
  type HoursLedger,
  type HoursLedgerEntry,
  type HoursLedgerEntryKind
} from "@/lib/hoursLedger";
import { isUserSession } from "@/lib/membershipRouting";
import { monthDateBounds } from "@/lib/planningDates";
import { t, type TranslationKey } from "@/lib/i18n";
import { teamMemberPlanningDisplayName } from "@/lib/teamMemberDisplay";

type HoursLedgerVariant = "member" | "planner";

type PlanningPeriod = {
  id: number;
  year: number;
  month: number;
};

type ShiftGroupOption = {
  id: number;
  code: string;
  name: string;
  team_member_ids?: number[];
};

type TeamMemberOption = {
  id: number;
  first_name: string;
  last_name: string;
  nickname: string | null;
};

type EditDraft = {
  statutory_minutes: string;
  credited_minutes: string;
  comment: string;
};

const KIND_KEYS: Record<HoursLedgerEntryKind, TranslationKey> = {
  work: "hoursKindWork",
  absence: "hoursKindAbsence",
  call_out: "hoursKindCallOut",
  in_duty_activity: "hoursKindInDuty"
};

const SOURCE_KEYS: Record<HoursLedgerEntry["source"], TranslationKey> = {
  roster: "hoursSourceRoster",
  day_status: "hoursSourceDayStatus",
  manual: "hoursSourceManual"
};

function monthLabel(period: PlanningPeriod, locale: string): string {
  return new Date(period.year, period.month - 1, 1).toLocaleDateString(locale === "de" ? "de-DE" : "en-GB", {
    month: "long",
    year: "numeric"
  });
}

export function HoursLedgerPanel({ variant }: { variant: HoursLedgerVariant }) {
  const { locale } = useLocale();
  const { me, loading } = useSession();
  const router = useRouter();
  const searchParams = useSearchParams();
  const portal = variant === "member";
  const [periods, setPeriods] = useState<PlanningPeriod[]>([]);
  const [periodId, setPeriodId] = useState(searchParams.get("period") ?? "");
  const [shiftGroups, setShiftGroups] = useState<ShiftGroupOption[]>([]);
  const [shiftGroupId, setShiftGroupId] = useState(searchParams.get("shiftGroup") ?? "");
  const [members, setMembers] = useState<TeamMemberOption[]>([]);
  const [memberId, setMemberId] = useState(searchParams.get("member") ?? "");
  const [ledger, setLedger] = useState<HoursLedger | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState<EditDraft>({ statutory_minutes: "", credited_minutes: "", comment: "" });
  const [manualDate, setManualDate] = useState("");
  const [manualKind, setManualKind] = useState<HoursLedgerEntryKind>("work");
  const [manualStatutory, setManualStatutory] = useState("0");
  const [manualCredited, setManualCredited] = useState("0");
  const [manualComment, setManualComment] = useState("");

  const userMe: MeUser | null = isUserSession(me) ? me : null;
  const plannerNeedsShiftGroup = Boolean(userMe && !userMe.capabilities.admin && variant === "planner");

  useEffect(() => {
    if (loading) {
      return;
    }
    if (!userMe) {
      router.replace("/login");
      return;
    }
    if (variant === "planner" && !userMe.capabilities.planning) {
      router.replace("/");
      return;
    }
    if (variant === "member" && !userMe.capabilities.team_member_portal) {
      router.replace("/");
    }
  }, [loading, router, userMe, variant]);

  useEffect(() => {
    void apiFetch<PlanningPeriod[]>("/api/v1/planning-periods")
      .then((rows) => {
        setPeriods(rows);
        setPeriodId((current) => current || (rows[0] ? String(rows[0].id) : ""));
      })
      .catch(() => setPeriods([]));
  }, []);

  useEffect(() => {
    if (!userMe || variant !== "planner") {
      return;
    }
    void apiFetch<ShiftGroupOption[]>("/api/v1/shift-groups?active_only=true")
      .then((groups) => {
        setShiftGroups(groups);
        setShiftGroupId((current) => {
          if (current) {
            return current;
          }
          if (!userMe.capabilities.admin && groups.length === 1) {
            return String(groups[0].id);
          }
          return current;
        });
      })
      .catch(() => setShiftGroups([]));
  }, [userMe, variant]);

  useEffect(() => {
    if (variant !== "planner") {
      return;
    }
    void apiFetch<TeamMemberOption[]>("/api/v1/team-members")
      .then(setMembers)
      .catch(() => setMembers([]));
  }, [variant]);

  const scopedMembers = useMemo(() => {
    if (!shiftGroupId) {
      return members;
    }
    const group = shiftGroups.find((row) => String(row.id) === shiftGroupId);
    const allowed = new Set(group?.team_member_ids ?? []);
    return members.filter((row) => allowed.has(row.id));
  }, [members, shiftGroupId, shiftGroups]);

  useEffect(() => {
    if (variant !== "planner" || scopedMembers.length === 0) {
      return;
    }
    if (!memberId || !scopedMembers.some((row) => String(row.id) === memberId)) {
      setMemberId(String(scopedMembers[0].id));
    }
  }, [memberId, scopedMembers, variant]);

  const activePeriod = periods.find((period) => String(period.id) === periodId);
  const bounds = useMemo(() => {
    const now = new Date();
    return activePeriod
      ? monthDateBounds(activePeriod.year, activePeriod.month)
      : monthDateBounds(now.getFullYear(), now.getMonth() + 1);
  }, [activePeriod]);

  const resolvedMemberId = variant === "member" ? userMe?.team_member_id ?? null : Number(memberId) || null;
  const canLoadPlanner = variant !== "planner" || Boolean(userMe?.capabilities.admin || shiftGroupId);

  const loadLedger = useCallback(async () => {
    if (!resolvedMemberId || !canLoadPlanner) {
      setLedger(null);
      return;
    }
    const params = new URLSearchParams({
      team_member_id: String(resolvedMemberId),
      start_date: bounds.min,
      end_date: bounds.max
    });
    if (portal) {
      params.set("team_member_portal", "true");
    }
    if (variant === "planner" && shiftGroupId) {
      params.set("shift_group_id", shiftGroupId);
    }
    if (variant === "planner") {
      params.set("include_reconciliation", "true");
    }
    setLoadError(false);
    try {
      const next = await apiFetch<HoursLedger>(`/api/v1/time-entries/ledger?${params.toString()}`);
      setLedger(next);
    } catch {
      setLedger(null);
      setLoadError(true);
    }
  }, [bounds.max, bounds.min, canLoadPlanner, portal, resolvedMemberId, shiftGroupId, variant]);

  useEffect(() => {
    void loadLedger();
  }, [loadLedger]);

  useEffect(() => {
    const next = new URLSearchParams();
    if (periodId) {
      next.set("period", periodId);
    }
    if (variant === "planner" && shiftGroupId) {
      next.set("shiftGroup", shiftGroupId);
    }
    if (variant === "planner" && memberId) {
      next.set("member", memberId);
    }
    const qs = next.toString();
    const path = variant === "member" ? "/my-hours" : "/hours";
    router.replace(qs ? `${path}?${qs}` : path, { scroll: false });
  }, [memberId, periodId, router, shiftGroupId, variant]);

  async function saveCorrection(entryId: number) {
    if (!resolvedMemberId) {
      return;
    }
    setBusy(true);
    try {
      const params = portal ? "?team_member_portal=true" : "";
      await apiFetch(`/api/v1/time-entries/${entryId}${params}`, {
        method: "PATCH",
        body: JSON.stringify({
          statutory_minutes: Number(draft.statutory_minutes),
          credited_minutes: Number(draft.credited_minutes),
          comment: draft.comment.trim() ? draft.comment.trim() : null
        })
      });
      setEditingId(null);
      await loadLedger();
    } catch {
      setLoadError(true);
    } finally {
      setBusy(false);
    }
  }

  async function addManual(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!resolvedMemberId || !manualDate) {
      return;
    }
    setBusy(true);
    try {
      const params = portal ? "?team_member_portal=true" : "";
      await apiFetch(`/api/v1/time-entries${params}`, {
        method: "POST",
        body: JSON.stringify({
          team_member_id: resolvedMemberId,
          entry_date: manualDate,
          kind: manualKind,
          duration_minutes: 0,
          statutory_minutes: Number(manualStatutory) || 0,
          credited_minutes: Number(manualCredited) || 0,
          comment: manualComment.trim() ? manualComment.trim() : null
        })
      });
      setManualComment("");
      await loadLedger();
    } catch {
      setLoadError(true);
    } finally {
      setBusy(false);
    }
  }

  function startEdit(entry: HoursLedgerEntry) {
    setEditingId(entry.id);
    setDraft({
      statutory_minutes: String(entry.statutory_minutes),
      credited_minutes: String(entry.credited_minutes),
      comment: entry.comment ?? ""
    });
  }

  function derivedHint(entry: HoursLedgerEntry, field: "statutory_minutes" | "credited_minutes", editing: boolean) {
    const derived = snapshotNumber(entry.derived_snapshot, field);
    if (derived == null) {
      return null;
    }
    if (!editing && !shouldShowDerived(entry, field)) {
      return null;
    }
    return (
      <p className="mt-1 text-xs text-slate-500">
        {t(locale, "hoursDerivedValue")}: {formatLedgerMinutes(derived)}
      </p>
    );
  }

  const divergences = (ledger?.reconciliation ?? []).filter((row) => row.diverges);
  const totals = ledger?.totals;

  return (
    <div className="grid gap-4">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">{t(locale, variant === "member" ? "myHoursNav" : "hoursNav")}</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-600">{t(locale, "hoursHelp")}</p>
        <p className="mt-1 max-w-3xl text-xs text-slate-500">{t(locale, "hoursStatutoryCreditedHelp")}</p>
      </div>
      <Card>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Field label={t(locale, "planningPeriod")}>
            <select className={inputClass} value={periodId} onChange={(event) => setPeriodId(event.target.value)}>
              {periods.length === 0 ? <option value="">{t(locale, "noPlanningPeriodSelected")}</option> : null}
              {periods.map((period) => (
                <option key={period.id} value={period.id}>
                  {monthLabel(period, locale)}
                </option>
              ))}
            </select>
          </Field>
          {variant === "planner" ? (
            <Field label={t(locale, "selectPlanningShiftGroup")}>
              <select className={inputClass} value={shiftGroupId} onChange={(event) => setShiftGroupId(event.target.value)}>
                {userMe?.capabilities.admin ? <option value="">{t(locale, "allShiftGroupsLabel")}</option> : null}
                {!userMe?.capabilities.admin ? <option value="">{t(locale, "planningPeriodStatusSelectGroup")}</option> : null}
                {shiftGroups.map((group) => (
                  <option key={group.id} value={group.id}>
                    {group.name}
                  </option>
                ))}
              </select>
            </Field>
          ) : null}
          {variant === "planner" ? (
            <Field label={t(locale, "hoursSelectMember")}>
              <select className={inputClass} value={memberId} onChange={(event) => setMemberId(event.target.value)} disabled={!canLoadPlanner}>
                {scopedMembers.map((member) => (
                  <option key={member.id} value={member.id}>
                    {teamMemberPlanningDisplayName(member)} ({member.first_name})
                  </option>
                ))}
              </select>
            </Field>
          ) : null}
        </div>
        {plannerNeedsShiftGroup && !shiftGroupId ? (
          <p className="mt-3 text-sm text-amber-800">{t(locale, "hoursPlannerShiftGroupRequired")}</p>
        ) : null}
      </Card>
      {loadError ? <p className="text-sm text-red-600">{t(locale, "apiUnavailable")}</p> : null}
      {totals ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <Card>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t(locale, "hoursOpeningBalance")}</p>
            <p className="mt-1 text-2xl font-semibold text-slate-900">{formatLedgerMinutes(totals.opening_overtime_minutes)}</p>
          </Card>
          <Card>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t(locale, "hoursContractTarget")}</p>
            <p className="mt-1 text-2xl font-semibold text-slate-900">{formatLedgerMinutes(totals.contract_target_minutes)}</p>
          </Card>
          <Card>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t(locale, "hoursStatutoryColumn")}</p>
            <p className="mt-1 text-2xl font-semibold text-slate-900">{formatLedgerMinutes(totals.statutory_minutes)}</p>
          </Card>
          <Card>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t(locale, "hoursCreditedColumn")}</p>
            <p className="mt-1 text-2xl font-semibold text-slate-900">{formatLedgerMinutes(totals.credited_minutes)}</p>
          </Card>
          <Card>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t(locale, "hoursRunningAccount")}</p>
            <p className="mt-1 text-2xl font-semibold text-slate-900">{formatLedgerMinutes(totals.running_overtime_minutes)}</p>
            <p className="mt-1 text-xs text-slate-500">{t(locale, "hoursRunningAccountHelp")}</p>
          </Card>
          <Card>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t(locale, "hoursAbsences")}</p>
            <p className="mt-1 text-2xl font-semibold text-slate-900">{totals.absence_count}</p>
            <p className="mt-1 text-xs text-slate-500">
              {t(locale, "hoursVacationConsumed")}: {totals.vacation_days_consumed}
              {totals.vacation_days_remaining != null
                ? ` · ${t(locale, "hoursVacationRemaining")}: ${totals.vacation_days_remaining}`
                : ""}
            </p>
          </Card>
        </div>
      ) : null}
      <Card>
        <div className={`${dataTableScrollShellClassName} rounded-lg border border-slate-200`}>
          <table className="w-full min-w-[720px] border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs font-semibold uppercase tracking-wide text-slate-500">
                <th className="sticky top-0 z-10 bg-white py-2 pr-3 shadow-[0_1px_0_0_rgb(226_232_240)]">{t(locale, "hoursEntryDate")}</th>
                <th className="sticky top-0 z-10 bg-white py-2 pr-3 shadow-[0_1px_0_0_rgb(226_232_240)]">{t(locale, "hoursKind")}</th>
                <th className="sticky top-0 z-10 bg-white py-2 pr-3 shadow-[0_1px_0_0_rgb(226_232_240)]">{t(locale, "hoursSource")}</th>
                <th className="sticky top-0 z-10 bg-white py-2 pr-3 shadow-[0_1px_0_0_rgb(226_232_240)]">{t(locale, "hoursStatutoryColumn")}</th>
                <th className="sticky top-0 z-10 bg-white py-2 pr-3 shadow-[0_1px_0_0_rgb(226_232_240)]">{t(locale, "hoursCreditedColumn")}</th>
                <th className="sticky top-0 z-10 bg-white py-2 pr-3 shadow-[0_1px_0_0_rgb(226_232_240)]">{t(locale, "hoursComment")}</th>
                <th className="sticky top-0 z-10 bg-white py-2 shadow-[0_1px_0_0_rgb(226_232_240)]" />
              </tr>
            </thead>
            <tbody>
              {(ledger?.entries ?? []).length === 0 ? (
                <tr>
                  <td className="py-4 text-slate-500" colSpan={7}>
                    {t(locale, "hoursNoEntries")}
                  </td>
                </tr>
              ) : (
                (ledger?.entries ?? []).map((entry) => {
                  const editing = editingId === entry.id;
                  return (
                    <tr key={entry.id} className="border-b border-slate-100 align-top last:border-0">
                      <td className="py-3 pr-3 font-medium text-slate-900">{entry.entry_date}</td>
                      <td className="py-3 pr-3">{t(locale, KIND_KEYS[entry.kind])}</td>
                      <td className="py-3 pr-3">{t(locale, SOURCE_KEYS[entry.source])}</td>
                      <td className="py-3 pr-3">
                        {editing ? (
                          <>
                            <input
                              className={`${inputClass} h-10 w-24`}
                              type="number"
                              min={0}
                              value={draft.statutory_minutes}
                              onChange={(event) => setDraft((current) => ({ ...current, statutory_minutes: event.target.value }))}
                            />
                            {derivedHint(entry, "statutory_minutes", editing)}
                          </>
                        ) : (
                          <>
                            <span>{formatLedgerMinutes(entry.statutory_minutes)}</span>
                            {derivedHint(entry, "statutory_minutes", editing)}
                          </>
                        )}
                      </td>
                      <td className="py-3 pr-3">
                        {editing ? (
                          <>
                            <input
                              className={`${inputClass} h-10 w-24`}
                              type="number"
                              min={0}
                              value={draft.credited_minutes}
                              onChange={(event) => setDraft((current) => ({ ...current, credited_minutes: event.target.value }))}
                            />
                            {derivedHint(entry, "credited_minutes", editing)}
                          </>
                        ) : (
                          <>
                            <span>{formatLedgerMinutes(entry.credited_minutes)}</span>
                            {derivedHint(entry, "credited_minutes", editing)}
                          </>
                        )}
                      </td>
                      <td className="py-3 pr-3">
                        {editing ? (
                          <input
                            className={`${inputClass} h-10 min-w-32`}
                            value={draft.comment}
                            onChange={(event) => setDraft((current) => ({ ...current, comment: event.target.value }))}
                          />
                        ) : (
                          entry.comment ?? ""
                        )}
                      </td>
                      <td className="py-3">
                        {editing ? (
                          <div className="flex flex-wrap gap-2">
                            <button
                              type="button"
                              className="inline-flex h-9 items-center rounded-lg bg-ink px-3 text-sm font-semibold text-white disabled:opacity-60"
                              disabled={busy}
                              onClick={() => void saveCorrection(entry.id)}
                            >
                              {t(locale, "save")}
                            </button>
                            <button
                              type="button"
                              className="inline-flex h-9 items-center rounded-lg border border-slate-200 px-3 text-sm"
                              onClick={() => setEditingId(null)}
                            >
                              {t(locale, "close")}
                            </button>
                          </div>
                        ) : (
                          <button
                            type="button"
                            className="inline-flex h-9 items-center rounded-lg border border-slate-200 px-3 text-sm"
                            onClick={() => startEdit(entry)}
                          >
                            {t(locale, "hoursEditEntry")}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </Card>
      {variant === "planner" ? (
        <Card>
          <h2 className="text-lg font-semibold text-slate-900">{t(locale, "hoursReconciliation")}</h2>
          {divergences.length === 0 ? (
            <p className="mt-2 text-sm text-slate-600">{t(locale, "hoursNoDivergence")}</p>
          ) : (
            <ul className="mt-3 grid gap-2 text-sm">
              {divergences.map((row) => (
                <li key={row.id} className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
                  {row.entry_date}: {t(locale, "hoursStatutoryColumn")} {formatLedgerMinutes(row.effective.statutory_minutes)}
                  {snapshotNumber(row.derived, "statutory_minutes") != null
                    ? ` (${t(locale, "hoursDerivedValue")} ${formatLedgerMinutes(snapshotNumber(row.derived, "statutory_minutes") ?? 0)})`
                    : ""}
                  {" · "}
                  {t(locale, "hoursCreditedColumn")} {formatLedgerMinutes(row.effective.credited_minutes)}
                  {snapshotNumber(row.derived, "credited_minutes") != null
                    ? ` (${t(locale, "hoursDerivedValue")} ${formatLedgerMinutes(snapshotNumber(row.derived, "credited_minutes") ?? 0)})`
                    : ""}
                </li>
              ))}
            </ul>
          )}
        </Card>
      ) : null}
      <Card>
        <h2 className="text-lg font-semibold text-slate-900">{t(locale, "hoursAddManual")}</h2>
        <form className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5" onSubmit={(event) => void addManual(event)}>
          <Field label={t(locale, "hoursEntryDate")}>
            <input className={inputClass} type="date" value={manualDate} onChange={(event) => setManualDate(event.target.value)} required />
          </Field>
          <Field label={t(locale, "hoursKind")}>
            <select className={inputClass} value={manualKind} onChange={(event) => setManualKind(event.target.value as HoursLedgerEntryKind)}>
              <option value="work">{t(locale, "hoursKindWork")}</option>
              <option value="absence">{t(locale, "hoursKindAbsence")}</option>
            </select>
          </Field>
          <Field label={t(locale, "hoursStatutoryColumn")}>
            <input className={inputClass} type="number" min={0} value={manualStatutory} onChange={(event) => setManualStatutory(event.target.value)} />
          </Field>
          <Field label={t(locale, "hoursCreditedColumn")}>
            <input className={inputClass} type="number" min={0} value={manualCredited} onChange={(event) => setManualCredited(event.target.value)} />
          </Field>
          <Field label={t(locale, "hoursComment")}>
            <input className={inputClass} value={manualComment} onChange={(event) => setManualComment(event.target.value)} />
          </Field>
          <button
            type="submit"
            className="inline-flex h-11 items-center justify-center rounded-lg bg-ink px-4 text-sm font-semibold text-white disabled:opacity-60 sm:col-span-2 lg:col-span-5"
            disabled={busy || !resolvedMemberId || !canLoadPlanner}
          >
            {t(locale, "hoursAddManual")}
          </button>
        </form>
      </Card>
    </div>
  );
}
