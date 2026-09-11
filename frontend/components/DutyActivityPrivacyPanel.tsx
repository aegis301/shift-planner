"use client";

import { FormEvent, useEffect, useState } from "react";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";
import { API_BASE_URL, ApiError, apiFetch } from "@/lib/api";
import { t } from "@/lib/i18n";

type ViewerRole = "admin" | "planner";

type DutyActivityAccessPolicy = {
  individual_read_roles: ViewerRole[];
  retention_months: number;
  purpose_statement: string;
  small_group_threshold: number;
};

type PlanningPeriod = {
  id: number;
  year: number;
  month: number;
};

export function DutyActivityPrivacyPanel() {
  const { locale } = useLocale();
  const [policy, setPolicy] = useState<DutyActivityAccessPolicy | null>(null);
  const [periods, setPeriods] = useState<PlanningPeriod[]>([]);
  const [periodId, setPeriodId] = useState("");
  const [allowAdmin, setAllowAdmin] = useState(false);
  const [allowPlanner, setAllowPlanner] = useState(false);
  const [retentionMonths, setRetentionMonths] = useState("24");
  const [threshold, setThreshold] = useState("5");
  const [purpose, setPurpose] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    void (async () => {
      const next = await apiFetch<DutyActivityAccessPolicy>("/api/v1/organization/duty-activity-access-policy");
      setPolicy(next);
      setAllowAdmin(next.individual_read_roles.includes("admin"));
      setAllowPlanner(next.individual_read_roles.includes("planner"));
      setRetentionMonths(String(next.retention_months));
      setThreshold(String(next.small_group_threshold));
      setPurpose(next.purpose_statement);
      const listed = await apiFetch<PlanningPeriod[]>("/api/v1/planning-periods");
      setPeriods(listed);
      if (listed.length > 0) {
        setPeriodId(String(listed[0].id));
      }
    })();
  }, []);

  async function save(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    const roles: ViewerRole[] = [];
    if (allowAdmin) {
      roles.push("admin");
    }
    if (allowPlanner) {
      roles.push("planner");
    }
    try {
      const next = await apiFetch<DutyActivityAccessPolicy>("/api/v1/organization/duty-activity-access-policy", {
        method: "PATCH",
        body: JSON.stringify({
          individual_read_roles: roles,
          retention_months: Number(retentionMonths),
          small_group_threshold: Number(threshold),
          purpose_statement: purpose
        })
      });
      setPolicy(next);
      setMessage(t(locale, "saved"));
    } catch (e) {
      if (e instanceof ApiError && typeof e.detail === "string") {
        setMessage(e.detail);
      } else {
        setMessage(t(locale, "dutyActivitySaveError"));
      }
    }
  }

  if (!policy) {
    return null;
  }

  return (
    <div className="space-y-4">
      <Card>
        <h2 className="text-lg font-semibold text-ink">{t(locale, "dutyActivityPrivacyTitle")}</h2>
        <p className="mt-1 text-sm text-slate-600">{t(locale, "dutyActivityPrivacyHelp")}</p>
        <form className="mt-4 space-y-4" onSubmit={save}>
          <fieldset>
            <legend className="text-sm font-medium text-slate-700">{t(locale, "dutyActivityIndividualReadRoles")}</legend>
            <label className="mt-2 flex items-center gap-2 text-sm">
              <input type="checkbox" checked={allowAdmin} onChange={(event) => setAllowAdmin(event.target.checked)} />
              {t(locale, "dutyActivityRoleAdmin")}
            </label>
            <label className="mt-2 flex items-center gap-2 text-sm">
              <input type="checkbox" checked={allowPlanner} onChange={(event) => setAllowPlanner(event.target.checked)} />
              {t(locale, "dutyActivityRolePlanner")}
            </label>
          </fieldset>
          <Field label={t(locale, "dutyActivityRetentionMonths")}>
            <input
              className={inputClass}
              type="number"
              min={1}
              max={120}
              value={retentionMonths}
              onChange={(event) => setRetentionMonths(event.target.value)}
              required
            />
          </Field>
          <Field label={t(locale, "dutyActivitySmallGroupThreshold")}>
            <input
              className={inputClass}
              type="number"
              min={2}
              max={100}
              value={threshold}
              onChange={(event) => setThreshold(event.target.value)}
              required
            />
          </Field>
          <Field label={t(locale, "dutyActivityPurposeStatement")}>
            <textarea
              className={`${inputClass} min-h-32`}
              value={purpose}
              onChange={(event) => setPurpose(event.target.value)}
              rows={6}
            />
          </Field>
          <button
            type="submit"
            className="inline-flex h-11 items-center justify-center rounded-lg bg-ink px-4 text-sm font-semibold text-white"
          >
            {t(locale, "save")}
          </button>
          {message ? <p className="text-sm text-emerald-700">{message}</p> : null}
        </form>
      </Card>
      <Card>
        <h2 className="text-lg font-semibold text-ink">{t(locale, "dutyActivityWorksCouncilExport")}</h2>
        <p className="mt-1 text-sm text-slate-600">{t(locale, "dutyActivityWorksCouncilHelp")}</p>
        <Field label={t(locale, "planningPeriod")}>
          <select className={inputClass} value={periodId} onChange={(event) => setPeriodId(event.target.value)}>
            {periods.map((period) => (
              <option key={period.id} value={period.id}>
                {period.year}-{String(period.month).padStart(2, "0")}
              </option>
            ))}
          </select>
        </Field>
        {periodId ? (
          <div className="mt-3 flex flex-wrap gap-3">
            <a
              className="inline-flex h-11 items-center justify-center rounded-lg bg-ink px-4 text-sm font-semibold text-white"
              href={`${API_BASE_URL}/api/v1/exports/duty-activity/works-council/${periodId}.xlsx`}
            >
              {t(locale, "dutyActivityExportXlsx")}
            </a>
            <a
              className="inline-flex h-11 items-center justify-center rounded-lg border border-slate-300 px-4 text-sm font-semibold"
              href={`${API_BASE_URL}/api/v1/exports/duty-activity/works-council/${periodId}.pdf`}
            >
              {t(locale, "dutyActivityExportPdf")}
            </a>
          </div>
        ) : null}
      </Card>
    </div>
  );
}
