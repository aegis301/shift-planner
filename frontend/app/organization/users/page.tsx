"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ContactRound } from "lucide-react";
import { Card } from "@/components/Card";
import { useLocale, useSession } from "@/components/LocaleProvider";
import { apiFetch } from "@/lib/api";
import { t } from "@/lib/i18n";

type OrgUserRow = {
  id: number;
  email: string;
  role: string;
  locale: string;
  linked_doctor_id: number | null;
  linked_doctor_label: string | null;
};

export default function OrganizationUsersPage() {
  const { locale } = useLocale();
  const { me, loading } = useSession();
  const router = useRouter();
  const [rows, setRows] = useState<OrgUserRow[]>([]);
  const [loadError, setLoadError] = useState(false);
  const [copiedId, setCopiedId] = useState<number | null>(null);

  useEffect(() => {
    if (loading) return;
    if (!me?.capabilities.admin) {
      router.replace("/");
      return;
    }
    void (async () => {
      try {
        const data = await apiFetch<OrgUserRow[]>("/api/v1/organization/users");
        setRows(data);
      } catch {
        setLoadError(true);
      }
    })();
  }, [loading, me, router]);

  async function copyId(id: number) {
    try {
      await navigator.clipboard.writeText(String(id));
      setCopiedId(id);
      window.setTimeout(() => setCopiedId((x) => (x === id ? null : x)), 2000);
    } catch {
      setCopiedId(null);
    }
  }

  if (loading || !me?.capabilities.admin) {
    return null;
  }

  return (
    <div className="grid gap-5">
      <div className="flex items-center gap-3">
        <ContactRound className="text-emerald-700" aria-hidden />
        <h1 className="text-2xl font-semibold text-ink">{t(locale, "orgUserAccountsTitle")}</h1>
      </div>
      <p className="max-w-3xl text-sm text-slate-600">{t(locale, "orgUserAccountsHelp")}</p>
      {loadError ? <p className="text-sm text-red-600">{t(locale, "apiUnavailable")}</p> : null}
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs font-semibold uppercase tracking-wide text-slate-500">
                <th className="py-2 pr-3">{t(locale, "orgUserColumnId")}</th>
                <th className="py-2 pr-3">{t(locale, "orgUserColumnEmail")}</th>
                <th className="py-2 pr-3">{t(locale, "orgUserColumnRole")}</th>
                <th className="py-2 pr-3">{t(locale, "orgUserColumnDoctor")}</th>
                <th className="py-2">{t(locale, "orgUserColumnActions")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-slate-100 last:border-0">
                  <td className="py-3 pr-3 font-mono text-slate-900">{r.id}</td>
                  <td className="max-w-[200px] truncate py-3 pr-3 text-slate-800" title={r.email}>
                    {r.email}
                  </td>
                  <td className="py-3 pr-3 text-slate-700">{r.role}</td>
                  <td className="max-w-[220px] truncate py-3 pr-3 text-slate-700" title={r.linked_doctor_label ?? ""}>
                    {r.linked_doctor_label ?? t(locale, "emptyValue")}
                    {r.linked_doctor_id != null ? (
                      <span className="ml-1 font-mono text-xs text-slate-500">#{r.linked_doctor_id}</span>
                    ) : null}
                  </td>
                  <td className="py-3">
                    <button
                      type="button"
                      className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs font-medium text-slate-700 shadow-sm"
                      onClick={() => void copyId(r.id)}
                    >
                      {copiedId === r.id ? t(locale, "orgUserCopied") : t(locale, "orgUserCopyId")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
