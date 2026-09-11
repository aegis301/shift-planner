"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";
import { API_BASE_URL, apiFetch } from "@/lib/api";
import { dataTableScrollShellClassName } from "@/lib/dataTableLayout";
import { t } from "@/lib/i18n";

type ComplianceFinding = {
  code: string;
  severity: string;
  message: string;
  team_member_id: number | null;
  date: string | null;
};

type ComplianceRestViolation = {
  code: string;
  compensation_pending: boolean;
  rest_minutes: number | null;
  date: string | null;
};

type ComplianceMember = {
  team_member_id: number;
  display_name: string;
  statutory_minutes: number;
  credited_minutes: number;
  weekly_average_minutes: number;
  weekly_cap_minutes: number;
  weekly_cap_source: "base" | "opt_out";
  weekly_cap_tier: string | null;
  weekly_cap_consent_id: number | null;
  consecutive_work_days: number;
  consecutive_work_days_limit: number | null;
  duty_count: number;
  duty_count_allowed: number | null;
  duty_count_period: string | null;
  documentation_days_above_threshold: number;
  documentation_days_recorded: number;
  rest_violations: ComplianceRestViolation[];
  findings: ComplianceFinding[];
};

type ComplianceReport = {
  planning_period_id: number;
  year: number;
  month: number;
  generated_at: string;
  rule_set: { id: number; name: string; version: number } | null;
  members: ComplianceMember[];
  findings: ComplianceFinding[];
};

function minutesLabel(value: number): string {
  return `${value.toLocaleString()} min`;
}

export function ComplianceReportPanel({
  periodId,
  shiftGroupId,
}: {
  periodId: string;
  shiftGroupId: string;
}) {
  const { locale } = useLocale();
  const [report, setReport] = useState<ComplianceReport | null>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!periodId) {
      setReport(null);
      return;
    }
    const query = shiftGroupId ? `?shift_group_id=${encodeURIComponent(shiftGroupId)}` : "";
    void apiFetch<ComplianceReport>(`/api/v1/compliance-report/${periodId}${query}`)
      .then((next) => {
        setReport(next);
        setMessage("");
      })
      .catch(() => {
        setReport(null);
        setMessage(t(locale, "complianceReportLoadError"));
      });
  }, [locale, periodId, shiftGroupId]);

  const exportQuery = shiftGroupId ? `?shift_group_id=${encodeURIComponent(shiftGroupId)}` : "";

  return (
    <Card>
      <div className="grid gap-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-ink">{t(locale, "complianceReportTitle")}</h2>
            <p className="mt-1 text-sm text-slate-600">{t(locale, "complianceReportHelp")}</p>
          </div>
          {periodId ? (
            <div className="flex flex-wrap gap-2">
              <a
                className="inline-flex h-10 items-center rounded-lg bg-ink px-3 text-sm font-semibold text-white"
                href={`${API_BASE_URL}/api/v1/exports/compliance-report/${periodId}.xlsx${exportQuery}`}
              >
                {t(locale, "complianceReportExportXlsx")}
              </a>
              <a
                className="inline-flex h-10 items-center rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-800"
                href={`${API_BASE_URL}/api/v1/exports/compliance-report/${periodId}.pdf${exportQuery}`}
              >
                {t(locale, "complianceReportExportPdf")}
              </a>
            </div>
          ) : null}
        </div>
        {report?.rule_set ? (
          <p className="text-sm font-medium text-ink">
            {t(locale, "complianceReportRuleSet", {
              name: report.rule_set.name,
              version: String(report.rule_set.version),
            })}
          </p>
        ) : report ? (
          <p className="text-sm text-slate-500">{t(locale, "complianceReportNoRuleSet")}</p>
        ) : null}
        {message ? <p className="text-sm text-rose-700">{message}</p> : null}
        {report && report.members.length === 0 ? (
          <p className="text-sm text-slate-500">{t(locale, "noData")}</p>
        ) : null}
        {report && report.members.length > 0 ? (
          <div className={`${dataTableScrollShellClassName} rounded-lg border border-slate-200`}>
            <table className="min-w-full text-sm">
              <thead className="text-left text-slate-600">
                <tr className="border-b border-slate-200">
                  <th className="px-3 py-2 font-semibold">{t(locale, "teamMembers")}</th>
                  <th className="px-3 py-2 font-semibold">{t(locale, "complianceReportStatutory")}</th>
                  <th className="px-3 py-2 font-semibold">{t(locale, "complianceReportCredit")}</th>
                  <th className="px-3 py-2 font-semibold">{t(locale, "complianceReportWeeklyAverage")}</th>
                  <th className="px-3 py-2 font-semibold">{t(locale, "complianceReportConsecutive")}</th>
                  <th className="px-3 py-2 font-semibold">{t(locale, "complianceReportDuties")}</th>
                  <th className="px-3 py-2 font-semibold">{t(locale, "complianceReportDocumentation")}</th>
                  <th className="px-3 py-2 font-semibold">{t(locale, "complianceReportRest")}</th>
                </tr>
              </thead>
              <tbody>
                {report.members.map((member) => (
                  <tr key={member.team_member_id} className="border-b border-slate-100">
                    <td className="px-3 py-2 font-medium text-ink">{member.display_name}</td>
                    <td className="px-3 py-2">{minutesLabel(member.statutory_minutes)}</td>
                    <td className="px-3 py-2">{minutesLabel(member.credited_minutes)}</td>
                    <td className="px-3 py-2">
                      {minutesLabel(member.weekly_average_minutes)}
                      {" / "}
                      {minutesLabel(member.weekly_cap_minutes)}
                      {" · "}
                      {member.weekly_cap_source === "opt_out"
                        ? t(locale, "complianceReportCapOptOut")
                        : t(locale, "complianceReportCapBase")}
                      {member.weekly_cap_tier ? ` (${member.weekly_cap_tier})` : ""}
                    </td>
                    <td className="px-3 py-2">
                      {member.consecutive_work_days}
                      {member.consecutive_work_days_limit != null
                        ? ` / ${member.consecutive_work_days_limit}`
                        : ""}
                    </td>
                    <td className="px-3 py-2">
                      {member.duty_count}
                      {member.duty_count_allowed != null ? ` / ${member.duty_count_allowed}` : ""}
                    </td>
                    <td className="px-3 py-2">
                      {member.documentation_days_recorded} / {member.documentation_days_above_threshold}
                    </td>
                    <td className="px-3 py-2">
                      {member.rest_violations.length
                        ? member.rest_violations
                            .map((item) =>
                              item.compensation_pending
                                ? t(locale, "complianceReportRestPending")
                                : item.code
                            )
                            .join(", ")
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    </Card>
  );
}
