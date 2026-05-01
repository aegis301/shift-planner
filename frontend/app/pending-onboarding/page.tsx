"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Hourglass } from "lucide-react";
import { Card } from "@/components/Card";
import { useLocale, useSession } from "@/components/LocaleProvider";
import { apiFetch } from "@/lib/api";
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
  resolved_doctor_id: number | null;
  created_at: string;
};

export default function PendingOnboardingPage() {
  const { locale } = useLocale();
  const { me, loading, refreshMe } = useSession();
  const router = useRouter();
  const [row, setRow] = useState<JoinRequest | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);

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

  if (loading || !me || me.role !== "applicant") {
    return null;
  }

  return (
    <div className="mx-auto max-w-lg">
      <Card>
        <div className="flex items-start gap-4">
          <Hourglass className="shrink-0 text-amber-600" aria-hidden />
          <div>
            <h1 className="text-xl font-semibold text-ink">{t(locale, "pendingOnboardingTitle")}</h1>
            <p className="mt-2 text-sm text-slate-600">{t(locale, "pendingOnboardingBody")}</p>
            {row ? (
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
            ) : null}
          </div>
        </div>
      </Card>
    </div>
  );
}
