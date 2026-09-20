"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Field, inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";
import { ApiError, apiFetch } from "@/lib/api";
import { t } from "@/lib/i18n";
import type { ContractGroup } from "@/components/ContractGroupsPanel";

type EmploymentPeriod = {
  id: number;
  contract_group_id: number;
  employment_percentage: number;
  start_date: string;
  end_date: string | null;
};

type Opening = {
  as_of_date: string;
  overtime_minutes: number;
  vacation_days_remaining: number | string;
  sick_days_used_ytd: number | string;
};

type DraftPeriod = {
  contract_group_id: string;
  employment_percentage: string;
  start_date: string;
  end_date: string;
};

export function EmploymentContractSection({ teamMemberId }: { teamMemberId: number }) {
  const { locale } = useLocale();
  const [groups, setGroups] = useState<ContractGroup[]>([]);
  const [periods, setPeriods] = useState<DraftPeriod[]>([]);
  const [opening, setOpening] = useState<Opening>({
    as_of_date: "2000-01-01",
    overtime_minutes: 0,
    vacation_days_remaining: 0,
    sick_days_used_ytd: 0
  });
  const [message, setMessage] = useState("");

  const reload = useCallback(async () => {
    const [groupRows, periodRows, openingRow] = await Promise.all([
      apiFetch<ContractGroup[]>("/api/v1/contract-groups"),
      apiFetch<EmploymentPeriod[]>(`/api/v1/team-members/${teamMemberId}/employment-periods`),
      apiFetch<Opening | null>(`/api/v1/team-members/${teamMemberId}/time-account-opening`)
    ]);
    setGroups(groupRows);
    setPeriods(
      periodRows.map((row) => ({
        contract_group_id: String(row.contract_group_id),
        employment_percentage: String(row.employment_percentage),
        start_date: row.start_date,
        end_date: row.end_date ?? ""
      }))
    );
    if (openingRow) {
      setOpening({
        as_of_date: openingRow.as_of_date,
        overtime_minutes: openingRow.overtime_minutes,
        vacation_days_remaining: openingRow.vacation_days_remaining,
        sick_days_used_ytd: openingRow.sick_days_used_ytd
      });
    }
  }, [teamMemberId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function savePeriods(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    try {
      await apiFetch(`/api/v1/team-members/${teamMemberId}/employment-periods`, {
        method: "PUT",
        body: JSON.stringify({
          periods: periods.map((row) => ({
            contract_group_id: Number(row.contract_group_id),
            employment_percentage: Number(row.employment_percentage),
            start_date: row.start_date,
            end_date: row.end_date.trim() ? row.end_date : null
          }))
        })
      });
      await reload();
      setMessage(t(locale, "saved"));
    } catch (e) {
      if (e instanceof ApiError && typeof e.detail === "string") {
        setMessage(e.detail);
      } else {
        setMessage(t(locale, "contractGroupSaveError"));
      }
    }
  }

  async function saveOpening(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    try {
      await apiFetch(`/api/v1/team-members/${teamMemberId}/time-account-opening`, {
        method: "PUT",
        body: JSON.stringify({
          as_of_date: opening.as_of_date,
          overtime_minutes: Number(opening.overtime_minutes),
          vacation_days_remaining: Number(opening.vacation_days_remaining),
          sick_days_used_ytd: Number(opening.sick_days_used_ytd)
        })
      });
      await reload();
      setMessage(t(locale, "saved"));
    } catch (e) {
      if (e instanceof ApiError && typeof e.detail === "string") {
        setMessage(e.detail);
      } else {
        setMessage(t(locale, "contractGroupSaveError"));
      }
    }
  }

  return (
    <div className="grid gap-5">
      <section className="rounded-lg border border-slate-200 p-4">
        <h3 className="text-sm font-semibold text-slate-800">{t(locale, "employmentPeriodsTitle")}</h3>
        <p className="mt-1 text-xs text-slate-500">{t(locale, "employmentPeriodsHelp")}</p>
        <form className="mt-3 grid gap-3" onSubmit={(event) => void savePeriods(event)}>
          {periods.map((row, index) => (
            <div key={index} className="grid gap-2 rounded-lg bg-slate-50 p-3 md:grid-cols-4">
              <Field label={t(locale, "contractGroupsNav")}>
                <select
                  className={inputClass}
                  value={row.contract_group_id}
                  onChange={(event) =>
                    setPeriods((prev) =>
                      prev.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, contract_group_id: event.target.value } : item
                      )
                    )
                  }
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
                  onChange={(event) =>
                    setPeriods((prev) =>
                      prev.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, employment_percentage: event.target.value } : item
                      )
                    )
                  }
                />
              </Field>
              <Field label={t(locale, "employmentStart")}>
                <input
                  className={inputClass}
                  type="date"
                  value={row.start_date}
                  onChange={(event) =>
                    setPeriods((prev) =>
                      prev.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, start_date: event.target.value } : item
                      )
                    )
                  }
                />
              </Field>
              <Field label={t(locale, "employmentEnd")}>
                <input
                  className={inputClass}
                  type="date"
                  value={row.end_date}
                  onChange={(event) =>
                    setPeriods((prev) =>
                      prev.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, end_date: event.target.value } : item
                      )
                    )
                  }
                />
              </Field>
            </div>
          ))}
          <div className="flex gap-2">
            <button
              type="button"
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
              onClick={() =>
                setPeriods((prev) => [
                  ...prev,
                  {
                    contract_group_id: String(groups[0]?.id ?? ""),
                    employment_percentage: "100",
                    start_date: new Date().toISOString().slice(0, 10),
                    end_date: ""
                  }
                ])
              }
            >
              {t(locale, "employmentPeriodAdd")}
            </button>
            <button type="submit" className="rounded-lg bg-ink px-3 py-2 text-sm font-semibold text-white">
              {t(locale, "save")}
            </button>
          </div>
        </form>
      </section>
      <section className="rounded-lg border border-slate-200 p-4">
        <h3 className="text-sm font-semibold text-slate-800">{t(locale, "timeAccountOpeningTitle")}</h3>
        <form className="mt-3 grid gap-3 md:grid-cols-2" onSubmit={(event) => void saveOpening(event)}>
          <Field label={t(locale, "timeAccountAsOf")}>
            <input
              className={inputClass}
              type="date"
              value={opening.as_of_date}
              onChange={(event) => setOpening((prev) => ({ ...prev, as_of_date: event.target.value }))}
            />
          </Field>
          <Field label={t(locale, "timeAccountOvertimeMinutes")}>
            <input
              className={inputClass}
              type="number"
              value={opening.overtime_minutes}
              onChange={(event) => setOpening((prev) => ({ ...prev, overtime_minutes: Number(event.target.value) }))}
            />
          </Field>
          <Field label={t(locale, "timeAccountVacationRemaining")}>
            <input
              className={inputClass}
              type="number"
              step="0.5"
              value={opening.vacation_days_remaining}
              onChange={(event) => setOpening((prev) => ({ ...prev, vacation_days_remaining: event.target.value }))}
            />
          </Field>
          <Field label={t(locale, "timeAccountSickYtd")}>
            <input
              className={inputClass}
              type="number"
              step="0.5"
              value={opening.sick_days_used_ytd}
              onChange={(event) => setOpening((prev) => ({ ...prev, sick_days_used_ytd: event.target.value }))}
            />
          </Field>
          <div>
            <button type="submit" className="rounded-lg bg-ink px-3 py-2 text-sm font-semibold text-white">
              {t(locale, "save")}
            </button>
          </div>
        </form>
      </section>
      {message ? <p className="text-sm text-emerald-700">{message}</p> : null}
    </div>
  );
}
