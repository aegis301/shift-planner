"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Hourglass } from "lucide-react";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale, useSession } from "@/components/LocaleProvider";
import { ApiError, apiFetch } from "@/lib/api";
import { t } from "@/lib/i18n";

type JoinRequest = {
  id: number;
  organization_id: number;
  requester_user_id: number;
  requester_email: string;
  first_name: string;
  last_name: string;
  message: string | null;
  status: string;
  resolution: string | null;
  resolved_team_member_id: number | null;
  created_at: string;
};

export default function PendingOnboardingPage() {
  const { locale } = useLocale();
  const { me, loading, refreshMe } = useSession();
  const router = useRouter();
  const [row, setRow] = useState<JoinRequest | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [resubmitBusy, setResubmitBusy] = useState(false);
  const [resubmitError, setResubmitError] = useState("");

  useEffect(() => {
    if (loading) return;
    if (!me) {
      router.replace("/login");
      return;
    }
    if (me.role !== "applicant") {
      router.replace("/");
      return;
    }
    void (async () => {
      try {
        const data = await apiFetch<JoinRequest | null>("/api/v1/auth/me/join-request");
        setRow(data ?? null);
      } catch {
        setRow(null);
      }
    })();
  }, [loading, me, router]);

  async function cancel() {
    if (!row) return;
    setBusy(true);
    try {
      await apiFetch(`/api/v1/organization/join-requests/${row.id}/cancel`, { method: "POST" });
      await refreshMe();
      router.push("/login");
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  async function resubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setResubmitError("");
    const form = new FormData(event.currentTarget);
    const first_name = String(form.get("first_name") ?? "").trim();
    const last_name = String(form.get("last_name") ?? "").trim();
    const messageRaw = String(form.get("message") ?? "").trim();
    const message = messageRaw.length > 0 ? messageRaw : null;
    setResubmitBusy(true);
    try {
      const created = await apiFetch<JoinRequest>("/api/v1/auth/me/join-request", {
        method: "POST",
        body: JSON.stringify({ first_name, last_name, message }),
      });
      setRow(created);
      await refreshMe();
    } catch (e) {
      setResubmitError(e instanceof ApiError ? e.message : t(locale, "pendingOnboardingResubmitError"));
    } finally {
      setResubmitBusy(false);
    }
  }

  if (loading || !me || me.role !== "applicant") {
    return null;
  }

  return (
    <div className="mx-auto max-w-lg">
      <Card>
        <div className="flex items-start gap-4">
          <Hourglass className="shrink-0 text-amber-600" aria-hidden />
          <div className="min-w-0 flex-1">
            <h1 className="text-xl font-semibold text-ink">{t(locale, "pendingOnboardingTitle")}</h1>
            <p className="mt-2 text-sm text-slate-600">{t(locale, "pendingOnboardingBody")}</p>
            {row === undefined ? null : row ? (
              <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
                <p className="font-medium text-ink">
                  {me.organization.name} ({me.organization.slug})
                </p>
                <p className="mt-1">
                  {t(locale, "joinRequestFrom")}: {row.requester_email}
                </p>
                <button
                  type="button"
                  disabled={busy}
                  className="mt-3 h-10 rounded-lg border border-slate-300 bg-white px-3 text-sm font-medium text-slate-800 disabled:opacity-50"
                  onClick={() => void cancel()}
                >
                  {t(locale, "cancelJoinRequest")}
                </button>
              </div>
            ) : (
              <div className="mt-4">
                <h2 className="text-lg font-semibold text-ink">{t(locale, "pendingOnboardingResubmitTitle")}</h2>
                <p className="mt-2 text-sm text-slate-600">{t(locale, "pendingOnboardingResubmitBody")}</p>
                {resubmitError ? <p className="mt-2 text-sm text-red-600">{resubmitError}</p> : null}
                <form className="mt-4 grid gap-3" onSubmit={resubmit}>
                  <Field label={t(locale, "firstName")}>
                    <input className={inputClass} name="first_name" required minLength={1} maxLength={255} />
                  </Field>
                  <Field label={t(locale, "lastName")}>
                    <input className={inputClass} name="last_name" required minLength={1} maxLength={255} />
                  </Field>
                  <Field label={t(locale, "joinMessageOptional")}>
                    <textarea className={`${inputClass} min-h-[88px]`} name="message" maxLength={2000} rows={3} />
                  </Field>
                  <button
                    type="submit"
                    disabled={resubmitBusy}
                    className="h-11 rounded-lg bg-ink px-4 text-sm font-semibold text-white disabled:opacity-50"
                  >
                    {t(locale, "pendingOnboardingResubmitSubmit")}
                  </button>
                </form>
              </div>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}
