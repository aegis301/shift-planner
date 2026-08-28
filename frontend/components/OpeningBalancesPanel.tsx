"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";
import { ApiError, apiFetch } from "@/lib/api";
import { t } from "@/lib/i18n";
import type { TimeAccountOpening } from "@/lib/hours";
import { isTeamMemberRecord, type TeamMemberRecord } from "@/components/ResourceForms";

export function OpeningBalancesPanel() {
  const { locale } = useLocale();
  const [members, setMembers] = useState<TeamMemberRecord[]>([]);
  const [openings, setOpenings] = useState<TimeAccountOpening[]>([]);
  const [selectedId, setSelectedId] = useState<number | "">("");
  const [asOf, setAsOf] = useState("");
  const [overtime, setOvertime] = useState("0");
  const [vacation, setVacation] = useState("0");
  const [sick, setSick] = useState("0");
  const [message, setMessage] = useState("");

  async function reload() {
    const [memberRows, openingRows] = await Promise.all([
      apiFetch<TeamMemberRecord[]>("/api/v1/team-members?active_only=true"),
      apiFetch<TimeAccountOpening[]>("/api/v1/hours/openings")
    ]);
    setMembers(memberRows.filter(isTeamMemberRecord));
    setOpenings(openingRows);
  }

  useEffect(() => {
    void reload().catch(() => undefined);
  }, []);

  const openingByMember = useMemo(() => {
    const map = new Map<number, TimeAccountOpening>();
    for (const row of openings) {
      map.set(row.team_member_id, row);
    }
    return map;
  }, [openings]);

  useEffect(() => {
    if (selectedId === "") {
      return;
    }
    const row = openingByMember.get(selectedId);
    if (row) {
      setAsOf(row.as_of_date);
      setOvertime(String(row.overtime_minutes));
      setVacation(String(row.vacation_days_remaining));
      setSick(String(row.sick_days_used_ytd));
    } else {
      setAsOf(new Date().toISOString().slice(0, 10));
      setOvertime("0");
      setVacation("0");
      setSick("0");
    }
  }, [openingByMember, selectedId]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (selectedId === "") {
      return;
    }
    setMessage("");
    try {
      await apiFetch(`/api/v1/hours/members/${selectedId}/opening`, {
        method: "PUT",
        body: JSON.stringify({
          as_of_date: asOf,
          overtime_minutes: Number(overtime),
          vacation_days_remaining: Number(vacation),
          sick_days_used_ytd: Number(sick)
        })
      });
      await reload();
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : t(locale, "apiRequestFailed", { status: "" }));
    }
  }

  return (
    <div className="grid gap-4">
      <div>
        <h1 className="text-xl font-semibold text-ink">{t(locale, "hoursOpeningsTitle")}</h1>
        <p className="mt-1 max-w-2xl text-sm text-slate-600">{t(locale, "hoursOpeningsHelp")}</p>
      </div>
      <Card>
        <form className="grid gap-4 sm:grid-cols-2" onSubmit={save}>
          <Field label={t(locale, "teamMembers")}>
            <select
              className={inputClass}
              value={selectedId}
              onChange={(e) => setSelectedId(e.target.value ? Number(e.target.value) : "")}
            >
              <option value="">{t(locale, "selectTeamMemberToLink")}</option>
              {members.map((member) => (
                <option key={member.id} value={member.id}>
                  {member.last_name}, {member.first_name}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t(locale, "hoursAsOf")}>
            <input className={inputClass} type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} required />
          </Field>
          <Field label={t(locale, "hoursOvertimeMinutes")}>
            <input className={inputClass} type="number" value={overtime} onChange={(e) => setOvertime(e.target.value)} />
          </Field>
          <Field label={t(locale, "hoursVacationRemaining")}>
            <input className={inputClass} type="number" step={0.5} value={vacation} onChange={(e) => setVacation(e.target.value)} />
          </Field>
          <Field label={t(locale, "hoursSickYtd")}>
            <input className={inputClass} type="number" step={0.5} value={sick} onChange={(e) => setSick(e.target.value)} />
          </Field>
          <div className="flex items-end">
            <button className="h-11 rounded-lg bg-ink px-4 text-sm font-semibold text-white" type="submit">
              {t(locale, "hoursSaveOpening")}
            </button>
          </div>
        </form>
        {message ? <p className="mt-3 text-sm text-rose-700">{message}</p> : null}
      </Card>
      <Card>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="text-left text-slate-600">
              <tr>
                <th className="p-2">{t(locale, "name")}</th>
                <th className="p-2">{t(locale, "hoursAsOf")}</th>
                <th className="p-2 text-right">{t(locale, "hoursOvertime")}</th>
                <th className="p-2 text-right">{t(locale, "hoursVacationRemaining")}</th>
              </tr>
            </thead>
            <tbody>
              {openings.map((row) => {
                const member = members.find((item) => item.id === row.team_member_id);
                return (
                  <tr key={row.id} className="border-t border-slate-100">
                    <td className="p-2">{member ? `${member.last_name}, ${member.first_name}` : row.team_member_id}</td>
                    <td className="p-2 tabular-nums">{row.as_of_date}</td>
                    <td className="p-2 text-right tabular-nums">{row.overtime_minutes}</td>
                    <td className="p-2 text-right tabular-nums">{row.vacation_days_remaining}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
