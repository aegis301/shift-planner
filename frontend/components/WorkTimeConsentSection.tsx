"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Field, inputClass } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";
import { ApiError, apiFetch } from "@/lib/api";
import { t } from "@/lib/i18n";

type WorkTimeConsent = {
  id: number;
  tier: string;
  valid_from: string;
  signed_document_reference: string | null;
  recorded_by_user_id: number | null;
  revoked_at: string | null;
  notice_period_months: number;
  effective_until: string | null;
};

type AffectedPlan = {
  planning_plan_version_id: number;
  year: number;
  month: number;
  shift_group_id: number;
  warning_codes: string[];
};

export function WorkTimeConsentSection({
  teamMemberId,
  readOnly = false
}: {
  teamMemberId: number;
  readOnly?: boolean;
}) {
  const { locale } = useLocale();
  const [rows, setRows] = useState<WorkTimeConsent[]>([]);
  const [tier, setTier] = useState("stufe_i");
  const [validFrom, setValidFrom] = useState("");
  const [documentRef, setDocumentRef] = useState("");
  const [noticeMonths, setNoticeMonths] = useState("6");
  const [message, setMessage] = useState("");
  const [findings, setFindings] = useState<AffectedPlan[]>([]);

  const reload = useCallback(async () => {
    const listed = await apiFetch<WorkTimeConsent[]>(`/api/v1/team-members/${teamMemberId}/work-time-consents`);
    setRows(listed);
  }, [teamMemberId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function recordConsent(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    setFindings([]);
    try {
      await apiFetch(`/api/v1/team-members/${teamMemberId}/work-time-consents`, {
        method: "POST",
        body: JSON.stringify({
          tier,
          valid_from: validFrom,
          signed_document_reference: documentRef.trim() ? documentRef.trim() : null,
          notice_period_months: Number(noticeMonths)
        })
      });
      setValidFrom("");
      setDocumentRef("");
      await reload();
      setMessage(t(locale, "saved"));
    } catch (e) {
      if (e instanceof ApiError && typeof e.detail === "string") {
        setMessage(e.detail);
      } else {
        setMessage(t(locale, "workTimeConsentSaveError"));
      }
    }
  }

  async function revokeConsent(row: WorkTimeConsent) {
    setMessage("");
    try {
      const result = await apiFetch<{ consent: WorkTimeConsent; affected_plans: AffectedPlan[] }>(
        `/api/v1/team-members/${teamMemberId}/work-time-consents/${row.id}/revoke`,
        { method: "POST", body: JSON.stringify({}) }
      );
      setFindings(result.affected_plans);
      await reload();
      setMessage(t(locale, "saved"));
    } catch (e) {
      if (e instanceof ApiError && typeof e.detail === "string") {
        setMessage(e.detail);
      } else {
        setMessage(t(locale, "workTimeConsentSaveError"));
      }
    }
  }

  return (
    <section className="mt-4 space-y-3">
      <h4 className="text-sm font-semibold text-slate-800">{t(locale, "workTimeConsentTitle")}</h4>
      <p className="text-xs text-slate-500">{t(locale, readOnly ? "workTimeConsentReadOnlyHelp" : "workTimeConsentHelp")}</p>
      {rows.length === 0 ? <p className="text-sm text-slate-600">{t(locale, "workTimeConsentEmpty")}</p> : null}
      <ul className="space-y-2">
        {rows.map((row) => (
          <li key={row.id} className="rounded-lg border border-slate-200 bg-white p-3 text-sm">
            <p>
              <span className="font-semibold">{t(locale, "workTimeConsentTier")}:</span> {row.tier}
            </p>
            <p>
              <span className="font-semibold">{t(locale, "workTimeConsentValidFrom")}:</span> {row.valid_from}
            </p>
            {row.signed_document_reference ? (
              <p>
                <span className="font-semibold">{t(locale, "workTimeConsentDocumentRef")}:</span> {row.signed_document_reference}
              </p>
            ) : null}
            <p>
              <span className="font-semibold">{t(locale, "workTimeConsentEffectiveUntil")}:</span>{" "}
              {row.effective_until ?? t(locale, "workTimeConsentOpenEnded")}
            </p>
            {row.revoked_at ? (
              <p className="text-amber-800">
                {t(locale, "workTimeConsentRevoked")}: {row.revoked_at} ({row.notice_period_months}{" "}
                {t(locale, "workTimeConsentNoticeMonths")})
              </p>
            ) : null}
            {!readOnly && row.revoked_at == null ? (
              <button
                type="button"
                className="mt-2 inline-flex h-9 items-center rounded-lg border border-slate-200 px-3 text-xs font-semibold text-slate-700"
                onClick={() => void revokeConsent(row)}
              >
                {t(locale, "workTimeConsentRevoke")}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
      {findings.length > 0 ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950">
          <p className="font-semibold">{t(locale, "workTimeConsentAffectedPlans")}</p>
          <ul className="mt-1 list-disc pl-5">
            {findings.map((item) => (
              <li key={item.planning_plan_version_id}>
                {item.year}-{String(item.month).padStart(2, "0")} ({item.warning_codes.join(", ")})
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {readOnly ? null : (
        <form className="grid gap-3" onSubmit={recordConsent}>
          <p className="text-xs text-slate-500">{t(locale, "workTimeConsentImmutableHelp")}</p>
          <Field label={t(locale, "workTimeConsentTier")}>
            <input className={inputClass} value={tier} onChange={(event) => setTier(event.target.value)} required />
          </Field>
          <Field label={t(locale, "workTimeConsentValidFrom")}>
            <input className={inputClass} type="date" value={validFrom} onChange={(event) => setValidFrom(event.target.value)} required />
          </Field>
          <Field label={t(locale, "workTimeConsentDocumentRef")}>
            <input className={inputClass} value={documentRef} onChange={(event) => setDocumentRef(event.target.value)} />
          </Field>
          <Field label={t(locale, "workTimeConsentNoticeMonths")}>
            <input
              className={inputClass}
              type="number"
              min={1}
              max={24}
              value={noticeMonths}
              onChange={(event) => setNoticeMonths(event.target.value)}
            />
          </Field>
          <button type="submit" className="inline-flex h-10 items-center justify-center rounded-lg bg-ink px-4 text-sm font-semibold text-white">
            {t(locale, "workTimeConsentRecord")}
          </button>
        </form>
      )}
      {message ? <p className="text-sm text-emerald-700">{message}</p> : null}
    </section>
  );
}
