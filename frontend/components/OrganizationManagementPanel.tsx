"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertTriangle, Building2, Trash2, UserPlus } from "lucide-react";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale, useSession } from "@/components/LocaleProvider";
import { isUserSession } from "@/lib/membershipRouting";
import { ApiError, apiFetch } from "@/lib/api";
import { dataTableScrollShellClassName } from "@/lib/dataTableLayout";
import { t, type Locale } from "@/lib/i18n";

type OrgSettings = { id: number; name: string; slug: string; plan_tier: string };

type MemberPatternPolicy = {
  hard_types: Array<"allowed_calendar_week_parity">;
};

type ShiftGroupOption = { id: number; code: string; name_de: string; name_en: string; is_active?: boolean };

type MembershipInvite = {
  id: number;
  organization_id: number;
  invitee_email: string;
  role: string;
  status: string;
  message: string | null;
  first_name: string | null;
  last_name: string | null;
  employment_percentage: number | null;
  shift_group_ids: number[];
  planner_shift_group_ids: number[];
  has_precreated_team_member: boolean;
  created_at: string;
};

function groupLabel(locale: Locale, g: ShiftGroupOption): string {
  return locale === "de" ? g.name_de : g.name_en;
}

function groupRowLabel(locale: Locale, g: ShiftGroupOption): string {
  const base = `${g.code} — ${groupLabel(locale, g)}`;
  if (g.is_active === false) {
    return `${base} (${t(locale, "orgManagementShiftGroupInactiveTag")})`;
  }
  return base;
}

function ShiftGroupsPickerEmpty({ locale }: { locale: Locale }) {
  return (
    <div className="text-sm text-slate-600">
      <p>{t(locale, "orgManagementShiftGroupsEmptyLine")}</p>
      <p className="mt-2">
        <Link href="/organization/shifts/groups" className="font-medium text-emerald-800 underline hover:text-emerald-900">
          {t(locale, "orgManagementShiftGroupsEmptyCta")}
        </Link>
      </p>
    </div>
  );
}

