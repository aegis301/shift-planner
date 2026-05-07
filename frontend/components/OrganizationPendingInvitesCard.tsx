"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Mail } from "lucide-react";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale, useSession, type MeUser } from "@/components/LocaleProvider";
import { isUserSession } from "@/lib/membershipRouting";
import { ApiError, apiFetch } from "@/lib/api";
import { membershipDefaultPath } from "@/lib/membershipRouting";
import { t, type Locale } from "@/lib/i18n";

type OrgBrief = { id: number; name: string; slug: string; plan_tier: string };

type ShiftGroupOption = { id: number; code: string; name_de: string; name_en: string; is_active?: boolean };

type PendingInvite = {
  id: number;
  organization: OrgBrief;
  role: string;
  message: string | null;
  first_name: string | null;
  last_name: string | null;
  needs_profile_on_accept: boolean;
  has_precreated_team_member: boolean;
  accept_shift_groups: ShiftGroupOption[];
  created_at: string;
};

function roleLabel(locale: Locale, role: string): string {
  if (role === "planner") {
    return t(locale, "roleOptionPlanner");
  }
  if (role === "team_member") {
    return t(locale, "roleOptionTeamMember");
  }
  return role;
}

function groupOptLabel(locale: Locale, g: ShiftGroupOption): string {
  const name = locale === "de" ? g.name_de : g.name_en;
  const base = `${g.code} — ${name}`;
  if (g.is_active === false) {
    return `${base} (${t(locale, "orgManagementShiftGroupInactiveTag")})`;
  }
  return base;
}

