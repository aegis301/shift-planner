"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale, useSession } from "@/components/LocaleProvider";
import { isUserSession } from "@/lib/membershipRouting";
import { ApiError, apiFetch } from "@/lib/api";
import { t, type Locale } from "@/lib/i18n";
import { dataTableScrollShellClassName } from "@/lib/dataTableLayout";
import {
  fetchHoursSummaries,
  fetchTimesheet,
  formatHoursFromMinutes,
  timesheetCsvHref,
  type Timesheet,
  type TimesheetDay,
  type TimesheetSummary
} from "@/lib/hours";

function currentYearMonth(): { year: number; month: number } {
  const now = new Date();
  return { year: now.getFullYear(), month: now.getMonth() + 1 };
}

function sourceLabel(locale: Locale, source: string): string {
  if (source === "roster_fill") {
    return t(locale, "hoursSourceRoster");
  }
  if (source === "regular_hours") {
    return t(locale, "hoursSourceRegular");
  }
  return t(locale, "hoursSourceManual");
}

export function HoursWorkspace({
  variant
}: {
  variant: "planner" | "team_member";
}) {
  const { locale } = useLocale();
  const { me } = useSession();
  const initial = currentYearMonth();
  const [year, setYear] = useState(initial.year);
  const [month, setMonth] = useState(initial.month);
  const [summaries, setSummaries] = useState<TimesheetSummary[]>([]);
  const [memberId, setMemberId] = useState<number | null>(
    variant === "team_member" && isUserSession(me) ? me.team_member_id : null
  );
  const [sheet, setSheet] = useState<Timesheet | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [startTime, setStartTime] = useState("08:00");
  const [endTime, setEndTime] = useState("16:00");
  const [absenceCode, setAbsenceCode] = useState("urlaub");
  const editable = variant === "planner";

  useEffect(() => {
    if (variant === "team_member" && isUserSession(me) && me.team_member_id) {
      setMemberId(me.team_member_id);
    }
  }, [me, variant]);

  async function reloadList() {
    if (variant === "team_member") {
      return;
    }
    const rows = await fetchHoursSummaries(year, month);
    setSummaries(rows);
  }

  async function reloadSheet(id: number) {
    const data = await fetchTimesheet(id, year, month);
    setSheet(data);
    setSelectedDate((prev) => prev ?? data.days[0]?.date ?? null);
  }

  useEffect(() => {
    if (variant === "planner") {
      void reloadList().catch(() => setSummaries([]));
    }
  }, [year, month, variant]);

  useEffect(() => {
    if (memberId != null) {
      void reloadSheet(memberId).catch(() => setSheet(null));
    }
  }, [memberId, year, month]);

  const selectedDay: TimesheetDay | undefined = useMemo(
    () => sheet?.days.find((day) => day.date === selectedDate),
    [sheet, selectedDate]
  );

  async function fill(kind: "roster" | "regular") {
    if (memberId == null || !sheet) {
      return;
    }
    setMessage("");
    const path =
      kind === "roster"
        ? `/api/v1/hours/members/${memberId}/fill-from-roster`
        : `/api/v1/hours/members/${memberId}/fill-regular-week`;
    try {
      const result = await apiFetch<{ created: number }>(path, {
        method: "POST",
        body: JSON.stringify({ from_date: sheet.from_date, to_date: sheet.to_date })
      });
      setMessage(t(locale, "hoursFillOk", { count: String(result.created) }));
      await reloadSheet(memberId);
      await reloadList();
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : t(locale, "apiRequestFailed", { status: "" }));
    }
  }

  async function addWork(event: FormEvent) {
    event.preventDefault();
    if (memberId == null || !selectedDate) {
      return;
    }
    setMessage("");
    try {
      await apiFetch(`/api/v1/hours/members/${memberId}/entries`, {
        method: "POST",
        body: JSON.stringify({
          entry_date: selectedDate,
          kind: "work",
          started_at: `${selectedDate}T${startTime}:00`,
          ended_at: `${selectedDate}T${endTime}:00`
        })
      });
      await reloadSheet(memberId);
      await reloadList();
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : t(locale, "apiRequestFailed", { status: "" }));
    }
  }

  async function addAbsence(event: FormEvent) {
    event.preventDefault();
    if (memberId == null || !selectedDate) {
      return;
    }
    setMessage("");
    try {
      await apiFetch(`/api/v1/hours/members/${memberId}/entries`, {
        method: "POST",
        body: JSON.stringify({
          entry_date: selectedDate,
          kind: "absence",
          all_day: true,
          planning_day_status_code: absenceCode
        })
      });
      await reloadSheet(memberId);
      await reloadList();
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : t(locale, "apiRequestFailed", { status: "" }));
    }
  }

  async function removeEntry(id: number) {
    setMessage("");
    try {
      await apiFetch(`/api/v1/hours/entries/${id}`, { method: "DELETE" });
      if (memberId != null) {
        await reloadSheet(memberId);
        await reloadList();
      }
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : t(locale, "apiRequestFailed", { status: "" }));
    }
  }

  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-ink">
            {variant === "team_member" ? t(locale, "myHoursNav") : t(locale, "hoursTitle")}
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-600">{t(locale, "hoursHelp")}</p>
        </div>
        <Field label={t(locale, "hoursMonth")}>
          <input
            className={inputClass}
            type="month"
            value={`${year}-${String(month).padStart(2, "0")}`}
            onChange={(e) => {
              const [nextYear, nextMonth] = e.target.value.split("-").map(Number);
              setYear(nextYear);
              setMonth(nextMonth);
            }}
          />
        </Field>
      </div>
      {message ? <p className="text-sm text-emerald-800">{message}</p> : null}
      {variant === "planner" && memberId == null ? (
        <Card>
          {summaries.length ? (
            <div className={`${dataTableScrollShellClassName} rounded-lg border border-slate-200`}>
              <table className="min-w-full text-sm">
                <thead className="text-left text-slate-600">
                  <tr>
                    <th className="p-3">{t(locale, "name")}</th>
                    <th className="p-3 text-right">{t(locale, "hoursWorked")}</th>
                    <th className="p-3 text-right">{t(locale, "hoursExpected")}</th>
                    <th className="p-3 text-right">{t(locale, "hoursExtra")}</th>
                    <th className="p-3 text-right">{t(locale, "hoursOvertime")}</th>
                    <th className="p-3 text-right">{t(locale, "hoursVacationRemaining")}</th>
                    <th className="p-3" />
                  </tr>
                </thead>
                <tbody>
                  {summaries.map((row) => (
                    <tr key={row.team_member_id} className="border-t border-slate-100">
                      <td className="p-3 font-medium text-ink">{row.name}</td>
                      <td className="p-3 text-right tabular-nums">{formatHoursFromMinutes(row.worked_contract_minutes)}</td>
                      <td className="p-3 text-right tabular-nums">{formatHoursFromMinutes(row.expected_minutes)}</td>
                      <td className="p-3 text-right tabular-nums">{formatHoursFromMinutes(row.worked_extra_minutes)}</td>
                      <td className="p-3 text-right tabular-nums">{formatHoursFromMinutes(row.overtime_minutes)}</td>
                      <td className="p-3 text-right tabular-nums">{row.vacation_days_remaining}</td>
                      <td className="p-3 text-right">
                        <button
                          className="text-sm font-semibold text-emerald-800 underline"
                          type="button"
                          onClick={() => setMemberId(row.team_member_id)}
                        >
                          {t(locale, "hoursOpenTimesheet")}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-slate-600">{t(locale, "hoursEmpty")}</p>
          )}
        </Card>
      ) : null}
      {sheet && memberId != null ? (
        <div className="grid gap-4">
          {variant === "planner" ? (
            <button
              type="button"
              className="inline-flex items-center gap-2 text-sm font-semibold text-slate-700"
              onClick={() => {
                setMemberId(null);
                setSheet(null);
              }}
            >
              <ArrowLeft size={16} />
              {t(locale, "hoursBackToList")}
            </button>
          ) : null}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Card>
              <p className="text-xs uppercase tracking-wide text-slate-500">{t(locale, "hoursWorked")}</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums text-ink">
                {formatHoursFromMinutes(sheet.worked_contract_minutes)}
              </p>
            </Card>
            <Card>
              <p className="text-xs uppercase tracking-wide text-slate-500">{t(locale, "hoursExpected")}</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums text-ink">
                {formatHoursFromMinutes(sheet.expected_minutes)}
              </p>
            </Card>
            <Card>
              <p className="text-xs uppercase tracking-wide text-slate-500">{t(locale, "hoursOvertime")}</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums text-ink">
                {formatHoursFromMinutes(sheet.overtime_minutes)}
              </p>
            </Card>
            <Card>
              <p className="text-xs uppercase tracking-wide text-slate-500">{t(locale, "hoursVacationRemaining")}</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums text-ink">{sheet.vacation_days_remaining}</p>
            </Card>
          </div>
          <div className="flex flex-wrap gap-2">
            {editable ? (
              <>
                <button
                  type="button"
                  className="h-10 rounded-lg bg-ink px-3 text-sm font-semibold text-white"
                  onClick={() => void fill("roster")}
                >
                  {t(locale, "hoursFillRoster")}
                </button>
                <button
                  type="button"
                  className="h-10 rounded-lg border border-slate-200 px-3 text-sm font-semibold"
                  onClick={() => void fill("regular")}
                >
                  {t(locale, "hoursFillRegular")}
                </button>
              </>
            ) : null}
            <a
              className="inline-flex h-10 items-center rounded-lg border border-slate-200 px-3 text-sm font-semibold"
              href={timesheetCsvHref(memberId, year, month)}
            >
              {t(locale, "hoursCsv")}
            </a>
          </div>
          <div className="flex gap-1 overflow-x-auto pb-1">
            {sheet.days.map((day) => {
              const active = day.date === selectedDate;
              const hasPlanGap = day.roster_plan_minutes !== day.worked_contract_minutes + day.worked_extra_minutes;
              return (
                <button
                  key={day.date}
                  type="button"
                  onClick={() => setSelectedDate(day.date)}
                  className={`min-w-14 rounded-lg px-2 py-2 text-xs ${
                    active ? "bg-ink text-white" : "bg-slate-100 text-slate-800"
                  } ${hasPlanGap && day.roster_plan_minutes > 0 ? "ring-1 ring-amber-400" : ""}`}
                >
                  <div className="tabular-nums">{day.date.slice(8)}</div>
                  <div className="tabular-nums">{formatHoursFromMinutes(day.worked_contract_minutes)}</div>
                </button>
              );
            })}
          </div>
          {selectedDay ? (
            <div className="grid gap-4 lg:grid-cols-2">
              <Card>
                <h2 className="text-base font-semibold text-ink">
                  {t(locale, "hoursSelectedDay")} · {selectedDay.date}
                </h2>
                <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
                  <dt className="text-slate-600">{t(locale, "hoursExpected")}</dt>
                  <dd className="text-right tabular-nums">{formatHoursFromMinutes(selectedDay.expected_minutes)}</dd>
                  <dt className="text-slate-600">{t(locale, "hoursActual")}</dt>
                  <dd className="text-right tabular-nums">
                    {formatHoursFromMinutes(selectedDay.worked_contract_minutes + selectedDay.worked_extra_minutes)}
                  </dd>
                  <dt className="text-slate-600">{t(locale, "hoursPlan")}</dt>
                  <dd className="text-right tabular-nums">{formatHoursFromMinutes(selectedDay.roster_plan_minutes)}</dd>
                  <dt className="text-slate-600">{t(locale, "hoursDelta")}</dt>
                  <dd className="text-right tabular-nums">{formatHoursFromMinutes(selectedDay.delta_minutes)}</dd>
                </dl>
                <ul className="mt-4 grid gap-2">
                  {selectedDay.roster_plan.map((plan, index) => (
                    <li key={`plan-${index}`} className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600">
                      {t(locale, "hoursPlan")}: {formatHoursFromMinutes(plan.duration_minutes)}
                      {plan.category ? ` · ${plan.category}` : ""}
                    </li>
                  ))}
                  {selectedDay.entries.length === 0 ? (
                    <li className="text-sm text-slate-500">{t(locale, "hoursNoEntries")}</li>
                  ) : (
                    selectedDay.entries.map((entry) => (
                      <li key={entry.id} className="flex items-center justify-between rounded-lg bg-emerald-50 px-3 py-2 text-sm">
                        <span>
                          {entry.kind === "absence" ? t(locale, "hoursKindAbsence") : t(locale, "hoursKindWork")} ·{" "}
                          {formatHoursFromMinutes(entry.duration_minutes)} · {sourceLabel(locale, entry.source)}
                          {entry.started_at && entry.ended_at
                            ? ` · ${entry.started_at.slice(11, 16)}–${entry.ended_at.slice(11, 16)}`
                            : ""}
                        </span>
                        {editable ? (
                          <button type="button" className="text-rose-700" onClick={() => void removeEntry(entry.id)}>
                            {t(locale, "hoursDeleteEntry")}
                          </button>
                        ) : null}
                      </li>
                    ))
                  )}
                </ul>
              </Card>
              {editable ? (
                <Card>
                  <form className="grid gap-3" onSubmit={addWork}>
                    <p className="text-sm font-semibold">{t(locale, "hoursAddEntry")}</p>
                    <div className="grid grid-cols-2 gap-2">
                      <Field label={t(locale, "start")}>
                        <input className={inputClass} type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} />
                      </Field>
                      <Field label={t(locale, "end")}>
                        <input className={inputClass} type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} />
                      </Field>
                    </div>
                    <button className="h-10 rounded-lg bg-ink text-sm font-semibold text-white" type="submit">
                      {t(locale, "hoursAddEntry")}
                    </button>
                  </form>
                  <form className="mt-6 grid gap-3" onSubmit={addAbsence}>
                    <p className="text-sm font-semibold">{t(locale, "hoursAddAbsence")}</p>
                    <Field label={t(locale, "hoursKindAbsence")}>
                      <input className={inputClass} value={absenceCode} onChange={(e) => setAbsenceCode(e.target.value)} />
                    </Field>
                    <button className="h-10 rounded-lg border border-slate-200 text-sm font-semibold" type="submit">
                      {t(locale, "hoursAddAbsence")}
                    </button>
                  </form>
                </Card>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
