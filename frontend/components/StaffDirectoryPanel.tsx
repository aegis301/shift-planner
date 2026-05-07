"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { ContactRound, Plus, RefreshCw, X } from "lucide-react";
import { Card } from "@/components/Card";
import { useLocale, useSession } from "@/components/LocaleProvider";
import { isUserSession } from "@/lib/membershipRouting";
import { ApiError, apiFetch } from "@/lib/api";
import { dataTableScrollShellClassName } from "@/lib/dataTableLayout";
import { t, type Locale, type TranslationKey } from "@/lib/i18n";
import { TeamMemberCreateModal, TeamMemberEditorModal, isTeamMemberRecord, type TeamMemberRecord } from "@/components/ResourceForms";

type StaffDirectoryLinkStatus =
  | "team_member_only"
  | "login_only"
  | "login_unlinked"
  | "linked_ok"
  | "linked_wrong_user"
  | "linked_foreign_user";

type StaffDirectoryRow = {
  email: string;
  team_member_id: number | null;
  team_member_label: string | null;
  team_member_is_active: boolean | null;
  user_id: number | null;
  user_role: string | null;
  user_is_active: boolean | null;
  linked_user_id: number | null;
  linked_user_role: string | null;
  linked_user_is_active: boolean | null;
  link_status: StaffDirectoryLinkStatus;
};

const STAFF_ASSIGNABLE_ROLES = ["admin", "planner", "team_member"] as const;
type StaffAssignableRole = (typeof STAFF_ASSIGNABLE_ROLES)[number];

const OTHER_ROLE_VALUE = "__other__" as const;

type StaffActionModal =
  | {
      kind: "role";
      rowKey: string;
      userId: number;
      fromRole: string;
      toRole: StaffAssignableRole;
    }
  | { kind: "unlink"; rowKey: string; row: StaffDirectoryRow }
  | { kind: "remove"; rowKey: string; userId: number };

function rowKeyOf(r: StaffDirectoryRow): string {
  return `${r.email}\t${r.team_member_id ?? ""}\t${r.user_id ?? ""}\t${r.linked_user_id ?? ""}`;
}

function linkStatusTranslationKey(status: StaffDirectoryLinkStatus): TranslationKey {
  switch (status) {
    case "team_member_only":
      return "orgStaffLinkTeamProfileOnly";
    case "login_only":
      return "orgStaffLinkLoginOnly";
    case "login_unlinked":
      return "orgStaffLinkLoginUnlinked";
    case "linked_ok":
      return "orgStaffLinkLinkedOk";
    case "linked_wrong_user":
      return "orgStaffLinkWrongUser";
    case "linked_foreign_user":
      return "orgStaffLinkForeignUser";
    default:
      return "orgStaffLinkLoginOnly";
  }
}

function isStaffAssignableRole(role: string | null): role is StaffAssignableRole {
  return role != null && (STAFF_ASSIGNABLE_ROLES as readonly string[]).includes(role);
}

function roleLabel(locale: Locale, role: string): string {
  if (role === "admin") return t(locale, "roleOptionAdmin");
  if (role === "planner") return t(locale, "roleOptionPlanner");
  if (role === "team_member") return t(locale, "roleOptionTeamMember");
  return role;
}

function signInBadge(locale: Locale, active: boolean) {
  return (
    <span
      className={
        active
          ? "rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-800"
          : "rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600"
      }
    >
      {active ? t(locale, "orgUserSignInActive") : t(locale, "orgUserSignInInactive")}
    </span>
  );
}

function accountBlock(locale: Locale, id: number | null, role: string | null, isActive: boolean | null): ReactNode {
  if (id == null) {
    return <span className="text-slate-500">{t(locale, "emptyValue")}</span>;
  }
  return (
    <div className="flex flex-col gap-1">
      <span className="font-mono text-slate-900">
        #{id}
        {role != null ? <span className="ml-2 font-sans text-slate-700">{role}</span> : null}
      </span>
      {isActive != null ? signInBadge(locale, isActive) : null}
    </div>
  );
}