export function OrganizationManagementPanel() {
  const { locale } = useLocale();
  const { me, loading, refreshMe } = useSession();
  const router = useRouter();
  const [org, setOrg] = useState<OrgSettings | null>(null);
  const [invites, setInvites] = useState<MembershipInvite[]>([]);
  const [shiftGroups, setShiftGroups] = useState<ShiftGroupOption[]>([]);
  const [inviteMsg, setInviteMsg] = useState("");
  const [deleteMsg, setDeleteMsg] = useState("");
  const [inviteRole, setInviteRole] = useState<"planner" | "team_member">("team_member");
  const [plannerGroupIds, setPlannerGroupIds] = useState<Set<number>>(new Set());
  const [teamGroupIds, setTeamGroupIds] = useState<Set<number>>(new Set());
  const [prepareTeamProfile, setPrepareTeamProfile] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteConfirmName, setDeleteConfirmName] = useState("");
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [memberPatternPolicy, setMemberPatternPolicy] = useState<MemberPatternPolicy>({ hard_types: [] });
  const [patternPolicyMsg, setPatternPolicyMsg] = useState("");

  const orgName = org?.name ?? "";

  async function refetchInvitesAndOrg() {
    const [o, inv] = await Promise.all([
      apiFetch<OrgSettings>("/api/v1/organization"),
      apiFetch<MembershipInvite[]>("/api/v1/organization/invites"),
    ]);
    setOrg(o);
    setInvites(inv);
    await refreshMe();
  }

  useEffect(() => {
    if (loading) return;
    if (!me || !isUserSession(me) || !me.capabilities.admin) {
      router.replace("/");
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const [o, inv] = await Promise.all([
          apiFetch<OrgSettings>("/api/v1/organization"),
          apiFetch<MembershipInvite[]>("/api/v1/organization/invites"),
        ]);
        if (!cancelled) {
          setOrg(o);
          setInvites(inv);
        }
      } catch {
        if (!cancelled) {
          setOrg(null);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loading, me, router]);

  useEffect(() => {
    if (loading || !isUserSession(me) || !me.capabilities.admin) {
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const policy = await apiFetch<MemberPatternPolicy>("/api/v1/organization/member-pattern-policy");
        if (!cancelled) {
          setMemberPatternPolicy({
            hard_types: policy.hard_types.filter(
              (item): item is "allowed_calendar_week_parity" => item === "allowed_calendar_week_parity"
            )
          });
        }
      } catch {
        if (!cancelled) {
          setMemberPatternPolicy({ hard_types: [] });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loading, me]);

  useEffect(() => {
    if (loading || !isUserSession(me) || !me.capabilities.admin) return;
    const fromMe = me.organization_shift_groups;
    if (Array.isArray(fromMe)) {
      setShiftGroups(fromMe);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const sg = await apiFetch<ShiftGroupOption[]>("/api/v1/shift-groups");
        if (!cancelled) {
          setShiftGroups(sg);
        }
      } catch {
        if (!cancelled) {
          setShiftGroups([]);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loading, me]);

  function togglePlannerGroup(id: number) {
    setPlannerGroupIds((prev) => {
      const n = new Set(prev);
      if (n.has(id)) {
        n.delete(id);
      } else {
        n.add(id);
      }
      return n;
    });
  }

  function toggleTeamGroup(id: number) {
    setTeamGroupIds((prev) => {
      const n = new Set(prev);
      if (n.has(id)) {
        n.delete(id);
      } else {
        n.add(id);
      }
      return n;
    });
  }

  async function submitInvite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setInviteMsg("");
    const form = new FormData(event.currentTarget);
    const email = String(form.get("invitee_email") ?? "")
      .trim()
      .toLowerCase();
    const messageTrim = String(form.get("message") ?? "").trim();
    const body: Record<string, unknown> = {
      invitee_email: email,
      role: inviteRole,
      message: messageTrim.length ? messageTrim : null,
      prepare_team_member_profile: inviteRole === "team_member" && prepareTeamProfile,
      shift_group_ids: inviteRole === "team_member" && prepareTeamProfile ? Array.from(teamGroupIds) : [],
      planner_shift_group_ids: inviteRole === "planner" ? Array.from(plannerGroupIds) : [],
    };
    if (inviteRole === "team_member" && prepareTeamProfile) {
      body.first_name = String(form.get("first_name") ?? "").trim();
      body.last_name = String(form.get("last_name") ?? "").trim();
      body.employment_percentage = Number(form.get("employment_percentage") ?? 100);
      const notesTrim = String(form.get("notes") ?? "").trim();
      body.notes = notesTrim.length ? notesTrim : null;
    }
    try {
      await apiFetch<MembershipInvite>("/api/v1/organization/invites", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setInviteMsg("");
      (event.currentTarget as HTMLFormElement).reset();
      setPlannerGroupIds(new Set());
      setTeamGroupIds(new Set());
      setPrepareTeamProfile(false);
      await refetchInvitesAndOrg();
    } catch (e) {
      if (e instanceof ApiError && typeof e.detail === "string") {
        setInviteMsg(e.detail);
      } else {
        setInviteMsg(t(locale, "orgManagementInviteError"));
      }
    }
  }

  async function revokeInvite(id: number) {
    setInviteMsg("");
    try {
      await apiFetch(`/api/v1/organization/invites/${id}`, { method: "DELETE" });
      setInviteMsg("");
      await refetchInvitesAndOrg();
    } catch (e) {
      if (e instanceof ApiError && typeof e.detail === "string") {
        setInviteMsg(e.detail);
      } else {
        setInviteMsg(t(locale, "orgManagementInviteError"));
      }
    }
  }

  async function saveMemberPatternPolicy() {
    setPatternPolicyMsg("");
    try {
      const saved = await apiFetch<MemberPatternPolicy>("/api/v1/organization/member-pattern-policy", {
        method: "PATCH",
        body: JSON.stringify(memberPatternPolicy)
      });
      setMemberPatternPolicy(saved);
      setPatternPolicyMsg(t(locale, "saved"));
    } catch (e) {
      if (e instanceof ApiError && typeof e.detail === "string") {
        setPatternPolicyMsg(e.detail);
      } else {
        setPatternPolicyMsg(t(locale, "orgManagementInviteError"));
      }
    }
  }

  async function submitDeleteOrg() {
    if (!org) return;
    setDeleteBusy(true);
    setDeleteMsg("");
    try {
      await apiFetch("/api/v1/organization", {
        method: "DELETE",
        body: JSON.stringify({ confirm_organization_name: deleteConfirmName }),
      });
      setDeleteOpen(false);
      setDeleteMsg("");
      await refreshMe();
      router.push("/login");
      router.refresh();
    } catch (e) {
      if (e instanceof ApiError && typeof e.detail === "string") {
        setDeleteMsg(e.detail);
      } else {
        setDeleteMsg(t(locale, "orgManagementInviteError"));
      }
    } finally {
      setDeleteBusy(false);
    }
  }

  const sortedInvites = useMemo(
    () => [...invites].sort((a, b) => b.id - a.id),
    [invites]
  );

  if (loading || !isUserSession(me) || !me.capabilities.admin) {
    return null;
  }

  return (
    <div className="grid min-w-0 gap-6">
      <div className="flex min-w-0 items-center gap-3">
        <Building2 className="shrink-0 text-emerald-700" aria-hidden />
        <h1 className="min-w-0 truncate text-2xl font-semibold text-ink">{t(locale, "orgManagementTitle")}</h1>
      </div>
      {org ? (
        <Card>
          <h2 className="text-lg font-semibold text-ink">{t(locale, "organizationNameField")}</h2>
          <p className="mt-1 text-sm text-slate-700">{org.name}</p>
          <p className="mt-1 font-mono text-sm text-slate-600">{org.slug}</p>
        </Card>
      ) : null}
      <Card>
        <h2 className="text-lg font-semibold text-ink">{t(locale, "memberPatternPolicyTitle")}</h2>
        <p className="mt-1 text-sm text-slate-600">{t(locale, "memberPatternPolicyHelp")}</p>
        <p className="mt-2 text-sm text-slate-600">{t(locale, "memberPatternPolicyAvoidTimeWindowInfo")}</p>
        <div className="mt-4 grid gap-2 text-sm text-slate-800">
          <label className="inline-flex items-center gap-2">
            <input
              type="checkbox"
              checked={memberPatternPolicy.hard_types.includes("allowed_calendar_week_parity")}
              onChange={() =>
                setMemberPatternPolicy((prev) => ({
                  hard_types: prev.hard_types.includes("allowed_calendar_week_parity")
                    ? prev.hard_types.filter((item) => item !== "allowed_calendar_week_parity")
                    : [...prev.hard_types, "allowed_calendar_week_parity"]
                }))
              }
            />
            {t(locale, "memberPatternPolicyHardWeekParity")}
          </label>
        </div>
        <button
          type="button"
          className="mt-4 inline-flex h-10 items-center justify-center rounded-lg bg-ink px-4 text-sm font-semibold text-white"
          onClick={() => void saveMemberPatternPolicy()}
        >
          {t(locale, "save")}
        </button>
        {patternPolicyMsg ? <p className="mt-2 text-sm text-emerald-700">{patternPolicyMsg}</p> : null}
      </Card>
      <Card>
        <div className="flex items-center gap-2">
          <UserPlus className="text-emerald-700" aria-hidden />
          <h2 className="text-lg font-semibold text-ink">{t(locale, "orgManagementInvites")}</h2>
        </div>
        <form className="mt-4 grid max-w-xl gap-3" onSubmit={(e) => void submitInvite(e)}>
          <Field label={t(locale, "email")}>
            <input className={inputClass} name="invitee_email" type="email" required autoComplete="off" />
          </Field>
          <Field label={t(locale, "orgManagementInviteRole")}>
            <select
              className={inputClass}
              value={inviteRole}
              onChange={(ev) => {
                const v = ev.target.value as "planner" | "team_member";
                setInviteRole(v);
                if (v === "planner") {
                  setPrepareTeamProfile(false);
                  setTeamGroupIds(new Set());
                }
              }}
            >
              <option value="planner">{t(locale, "roleOptionPlanner")}</option>
              <option value="team_member">{t(locale, "roleOptionTeamMember")}</option>
            </select>
          </Field>
          {inviteRole === "planner" ? (
            <Field label={t(locale, "orgManagementPlannerGroups")}>
              <div className="mt-1 flex max-h-40 flex-col gap-2 overflow-y-auto rounded-lg border border-slate-200 p-2">
                {shiftGroups.length === 0 ? (
                  <ShiftGroupsPickerEmpty locale={locale} />
                ) : (
                  shiftGroups.map((g) => (
                    <label key={g.id} className="flex cursor-pointer items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={plannerGroupIds.has(g.id)}
                        onChange={() => togglePlannerGroup(g.id)}
                      />
                      <span>{groupRowLabel(locale, g)}</span>
                    </label>
                  ))
                )}
              </div>
            </Field>
          ) : (
            <div className="grid gap-3">
              <label className="flex cursor-pointer items-start gap-2 text-sm text-slate-800">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={prepareTeamProfile}
                  onChange={(ev) => {
                    setPrepareTeamProfile(ev.target.checked);
                    if (!ev.target.checked) {
                      setTeamGroupIds(new Set());
                    }
                  }}
                />
                <span>
                  <span className="font-medium">{t(locale, "orgManagementPrepareTeamProfile")}</span>
                  <span className="mt-0.5 block text-slate-600">{t(locale, "orgManagementPrepareTeamProfileHint")}</span>
                </span>
              </label>
              {prepareTeamProfile ? (
                <>
                  <Field label={t(locale, "firstName")}>
                    <input className={inputClass} name="first_name" required minLength={1} />
                  </Field>
                  <Field label={t(locale, "lastName")}>
                    <input className={inputClass} name="last_name" required minLength={1} />
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
                  <Field label={t(locale, "orgManagementTeamGroups")}>
                    <div className="mt-1 flex max-h-40 flex-col gap-2 overflow-y-auto rounded-lg border border-slate-200 p-2">
                      {shiftGroups.length === 0 ? (
                        <ShiftGroupsPickerEmpty locale={locale} />
                      ) : (
                        shiftGroups.map((g) => (
                          <label key={g.id} className="flex cursor-pointer items-center gap-2 text-sm">
                            <input
                              type="checkbox"
                              checked={teamGroupIds.has(g.id)}
                              onChange={() => toggleTeamGroup(g.id)}
                            />
                            <span>{groupRowLabel(locale, g)}</span>
                          </label>
                        ))
                      )}
                    </div>
                  </Field>
                </>
              ) : null}
            </div>
          )}
          <Field label={t(locale, "joinMessageOptional")}>
            <textarea className={`${inputClass} min-h-[72px] py-2`} name="message" maxLength={2000} />
          </Field>
          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:gap-3">
            <button
              type="submit"
              className="h-11 w-fit shrink-0 rounded-lg bg-ink px-4 text-sm font-semibold text-white"
            >
              {t(locale, "orgManagementSendInvite")}
            </button>
            {inviteMsg ? (
              <p className="text-sm text-red-600 sm:min-w-0 sm:flex-1" role="alert">
                {inviteMsg}
              </p>
            ) : null}
          </div>
        </form>
        <div className={`mt-6 ${dataTableScrollShellClassName} rounded-lg border border-slate-200`}>
          <table className="w-full min-w-[32rem] text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase text-slate-500">
                <th className="sticky top-0 z-10 bg-white py-2 pr-3 shadow-[0_1px_0_0_rgb(226_232_240)]">{t(locale, "email")}</th>
                <th className="sticky top-0 z-10 bg-white py-2 pr-3 shadow-[0_1px_0_0_rgb(226_232_240)]">{t(locale, "orgManagementInviteRole")}</th>
                <th className="sticky top-0 z-10 bg-white py-2 pr-3 shadow-[0_1px_0_0_rgb(226_232_240)]">{t(locale, "orgManagementInviteProfileColumn")}</th>
                <th className="sticky top-0 z-10 bg-white py-2 pr-3 shadow-[0_1px_0_0_rgb(226_232_240)]">{t(locale, "status")}</th>
                <th className="sticky top-0 z-10 bg-white py-2 pr-3 shadow-[0_1px_0_0_rgb(226_232_240)]">{t(locale, "createdAt")}</th>
                <th className="sticky top-0 z-10 bg-white py-2 shadow-[0_1px_0_0_rgb(226_232_240)]">{t(locale, "orgManagementRevoke")}</th>
              </tr>
            </thead>
            <tbody>
              {sortedInvites.map((row) => (
                <tr key={row.id} className="border-b border-slate-100">
                  <td className="py-2 pr-3 font-mono text-xs">{row.invitee_email}</td>
                  <td className="py-2 pr-3">{row.role === "planner" ? t(locale, "roleOptionPlanner") : t(locale, "roleOptionTeamMember")}</td>
                  <td className="py-2 pr-3 text-xs text-slate-600">
                    {row.has_precreated_team_member ? t(locale, "orgManagementInvitePrecreatedBadge") : t(locale, "emptyValue")}
                  </td>
                  <td className="py-2 pr-3">{row.status}</td>
                  <td className="py-2 pr-3 text-xs text-slate-600">{new Date(row.created_at).toLocaleString(locale)}</td>
                  <td className="py-2">
                    {row.status === "pending" ? (
                      <button
                        type="button"
                        className="text-sm font-medium text-red-700 hover:underline"
                        onClick={() => void revokeInvite(row.id)}
                      >
                        {t(locale, "orgManagementRevoke")}
                      </button>
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card>
        <div className="flex items-start gap-3">
          <Trash2 className="mt-0.5 shrink-0 text-red-600" aria-hidden />
          <div className="min-w-0 flex-1">
            <h2 className="text-lg font-semibold text-red-900">{t(locale, "orgManagementDeleteSection")}</h2>
            <p className="mt-2 text-sm text-slate-600">{t(locale, "orgManagementDeleteWarning")}</p>
            <button
              type="button"
              className="mt-4 h-11 rounded-lg border border-red-300 bg-red-50 px-4 text-sm font-semibold text-red-900 hover:bg-red-100"
              onClick={() => {
                setDeleteConfirmName("");
                setDeleteMsg("");
                setDeleteOpen(true);
              }}
            >
              {t(locale, "orgManagementDeleteButton")}
            </button>
          </div>
        </div>
      </Card>
      {deleteOpen ? (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="org-delete-title"
        >
          <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-5 shadow-xl">
            <div className="flex items-start gap-3">
              <AlertTriangle className="shrink-0 text-amber-600" aria-hidden />
              <div>
                <h3 id="org-delete-title" className="text-lg font-semibold text-ink">
                  {t(locale, "orgManagementDeleteModalTitle")}
                </h3>
                <p className="mt-2 text-sm text-slate-600">{t(locale, "orgManagementDeleteTypeNameHint", { name: orgName })}</p>
              </div>
            </div>
            <Field label={t(locale, "orgManagementDeleteConfirmLabel")}>
              <input
                className={inputClass}
                value={deleteConfirmName}
                onChange={(e) => setDeleteConfirmName(e.target.value)}
                autoComplete="off"
              />
            </Field>
            {deleteMsg ? (
              <p className="mt-3 text-sm text-red-600" role="alert">
                {deleteMsg}
              </p>
            ) : null}
            <div className="mt-4 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                className="h-10 rounded-lg border border-slate-200 bg-white px-4 text-sm font-medium text-slate-800"
                onClick={() => {
                  setDeleteOpen(false);
                  setDeleteMsg("");
                }}
              >
                {t(locale, "orgStaffModalCancel")}
              </button>
              <button
                type="button"
                disabled={deleteBusy || deleteConfirmName.trim() !== orgName.trim()}
                className="h-10 rounded-lg bg-red-700 px-4 text-sm font-semibold text-white disabled:opacity-40"
                onClick={() => void submitDeleteOrg()}
              >
                {t(locale, "orgManagementDeleteButton")}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
