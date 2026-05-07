"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, ClipboardList } from "lucide-react";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale, useSession } from "@/components/LocaleProvider";
import { isUserSession } from "@/lib/membershipRouting";
import { apiFetch } from "@/lib/api";
import { t } from "@/lib/i18n";

type OrgSettings = { id: number; name: string; slug: string; plan_tier: string };

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

type UnlinkedTeamMemberRow = {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
  user_id: number | null;
};

export function JoinRequestsAdminPanel() {
  const { locale } = useLocale();
  const { me, loading, refreshMe } = useSession();
  const router = useRouter();
  const [org, setOrg] = useState<OrgSettings | null>(null);
  const [requests, setRequests] = useState<JoinRequest[]>([]);
  const [unlinkedTeamMembers, setUnlinkedTeamMembers] = useState<UnlinkedTeamMemberRow[]>([]);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (loading) return;
    if (!me || !isUserSession(me) || !me.capabilities.admin) {
      router.replace("/");
      return;
    }
    void (async () => {
      try {
        const [o, r, d] = await Promise.all([
          apiFetch<OrgSettings>("/api/v1/organization"),
          apiFetch<JoinRequest[]>("/api/v1/organization/join-requests?status=pending"),
          apiFetch<UnlinkedTeamMemberRow[]>("/api/v1/team-members"),
        ]);
        setOrg(o);
        setRequests(r);
        setUnlinkedTeamMembers(d.filter((x) => x.user_id == null));
      } catch {
        setOrg(null);
      }
    })();
  }, [loading, me, router]);

  async function reload() {
    if (!isUserSession(me) || !me.capabilities.admin) return;
    const [o, r, d] = await Promise.all([
      apiFetch<OrgSettings>("/api/v1/organization"),
      apiFetch<JoinRequest[]>("/api/v1/organization/join-requests?status=pending"),
      apiFetch<UnlinkedTeamMemberRow[]>("/api/v1/team-members"),
    ]);
    setOrg(o);
    setRequests(r);
    setUnlinkedTeamMembers(d.filter((x) => x.user_id == null));
    await refreshMe();
  }

  async function approveCreate(req: JoinRequest, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMsg("");
    const form = new FormData(event.currentTarget);
    try {
      await apiFetch(`/api/v1/organization/join-requests/${req.id}/approve-create-team-member`, {
        method: "POST",
        body: JSON.stringify({
          first_name: form.get("first_name"),
          last_name: form.get("last_name"),
          email: form.get("email"),
          employment_percentage: Number(form.get("employment_percentage") ?? 100),
          notes: form.get("notes") || null,
          shift_group_ids: [],
        }),
      });
      await reload();
    } catch (e) {
      setMsg(String(e));
    }
  }

  async function approveLink(req: JoinRequest, memberId: number) {
    setMsg("");
    try {
      await apiFetch(`/api/v1/organization/join-requests/${req.id}/approve-link-team-member`, {
        method: "POST",
        body: JSON.stringify({ team_member_id: memberId }),
      });
      await reload();
    } catch (e) {
      setMsg(String(e));
    }
  }

  async function reject(req: JoinRequest) {
    setMsg("");
    try {
      await apiFetch(`/api/v1/organization/join-requests/${req.id}/reject`, { method: "POST" });
      await reload();
    } catch (e) {
      setMsg(String(e));
    }
  }

  if (loading || !isUserSession(me) || !me.capabilities.admin) {
    return null;
  }

  return (
    <div className="grid min-w-0 gap-6">
      <div className="flex min-w-0 items-center gap-3">
        <Building2 className="shrink-0 text-emerald-700" aria-hidden />
        <h1 className="min-w-0 truncate text-2xl font-semibold text-ink">{t(locale, "organizationAdminTitle")}</h1>
      </div>
      {org ? (
        <Card>
          <h2 className="text-lg font-semibold text-ink">{t(locale, "organizationNameField")}</h2>
          <p className="mt-1 text-sm text-slate-700">{org.name}</p>
          <h2 className="mt-4 text-lg font-semibold text-ink">{t(locale, "organizationCodeLabel")}</h2>
          <p className="mt-1 font-mono text-sm text-slate-800">{org.slug}</p>
          <p className="mt-2 text-xs text-slate-500">{t(locale, "organizationCodeHint")}</p>
        </Card>
      ) : null}
      <div className="flex items-center gap-2">
        <ClipboardList className="text-coral" aria-hidden />
        <h2 className="text-xl font-semibold text-ink">{t(locale, "joinRequestsNav")}</h2>
      </div>
      {msg ? <p className="text-sm text-red-600">{msg}</p> : null}
      {requests.length === 0 ? (
        <p className="text-sm text-slate-600">{t(locale, "joinRequestsEmpty")}</p>
      ) : (
        <div className="grid gap-4">
          {requests.map((req) => (
            <Card key={req.id}>
              <p className="text-sm font-medium text-ink">
                {t(locale, "joinRequestFrom")}: {req.requester_email}
              </p>
              <p className="text-sm text-slate-600">
                {req.first_name} {req.last_name}
              </p>
              {req.message ? <p className="mt-2 text-sm text-slate-600">{req.message}</p> : null}
              <form className="mt-4 grid gap-3 border-t border-slate-100 pt-4" onSubmit={(e) => void approveCreate(req, e)}>
                <p className="text-sm font-semibold text-ink">{t(locale, "approveAsNewTeamMember")}</p>
                <Field label={t(locale, "firstName")}>
                  <input className={inputClass} name="first_name" required defaultValue={req.first_name} />
                </Field>
                <Field label={t(locale, "lastName")}>
                  <input className={inputClass} name="last_name" required defaultValue={req.last_name} />
                </Field>
                <Field label={t(locale, "email")}>
                  <input className={inputClass} name="email" type="email" required defaultValue={req.requester_email} />
                </Field>
                <Field label={t(locale, "employment")}>
                  <input
                    className={inputClass}
                    name="employment_percentage"
                    type="number"
                    min={1}
                    max={100}
                    defaultValue={100}
                  />
                </Field>
                <Field label={t(locale, "notes")}>
                  <textarea className={`${inputClass} min-h-[72px] py-2`} name="notes" />
                </Field>
                <button type="submit" className="h-11 rounded-lg bg-ink px-4 text-sm font-semibold text-white">
                  {t(locale, "confirmApproveCreateTeamMember")}
                </button>
              </form>
              <div className="mt-4 border-t border-slate-100 pt-4">
                <p className="text-sm font-semibold text-ink">{t(locale, "linkExistingTeamMember")}</p>
                <p className="mt-1 text-xs text-slate-500">{t(locale, "selectTeamMemberToLink")}</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {unlinkedTeamMembers.length === 0 ? (
                    <p className="text-sm text-slate-500">{t(locale, "noData")}</p>
                  ) : (
                    unlinkedTeamMembers.map((d) => (
                      <button
                        key={d.id}
                        type="button"
                        className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-left text-sm text-slate-800 shadow-sm"
                        onClick={() => void approveLink(req, d.id)}
                      >
                        {d.last_name}, {d.first_name}
                        <span className="block text-xs text-slate-500">{d.email}</span>
                      </button>
                    ))
                  )}
                </div>
              </div>
              <button
                type="button"
                className="mt-4 h-10 w-full rounded-lg border border-red-200 bg-red-50 text-sm font-medium text-red-800"
                onClick={() => void reject(req)}
              >
                {t(locale, "rejectJoinRequest")}
              </button>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