export function OrganizationPendingInvitesCard() {
  const { locale } = useLocale();
  const { me, loading, refreshMe } = useSession();
  const router = useRouter();
  const [rows, setRows] = useState<PendingInvite[]>([]);
  const [msg, setMsg] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [profileByInviteId, setProfileByInviteId] = useState<
    Record<number, { firstName: string; lastName: string; employment: string; notes: string; groupIds: number[] }>
  >({});

  useEffect(() => {
    if (loading || !me || !isUserSession(me)) return;
    let cancelled = false;
    void (async () => {
      try {
        const data = await apiFetch<PendingInvite[]>("/api/v1/auth/me/organization-invites");
        if (!cancelled) {
          setRows(data);
        }
      } catch {
        if (!cancelled) {
          setRows([]);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loading, me]);

  useEffect(() => {
    setProfileByInviteId((prev) => {
      const next = { ...prev };
      for (const r of rows) {
        if (r.needs_profile_on_accept && next[r.id] === undefined) {
          next[r.id] = { firstName: "", lastName: "", employment: "100", notes: "", groupIds: [] };
        }
      }
      return next;
    });
  }, [rows]);

  function toggleGroupForInvite(inviteId: number, groupId: number): void {
    setProfileByInviteId((prev) => {
      const cur = prev[inviteId] ?? { firstName: "", lastName: "", employment: "100", notes: "", groupIds: [] };
      const set = new Set(cur.groupIds);
      if (set.has(groupId)) {
        set.delete(groupId);
      } else {
        set.add(groupId);
      }
      return { ...prev, [inviteId]: { ...cur, groupIds: [...set] } };
    });
  }

  async function accept(row: PendingInvite) {
    setMsg("");
    setBusyId(row.id);
    let body: Record<string, unknown> | undefined;
    if (row.needs_profile_on_accept) {
      const p = profileByInviteId[row.id] ?? {
        firstName: "",
        lastName: "",
        employment: "100",
        notes: "",
        groupIds: [],
      };
      if (!p.firstName.trim() || !p.lastName.trim() || p.groupIds.length === 0) {
        setMsg(t(locale, "settingsOrganizationInviteAcceptNeedsProfile"));
        setBusyId(null);
        return;
      }
      const notesTrim = p.notes.trim();
      body = {
        first_name: p.firstName.trim(),
        last_name: p.lastName.trim(),
        employment_percentage: Math.min(100, Math.max(1, Number(p.employment) || 100)),
        shift_group_ids: p.groupIds,
        notes: notesTrim.length ? notesTrim : null,
      };
    }
    try {
      const user = await apiFetch<MeUser>(`/api/v1/auth/me/organization-invites/${row.id}/accept`, {
        method: "POST",
        body: JSON.stringify(body ?? {}),
      });
      await refreshMe();
      router.push(membershipDefaultPath(user));
      router.refresh();
    } catch (e) {
      if (e instanceof ApiError && typeof e.detail === "string") {
        setMsg(e.detail);
      } else {
        setMsg(t(locale, "settingsOrganizationInviteError"));
      }
    } finally {
      setBusyId(null);
      try {
        const data = await apiFetch<PendingInvite[]>("/api/v1/auth/me/organization-invites");
        setRows(data);
      } catch {
        setRows([]);
      }
    }
  }

  async function decline(id: number) {
    setMsg("");
    setBusyId(id);
    try {
      await apiFetch(`/api/v1/auth/me/organization-invites/${id}/decline`, { method: "POST" });
      const data = await apiFetch<PendingInvite[]>("/api/v1/auth/me/organization-invites");
      setRows(data);
      await refreshMe();
    } catch (e) {
      if (e instanceof ApiError && typeof e.detail === "string") {
        setMsg(e.detail);
      } else {
        setMsg(t(locale, "settingsOrganizationInviteError"));
      }
    } finally {
      setBusyId(null);
    }
  }

  if (loading || !me || !isUserSession(me) || rows.length === 0) {
    return null;
  }

  return (
    <div className="md:col-span-2">
      <Card>
        <div className="flex items-start gap-4">
          <Mail className="shrink-0 text-emerald-700" aria-hidden />
          <div className="min-w-0 flex-1">
            <h2 className="text-xl font-semibold text-ink">{t(locale, "settingsOrganizationInvitesTitle")}</h2>
            <ul className="mt-4 divide-y divide-slate-100 rounded-xl border border-slate-200">
              {rows.map((row) => {
                const p = profileByInviteId[row.id];
                return (
                  <li key={row.id} className="flex flex-col gap-3 px-4 py-4">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div className="min-w-0">
                        <p className="font-medium text-ink">
                          {row.organization.name.trim() ? row.organization.name : row.organization.slug}
                        </p>
                        <p className="font-mono text-xs text-slate-600">{row.organization.slug}</p>
                        <p className="text-sm text-slate-600">{roleLabel(locale, row.role)}</p>
                        {row.message ? <p className="mt-1 text-sm text-slate-500">{row.message}</p> : null}
                        {row.has_precreated_team_member ? (
                          <p className="mt-2 text-sm text-emerald-800">{t(locale, "settingsOrganizationInvitePrecreatedHint")}</p>
                        ) : null}
                      </div>
                      <div className="flex shrink-0 flex-wrap gap-2">
                        <button
                          type="button"
                          disabled={busyId != null}
                          className="h-10 rounded-lg bg-emerald-700 px-4 text-sm font-semibold text-white disabled:opacity-50"
                          onClick={() => void accept(row)}
                        >
                          {t(locale, "settingsOrganizationInviteAccept")}
                        </button>
                        <button
                          type="button"
                          disabled={busyId != null}
                          className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-800 disabled:opacity-50"
                          onClick={() => void decline(row.id)}
                        >
                          {t(locale, "settingsOrganizationInviteDecline")}
                        </button>
                      </div>
                    </div>
                    {row.needs_profile_on_accept && p ? (
                      <div className="rounded-lg border border-slate-200 bg-slate-50/80 p-3 sm:p-4">
                        <p className="text-sm font-medium text-ink">{t(locale, "settingsOrganizationInviteProfileFormTitle")}</p>
                        <p className="mt-2 text-xs text-slate-600">{t(locale, "orgManagementTeamGroups")}</p>
                        <div className="mt-3 grid gap-3 sm:grid-cols-2">
                          <Field label={t(locale, "firstName")}>
                            <input
                              className={inputClass}
                              value={p.firstName}
                              onChange={(ev) =>
                                setProfileByInviteId((prev) => ({
                                  ...prev,
                                  [row.id]: { ...p, firstName: ev.target.value },
                                }))
                              }
                            />
                          </Field>
                          <Field label={t(locale, "lastName")}>
                            <input
                              className={inputClass}
                              value={p.lastName}
                              onChange={(ev) =>
                                setProfileByInviteId((prev) => ({
                                  ...prev,
                                  [row.id]: { ...p, lastName: ev.target.value },
                                }))
                              }
                            />
                          </Field>
                          <Field label={t(locale, "employment")}>
                            <input
                              className={inputClass}
                              type="number"
                              min={1}
                              max={100}
                              value={p.employment}
                              onChange={(ev) =>
                                setProfileByInviteId((prev) => ({
                                  ...prev,
                                  [row.id]: { ...p, employment: ev.target.value },
                                }))
                              }
                            />
                          </Field>
                          <Field label={t(locale, "notes")}>
                            <input
                              className={inputClass}
                              value={p.notes}
                              onChange={(ev) =>
                                setProfileByInviteId((prev) => ({
                                  ...prev,
                                  [row.id]: { ...p, notes: ev.target.value },
                                }))
                              }
                            />
                          </Field>
                        </div>
                        <div className="mt-3 flex max-h-40 flex-col gap-2 overflow-y-auto rounded-lg border border-slate-200 bg-white p-2">
                          {row.accept_shift_groups.length === 0 ? (
                            <p className="text-sm text-slate-500">{t(locale, "noData")}</p>
                          ) : (
                            row.accept_shift_groups.map((g) => (
                              <label key={g.id} className="flex cursor-pointer items-center gap-2 text-sm">
                                <input
                                  type="checkbox"
                                  checked={p.groupIds.includes(g.id)}
                                  onChange={() => toggleGroupForInvite(row.id, g.id)}
                                />
                                <span>
                                  {g.code} — {groupOptLabel(locale, g)}
                                </span>
                              </label>
                            ))
                          )}
                        </div>
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
            {msg ? <p className="mt-3 text-sm text-red-600">{msg}</p> : null}
          </div>
        </div>
      </Card>
    </div>
  );
}