export function StaffDirectoryPanel() {
  const { locale } = useLocale();
  const { me, loading } = useSession();
  const router = useRouter();
  const [rows, setRows] = useState<StaffDirectoryRow[]>([]);
  const [loadError, setLoadError] = useState(false);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [busyRowKey, setBusyRowKey] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmModal, setConfirmModal] = useState<StaffActionModal | null>(null);
  const [detailRow, setDetailRow] = useState<StaffDirectoryRow | null>(null);
  const [detailMemberRecord, setDetailMemberRecord] = useState<TeamMemberRecord | null | undefined>(undefined);
  const [createOpen, setCreateOpen] = useState(false);

  const reloadDirectory = useCallback(async (): Promise<StaffDirectoryRow[]> => {
    try {
      const data = await apiFetch<StaffDirectoryRow[]>("/api/v1/organization/staff-directory");
      setRows(data);
      setLoadError(false);
      return data;
    } catch {
      setLoadError(true);
      return [];
    }
  }, []);

  useEffect(() => {
    if (loading) return;
    if (!isUserSession(me) || !me.capabilities.admin) {
      router.replace("/");
      return;
    }
    void reloadDirectory();
  }, [loading, me, router, reloadDirectory]);

  useEffect(() => {
    if (detailRow?.team_member_id == null) {
      setDetailMemberRecord(null);
      return;
    }
    setDetailMemberRecord(undefined);
    let cancelled = false;
    const memberId = detailRow.team_member_id;
    void (async () => {
      try {
        const list = await apiFetch<unknown[]>("/api/v1/team-members");
        const found = list.filter(isTeamMemberRecord).find((d) => d.id === memberId) ?? null;
        if (!cancelled) setDetailMemberRecord(found);
      } catch {
        if (!cancelled) setDetailMemberRecord(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [detailRow]);

  async function copyText(key: string, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedKey(key);
      window.setTimeout(() => setCopiedKey((x) => (x === key ? null : x)), 2000);
    } catch {
      setCopiedKey(null);
    }
  }

  async function reloadDetailMember() {
    const snapshot = detailRow;
    if (snapshot?.team_member_id == null) {
      await reloadDirectory();
      return;
    }
    const memberId = snapshot.team_member_id;
    const list = await apiFetch<unknown[]>("/api/v1/team-members");
    setDetailMemberRecord(list.filter(isTeamMemberRecord).find((d) => d.id === memberId) ?? null);
    const data = await reloadDirectory();
    const next =
      data.find((r) => r.team_member_id === memberId) ??
      data.find((r) => r.email === snapshot.email && r.team_member_id === snapshot.team_member_id);
    if (next) {
      setDetailRow(next);
    }
  }

  async function confirmStaffModal() {
    if (confirmModal == null) return;
    const modal = confirmModal;
    setConfirmModal(null);
    setActionError(null);
    setBusyRowKey(modal.rowKey);
    try {
      if (modal.kind === "role") {
        await apiFetch(`/api/v1/organization/users/${modal.userId}`, {
          method: "PATCH",
          body: JSON.stringify({ role: modal.toRole }),
        });
      } else if (modal.kind === "unlink") {
        const r = modal.row;
        if (r.team_member_id == null) return;
        await apiFetch(`/api/v1/team-members/${r.team_member_id}`, {
          method: "PATCH",
          body: JSON.stringify({ user_id: null }),
        });
      } else {
        await apiFetch(`/api/v1/organization/users/${modal.userId}`, { method: "DELETE" });
      }
      const data = await reloadDirectory();
      setDetailRow((current) => {
        if (current == null) return null;
        const docId = current.team_member_id;
        const email = current.email;
        const next =
          docId != null ? data.find((r) => r.team_member_id === docId) : data.find((r) => r.email === email);
        return next ?? null;
      });
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : t(locale, "apiUnavailable"));
    } finally {
      setBusyRowKey(null);
    }
  }

  if (loading || !isUserSession(me) || !me.capabilities.admin) {
    return null;
  }

  const modalTitleId = "staff-dir-modal-title";
  let modalTitle = "";
  let modalBody: ReactNode = null;
  let confirmClass =
    "inline-flex h-10 items-center justify-center rounded-lg bg-mint px-4 text-sm font-semibold text-ink ring-1 ring-mint/60";
  if (confirmModal?.kind === "role") {
    modalTitle = t(locale, "orgStaffModalRoleTitle");
    modalBody = (
      <p className="text-sm text-slate-600">
        {t(locale, "orgStaffModalRoleBody", {
          from: roleLabel(locale, confirmModal.fromRole),
          to: roleLabel(locale, confirmModal.toRole),
        })}
      </p>
    );
  } else if (confirmModal?.kind === "unlink") {
    modalTitle = t(locale, "orgStaffModalUnlinkTitle");
    modalBody = <p className="text-sm text-slate-600">{t(locale, "orgStaffModalUnlinkBody")}</p>;
    confirmClass =
      "inline-flex h-10 items-center justify-center rounded-lg bg-slate-800 px-4 text-sm font-semibold text-white";
  } else if (confirmModal?.kind === "remove") {
    modalTitle = t(locale, "orgStaffModalRemoveTitle");
    modalBody = <p className="text-sm text-slate-600">{t(locale, "orgStaffModalRemoveBody")}</p>;
    confirmClass =
      "inline-flex h-10 items-center justify-center rounded-lg bg-red-600 px-4 text-sm font-semibold text-white";
  }

  const detailKey = detailRow ? rowKeyOf(detailRow) : null;
  const detailBusy = detailKey != null && busyRowKey === detailKey;
  const myId = isUserSession(me) ? me.id : 0;

  function renderAccessControls(r: StaffDirectoryRow, rowKey: string) {
    const copyUserKey = `u:${rowKey}`;
    const copyDocKey = `d:${rowKey}`;
    const copyLinkedKey = `l:${rowKey}`;
    const showLinkedUserCopy =
      r.linked_user_id != null && (r.user_id == null || r.user_id !== r.linked_user_id);
    const canUnlinkTeamMember = r.team_member_id != null && r.linked_user_id != null;
    const canRemoveEmailUser = r.user_id != null && r.user_id !== myId;
    const canRemoveLinkedOnlyUser =
      r.linked_user_id != null &&
      r.linked_user_id !== myId &&
      (r.user_id == null || r.user_id !== r.linked_user_id);
    const emailRoleSelectValue =
      r.user_role != null && isStaffAssignableRole(r.user_role) ? r.user_role : OTHER_ROLE_VALUE;
    const linkedRoleSelectValue =
      r.linked_user_role != null && isStaffAssignableRole(r.linked_user_role)
        ? r.linked_user_role
        : OTHER_ROLE_VALUE;

    return (
      <div className="grid gap-4">
        <div>
          <h3 className="text-sm font-semibold text-slate-800">{t(locale, "orgStaffDetailLoginSection")}</h3>
          <div className="mt-2 flex flex-wrap gap-2">
            {r.user_id != null ? (
              <button
                type="button"
                disabled={detailBusy || confirmModal != null}
                className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs font-medium text-slate-700 shadow-sm disabled:opacity-50"
                onClick={() => void copyText(copyUserKey, String(r.user_id))}
              >
                {copiedKey === copyUserKey ? t(locale, "orgUserCopied") : t(locale, "orgUserCopyId")}
              </button>
            ) : null}
            {showLinkedUserCopy ? (
              <button
                type="button"
                disabled={detailBusy || confirmModal != null}
                className="rounded-lg border border-amber-200 bg-amber-50 px-2 py-1 text-xs font-medium text-amber-900 shadow-sm disabled:opacity-50"
                onClick={() => void copyText(copyLinkedKey, String(r.linked_user_id))}
              >
                {copiedKey === copyLinkedKey ? t(locale, "orgUserCopied") : t(locale, "orgStaffCopyLinkedLoginOnProfile")}
              </button>
            ) : null}
            {r.team_member_id != null ? (
              <button
                type="button"
                disabled={detailBusy || confirmModal != null}
                className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs font-medium text-slate-700 shadow-sm disabled:opacity-50"
                onClick={() => void copyText(copyDocKey, String(r.team_member_id))}
              >
                {copiedKey === copyDocKey ? t(locale, "orgUserCopied") : t(locale, "orgTeamMemberCopyId")}
              </button>
            ) : null}
          </div>
          <div className="mt-3 text-sm text-slate-700">{accountBlock(locale, r.user_id, r.user_role, r.user_is_active)}</div>
          {r.user_id != null && r.user_role != null ? (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="text-xs text-slate-500">{t(locale, "orgStaffRoleEmailAccount")}</span>
              <select
                className="max-w-full rounded-md border border-slate-200 bg-white py-1.5 pl-2 pr-8 text-sm text-slate-800 shadow-sm"
                disabled={detailBusy || confirmModal != null}
                value={emailRoleSelectValue}
                aria-label={t(locale, "orgStaffRoleEmailAccount")}
                onChange={(e) => {
                  const raw = e.target.value;
                  if (raw === OTHER_ROLE_VALUE) return;
                  const v = raw as StaffAssignableRole;
                  if (v === r.user_role) return;
                  setConfirmModal({
                    kind: "role",
                    rowKey,
                    userId: r.user_id!,
                    fromRole: r.user_role!,
                    toRole: v,
                  });
                }}
              >
                {!isStaffAssignableRole(r.user_role) ? (
                  <option value={OTHER_ROLE_VALUE} disabled>
                    {r.user_role}
                  </option>
                ) : null}
                <option value="admin">{t(locale, "roleOptionAdmin")}</option>
                <option value="planner">{t(locale, "roleOptionPlanner")}</option>
                <option value="team_member">{t(locale, "roleOptionTeamMember")}</option>
              </select>
            </div>
          ) : null}
        </div>
        {r.linked_user_id != null && r.linked_user_id !== r.user_id && r.linked_user_role != null ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50/40 p-3">
            <h3 className="text-sm font-semibold text-amber-950">{t(locale, "orgStaffDetailLinkedLoginSection")}</h3>
            <div className="mt-2 text-sm text-slate-800">
              {accountBlock(locale, r.linked_user_id, r.linked_user_role, r.linked_user_is_active)}
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="text-xs text-slate-600">{t(locale, "orgStaffRoleLinkedAccount")}</span>
              <select
                className="max-w-full rounded-md border border-amber-200 bg-white py-1.5 pl-2 pr-8 text-sm text-slate-800 shadow-sm"
                disabled={detailBusy || confirmModal != null}
                value={linkedRoleSelectValue}
                aria-label={t(locale, "orgStaffRoleLinkedAccount")}
                onChange={(e) => {
                  const raw = e.target.value;
                  if (raw === OTHER_ROLE_VALUE) return;
                  const v = raw as StaffAssignableRole;
                  if (v === r.linked_user_role) return;
                  setConfirmModal({
                    kind: "role",
                    rowKey,
                    userId: r.linked_user_id!,
                    fromRole: r.linked_user_role!,
                    toRole: v,
                  });
                }}
              >
                {!isStaffAssignableRole(r.linked_user_role) ? (
                  <option value={OTHER_ROLE_VALUE} disabled>
                    {r.linked_user_role}
                  </option>
                ) : null}
                <option value="admin">{t(locale, "roleOptionAdmin")}</option>
                <option value="planner">{t(locale, "roleOptionPlanner")}</option>
                <option value="team_member">{t(locale, "roleOptionTeamMember")}</option>
              </select>
            </div>
          </div>
        ) : null}
        <div className="flex flex-wrap gap-2 border-t border-slate-200 pt-3">
          {canUnlinkTeamMember ? (
            <button
              type="button"
              disabled={detailBusy || confirmModal != null}
              className="rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-800 shadow-sm disabled:opacity-50"
              onClick={() => setConfirmModal({ kind: "unlink", rowKey, row: r })}
            >
              {t(locale, "orgStaffUnlinkLogin")}
            </button>
          ) : null}
          {canRemoveEmailUser ? (
            <button
              type="button"
              disabled={detailBusy || confirmModal != null}
              className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-800 shadow-sm disabled:opacity-50"
              onClick={() => setConfirmModal({ kind: "remove", rowKey, userId: r.user_id! })}
            >
              {t(locale, "orgStaffRemoveUser")}
            </button>
          ) : r.user_id === myId ? (
            <span className="text-xs text-slate-400">{t(locale, "orgStaffRemoveSelfHint")}</span>
          ) : null}
          {canRemoveLinkedOnlyUser ? (
            <button
              type="button"
              disabled={detailBusy || confirmModal != null}
              className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-800 shadow-sm disabled:opacity-50"
              onClick={() => setConfirmModal({ kind: "remove", rowKey, userId: r.linked_user_id! })}
            >
              {t(locale, "orgStaffRemoveLinkedUser")}
            </button>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div className="grid min-w-0 gap-5">
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <ContactRound className="shrink-0 text-emerald-700" aria-hidden />
          <h1 className="min-w-0 truncate text-2xl font-semibold text-ink">{t(locale, "teamMembers")}</h1>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void reloadDirectory()}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 shadow-sm"
          >
            <RefreshCw size={16} />
            {t(locale, "refresh")}
          </button>
          <button
            type="button"
            onClick={() => {
              setDetailRow(null);
              setCreateOpen(true);
            }}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white"
          >
            <Plus size={16} />
            {t(locale, "addTeamMember")}
          </button>
        </div>
      </div>
      <p className="max-w-3xl text-sm text-slate-600">{t(locale, "orgUserAccountsHelp")}</p>
      <p className="max-w-3xl text-xs text-slate-500">{t(locale, "orgStaffClickRowHint")}</p>
      {loadError ? <p className="text-sm text-red-600">{t(locale, "apiUnavailable")}</p> : null}
      {actionError ? <p className="text-sm text-red-600">{actionError}</p> : null}
      <Card>
        <div className={`${dataTableScrollShellClassName} rounded-lg border border-slate-200`}>
          <table className="w-full min-w-[960px] border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs font-semibold uppercase tracking-wide text-slate-500">
                <th className="sticky top-0 z-10 bg-white py-2 pr-3 shadow-[0_1px_0_0_rgb(226_232_240)]">{t(locale, "orgStaffColumnEmail")}</th>
                <th className="sticky top-0 z-10 bg-white py-2 pr-3 shadow-[0_1px_0_0_rgb(226_232_240)]">{t(locale, "orgStaffColumnLink")}</th>
                <th className="sticky top-0 z-10 bg-white py-2 pr-3 shadow-[0_1px_0_0_rgb(226_232_240)]">{t(locale, "orgStaffColumnTeamProfile")}</th>
                <th className="sticky top-0 z-10 bg-white py-2 pr-3 shadow-[0_1px_0_0_rgb(226_232_240)]">{t(locale, "orgStaffColumnLogin")}</th>
                <th className="sticky top-0 z-10 bg-white py-2 pr-3 shadow-[0_1px_0_0_rgb(226_232_240)]">{t(locale, "orgStaffColumnUserIdOnTeamProfile")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const rk = rowKeyOf(r);
                const warn = r.link_status === "linked_wrong_user" || r.link_status === "linked_foreign_user";
                const rowBusy = busyRowKey === rk;
                return (
                  <tr
                    key={rk}
                    role="button"
                    tabIndex={0}
                    onClick={() => setDetailRow(r)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setDetailRow(r);
                      }
                    }}
                    className={`cursor-pointer border-b border-slate-100 last:border-0 hover:bg-slate-50/90 focus-visible:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-emerald-500 ${warn ? "bg-amber-50/80" : ""} ${rowBusy ? "pointer-events-none opacity-60" : ""}`}
                  >
                    <td className="max-w-[220px] truncate py-3 pr-3 font-medium text-slate-900" title={r.email}>
                      {r.email}
                    </td>
                    <td className="max-w-[200px] py-3 pr-3 text-slate-700">{t(locale, linkStatusTranslationKey(r.link_status))}</td>
                    <td className="max-w-[200px] py-3 pr-3 text-slate-800" title={r.team_member_label ?? ""}>
                      {r.team_member_id == null ? (
                        <span className="text-slate-500">{t(locale, "emptyValue")}</span>
                      ) : (
                        <>
                          <span className="truncate">{r.team_member_label ?? t(locale, "emptyValue")}</span>
                          <span className="ml-1 font-mono text-xs text-slate-500">#{r.team_member_id}</span>
                          {r.team_member_is_active === false ? (
                            <span className="ml-1 rounded bg-slate-200 px-1.5 py-0.5 text-xs text-slate-700">
                              {t(locale, "orgUserSignInInactive")}
                            </span>
                          ) : null}
                        </>
                      )}
                    </td>
                    <td className="py-3 pr-3 text-slate-800">{accountBlock(locale, r.user_id, r.user_role, r.user_is_active)}</td>
                    <td className="py-3 pr-3 text-slate-800">
                      {accountBlock(locale, r.linked_user_id, r.linked_user_role, r.linked_user_is_active)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {createOpen ? (
        <TeamMemberCreateModal
          onClose={() => setCreateOpen(false)}
          onCreated={async () => {
            await reloadDirectory();
          }}
        />
      ) : null}

      {detailRow ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 px-3 py-6 backdrop-blur-sm"
          role="presentation"
          tabIndex={-1}
          onClick={() => setDetailRow(null)}
          onKeyDown={(e) => {
            if (e.key === "Escape") setDetailRow(null);
          }}
        >
          <div
            className="flex max-h-[92vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl bg-white shadow-soft ring-1 ring-slate-200"
            role="dialog"
            aria-modal="true"
            aria-labelledby="staff-detail-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex shrink-0 items-start justify-between gap-3 border-b border-slate-100 px-4 py-3 sm:px-5">
              <div className="min-w-0">
                <h2 id="staff-detail-title" className="truncate text-lg font-semibold text-ink">
                  {detailRow.email}
                </h2>
                <p className="mt-1 text-xs text-slate-500">{t(locale, linkStatusTranslationKey(detailRow.link_status))}</p>
              </div>
              <button
                type="button"
                aria-label={t(locale, "close")}
                className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600"
                onClick={() => setDetailRow(null)}
              >
                <X size={17} />
              </button>
            </div>
            <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-4 sm:px-5">
              <section>
                <h3 className="text-sm font-semibold text-slate-800">{t(locale, "orgStaffColumnTeamProfile")}</h3>
                {detailRow.team_member_id == null ? (
                  <p className="mt-2 text-sm text-slate-600">{t(locale, "orgStaffNoTeamProfileRow")}</p>
                ) : detailMemberRecord === undefined ? (
                  <p className="mt-2 text-sm text-slate-500">{t(locale, "orgStaffDetailLoadingTeamMember")}</p>
                ) : detailMemberRecord == null ? (
                  <p className="mt-2 text-sm text-red-600">{t(locale, "orgStaffDetailTeamMemberMissing")}</p>
                ) : (
                  <div className="mt-2">
                    <TeamMemberEditorModal
                      member={detailMemberRecord}
                      embedded
                      onChanged={reloadDetailMember}
                      onClose={() => setDetailRow(null)}
                    />
                  </div>
                )}
              </section>
              <section className="rounded-lg border border-slate-200 bg-slate-50/50 p-4">
                {renderAccessControls(detailRow, rowKeyOf(detailRow))}
              </section>
            </div>
          </div>
        </div>
      ) : null}

      {confirmModal ? (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-ink/30 px-4 py-6 backdrop-blur-sm"
          role="presentation"
          tabIndex={-1}
          onClick={() => setConfirmModal(null)}
          onKeyDown={(e) => {
            if (e.key === "Escape") setConfirmModal(null);
          }}
        >
          <div
            className="w-full max-w-md rounded-xl bg-white p-5 shadow-soft ring-1 ring-slate-200"
            role="dialog"
            aria-modal="true"
            aria-labelledby={modalTitleId}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 id={modalTitleId} className="text-lg font-semibold text-ink">
                {modalTitle}
              </h2>
              <button
                aria-label={t(locale, "close")}
                className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600"
                onClick={() => setConfirmModal(null)}
                type="button"
              >
                <X size={17} />
              </button>
            </div>
            {modalBody}
            <div className="mt-6 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700"
                onClick={() => setConfirmModal(null)}
              >
                {t(locale, "orgStaffModalCancel")}
              </button>
              <button type="button" className={confirmClass} onClick={() => void confirmStaffModal()}>
                {t(locale, "confirm")}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
