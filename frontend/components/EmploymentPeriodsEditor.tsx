"use client";

import { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Field, inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";
import { ApiError, apiFetch } from "@/lib/api";
import { t } from "@/lib/i18n";
import type { EmploymentPeriod, WorkerGroup } from "@/lib/hours";
import { fetchWorkerGroups } from "@/lib/hours";

type DraftPeriod = {
  worker_group_id: number;
  employment_percentage: number;
  start_date: string;
  end_date: string;
};

export function EmploymentPeriodsEditor({ teamMemberId }: { teamMemberId: number }) {
  const { locale } = useLocale();
  const [groups, setGroups] = useState<WorkerGroup[]>([]);
  const [periods, setPeriods] = useState<DraftPeriod[]>([]);
  const [message, setMessage] = useState("");

  useEffect(() => {
    void Promise.all([
      fetchWorkerGroups(true),
      apiFetch<EmploymentPeriod[]>(`/api/v1/hours/members/${teamMemberId}/employment-periods`)
    ])
      .then(([groupRows, periodRows]) => {
        setGroups(groupRows);
        setPeriods(
          periodRows.map((row) => ({
            worker_group_id: row.worker_group_id,
            employment_percentage: row.employment_percentage,
            start_date: row.start_date,
            end_date: row.end_date ?? ""
          }))
        );
      })
      .catch(() => undefined);
  }, [teamMemberId]);

  async function save() {
    setMessage("");
    try {
      const saved = await apiFetch<EmploymentPeriod[]>(`/api/v1/hours/members/${teamMemberId}/employment-periods`, {
        method: "PUT",
        body: JSON.stringify({
          periods: periods.map((row) => ({
            worker_group_id: row.worker_group_id,
            employment_percentage: row.employment_percentage,
            start_date: row.start_date,
            end_date: row.end_date ? row.end_date : null
          }))
        })
      });
      setPeriods(
        saved.map((row) => ({
          worker_group_id: row.worker_group_id,
          employment_percentage: row.employment_percentage,
          start_date: row.start_date,
          end_date: row.end_date ?? ""
        }))
      );
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : t(locale, "apiRequestFailed", { status: "" }));
    }
  }

  return (
    <div className="mt-4 rounded-lg border border-slate-200 p-3">
      <p className="text-sm font-semibold text-ink">{t(locale, "hoursEmploymentPeriods")}</p>
      <p className="mt-1 text-xs text-slate-600">{t(locale, "hoursEmploymentPeriodsHelp")}</p>
      {groups.length === 0 ? (
        <p className="mt-2 text-sm text-amber-800">{t(locale, "hoursNoWorkerGroups")}</p>
      ) : (
        <div className="mt-3 grid gap-2">
          {periods.map((row, index) => (
            <div key={index} className="grid gap-2 rounded-lg bg-slate-50 p-2 sm:grid-cols-2">
              <Field label={t(locale, "hoursWorkerGroup")}>
                <select
                  className={inputClass}
                  value={row.worker_group_id}
                  onChange={(e) => {
                    const next = [...periods];
                    next[index] = { ...row, worker_group_id: Number(e.target.value) };
                    setPeriods(next);
                  }}
                >
                  {groups.map((group) => (
                    <option key={group.id} value={group.id}>
                      {group.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={t(locale, "employment")}>
                <input
                  className={inputClass}
                  type="number"
                  min={1}
                  max={100}
                  value={row.employment_percentage}
                  onChange={(e) => {
                    const next = [...periods];
                    next[index] = { ...row, employment_percentage: Number(e.target.value) };
                    setPeriods(next);
                  }}
                />
              </Field>
              <Field label={t(locale, "start")}>
                <input
                  className={inputClass}
                  type="date"
                  value={row.start_date}
                  onChange={(e) => {
                    const next = [...periods];
                    next[index] = { ...row, start_date: e.target.value };
                    setPeriods(next);
                  }}
                />
              </Field>
              <Field label={t(locale, "end")}>
                <div className="flex gap-2">
                  <input
                    className={inputClass}
                    type="date"
                    value={row.end_date}
                    onChange={(e) => {
                      const next = [...periods];
                      next[index] = { ...row, end_date: e.target.value };
                      setPeriods(next);
                    }}
                  />
                  <button
                    type="button"
                    className="inline-flex h-11 w-11 items-center justify-center rounded-lg border border-rose-200 text-rose-700"
                    onClick={() => setPeriods(periods.filter((_, i) => i !== index))}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </Field>
            </div>
          ))}
          <button
            type="button"
            className="inline-flex h-10 items-center gap-2 self-start rounded-lg border border-slate-200 px-3 text-sm font-semibold"
            onClick={() =>
              setPeriods([
                ...periods,
                {
                  worker_group_id: groups[0].id,
                  employment_percentage: 100,
                  start_date: new Date().toISOString().slice(0, 10),
                  end_date: ""
                }
              ])
            }
          >
            <Plus size={16} />
            {t(locale, "hoursAddPeriod")}
          </button>
          <button type="button" className="h-10 self-start rounded-lg bg-ink px-4 text-sm font-semibold text-white" onClick={() => void save()}>
            {t(locale, "save")}
          </button>
        </div>
      )}
      {message ? <p className="mt-2 text-sm text-rose-700">{message}</p> : null}
    </div>
  );
}
