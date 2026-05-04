"use client";

import { FormEvent, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Bot, Building2, Languages, Trash2 } from "lucide-react";
import { useLocale, useSession, type MeUser } from "@/components/LocaleProvider";
import { Card, Field, inputClass } from "@/components/Card";
import { OrganizationPendingInvitesCard } from "@/components/OrganizationPendingInvitesCard";
import { ApiError, apiFetch } from "@/lib/api";
import {
  membershipDefaultPath,
  membershipRoleLabel,
  pathnameCompatibleWithMembership,
} from "@/lib/membershipRouting";
import { t } from "@/lib/i18n";

type LookupResult = { slug: string; name: string };

function messageFromApiError(locale: "de" | "en", err: unknown): string {
  if (err instanceof ApiError && typeof err.detail === "string") {
    const d = err.detail;
    if (d.includes("only administrator") || d.includes("Cannot delete the only")) {
      return t(locale, "soleAdminCannotDelete");
    }
    if (d.includes("Invalid password")) {
      return t(locale, "loginFailed");
    }
    return d;
  }
  return t(locale, "deleteAccountError");
}

function SettingsContent() {
  const { locale, setLocale } = useLocale();
  const { me, refreshMe } = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const [deleteMsg, setDeleteMsg] = useState("");
  const [joinMsg, setJoinMsg] = useState("");
  const [joinBusy, setJoinBusy] = useState(false);
  const [joinLookup, setJoinLookup] = useState<LookupResult | null | undefined>(undefined);
  const [switchBusySlug, setSwitchBusySlug] = useState<string | null>(null);

  async function runJoinLookup(slug: string) {
    const s = slug.trim();
    if (!s) {
      setJoinLookup(undefined);
      return;
    }
    try {
      const res = await apiFetch<LookupResult>(
        `/api/v1/organizations/lookup?slug=${encodeURIComponent(s)}`
      );
      setJoinLookup(res);
    } catch {
      setJoinLookup(null);
    }
  }

  async function switchToOrganization(slug: string) {
    if (!me || slug === me.organization.slug) return;
    setSwitchBusySlug(slug);
    try {
      const updated = await apiFetch<MeUser>("/api/v1/auth/me/active-organization", {
        method: "POST",
        body: JSON.stringify({ organization_slug: slug }),
      });
      await refreshMe();
      const next = membershipDefaultPath(updated);
      if (!pathnameCompatibleWithMembership(pathname, updated)) {
        router.push(next);
      }
      router.refresh();
    } catch {
      return;
    } finally {
      setSwitchBusySlug(null);
    }
  }

  async function submitJoinAnother(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!me) return;
    setJoinMsg("");
    setJoinBusy(true);
    const form = new FormData(event.currentTarget);
    const organization_slug = String(form.get("join_organization_slug") ?? "")
      .trim()
      .toLowerCase();
    try {
      const user = await apiFetch<MeUser>("/api/v1/auth/me/add-organization-membership", {
        method: "POST",
        body: JSON.stringify({
          organization_slug,
          password: String(form.get("join_password") ?? ""),
          first_name: String(form.get("join_first_name") ?? "").trim(),
          last_name: String(form.get("join_last_name") ?? "").trim(),
          message: (() => {
            const m = String(form.get("join_message") ?? "").trim();
            return m.length ? m : null;
          })(),
        }),
      });
      await refreshMe();
      router.push(membershipDefaultPath(user));
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError && typeof err.detail === "string") {
        setJoinMsg(err.detail);
      } else {
        setJoinMsg(t(locale, "settingsJoinAnotherError"));
      }
    } finally {
      setJoinBusy(false);
    }
  }

  async function deleteAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setDeleteMsg("");
    const form = new FormData(event.currentTarget);
    const password = String(form.get("delete_password") ?? "");
    try {
      await apiFetch("/api/v1/auth/delete-account", {
        method: "POST",
        body: JSON.stringify({ password })
      });
      await refreshMe();
      router.push("/login");
      router.refresh();
    } catch (err) {
      setDeleteMsg(messageFromApiError(locale, err));
    }
  }

  return (
    <div className="grid gap-5 md:grid-cols-2">
      <OrganizationPendingInvitesCard />
      <Card>
        <div className="flex items-start gap-4">
          <Languages className="text-emerald-700" aria-hidden />
          <div>
            <h1 className="text-xl font-semibold text-ink">{t(locale, "language")}</h1>
            <button
              className="mt-4 h-11 rounded-lg bg-ink px-4 text-sm font-semibold text-white"
              onClick={() => setLocale(locale === "de" ? "en" : "de")}
            >
              {locale.toUpperCase()}
            </button>
          </div>
        </div>
      </Card>
      <Card>
        <div className="flex items-start gap-4">
          <Bot className="text-coral" aria-hidden />
          <div>
            <h2 className="text-xl font-semibold text-ink">{t(locale, "mcpStatus")}</h2>
            <p className="mt-2 text-sm text-slate-600">{t(locale, "mcpText")}</p>
          </div>
        </div>
      </Card>
      {me ? (
        <div className="md:col-span-2">
          <Card>
            <div className="flex items-start gap-4">
              <Building2 className="shrink-0 text-emerald-700" aria-hidden />
              <div className="min-w-0 flex-1 space-y-4">
                <div>
                  <h2 className="text-xl font-semibold text-ink">{t(locale, "settingsMembershipsTitle")}</h2>
                  <p className="mt-2 text-sm text-slate-600">{t(locale, "settingsMembershipsHelp")}</p>
                </div>
                <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-slate-50/60">
                  {[...me.memberships]
                    .sort((a, b) => a.organization.slug.localeCompare(b.organization.slug))
                    .map((m) => {
                      const active = m.organization.id === me.organization_id;
                      return (
                        <li key={m.membership_id} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                          <div className="min-w-0">
                            <p className="truncate font-medium text-ink">
                              {m.organization.name.trim() ? m.organization.name : m.organization.slug}
                            </p>
                            <p className="font-mono text-xs text-slate-600">{m.organization.slug}</p>
                            <p className="text-xs text-slate-600">{membershipRoleLabel(locale, m.role)}</p>
                            {m.team_member_id != null ? (
                              <p className="text-xs text-slate-500">{t(locale, "membershipLinkedTeamProfile")}</p>
                            ) : null}
                            <p className="text-xs text-slate-500">
                              {t(locale, "organizationIdLabel")}: {m.organization.id}
                            </p>
                          </div>
                          <div className="flex shrink-0 flex-col items-stretch gap-2 sm:items-end">
                            {active ? (
                              <span className="inline-flex rounded-lg bg-emerald-100 px-3 py-1.5 text-xs font-semibold text-emerald-900">
                                {t(locale, "organizationSwitcherCurrent")}
                              </span>
                            ) : (
                              <button
                                type="button"
                                aria-busy={switchBusySlug === m.organization.slug}
                                disabled={Boolean(switchBusySlug)}
                                onClick={() => void switchToOrganization(m.organization.slug)}
                                className="h-10 rounded-lg bg-ink px-4 text-sm font-semibold text-white disabled:opacity-50"
                              >
                                {t(locale, "settingsMembershipSwitch")}
                              </button>
                            )}
                          </div>
                        </li>
                      );
                    })}
                </ul>
                <div className="border-t border-slate-100 pt-4">
                  <h3 className="text-lg font-semibold text-ink">{t(locale, "settingsJoinAnotherTitle")}</h3>
                  <p className="mt-1 text-sm text-slate-600">{t(locale, "settingsJoinAnotherIntro")}</p>
                  <form className="mt-4 grid max-w-md gap-3" onSubmit={(e) => void submitJoinAnother(e)}>
                    <Field label={t(locale, "organizationSlugLabel")}>
                      <div className="flex gap-2">
                        <input
                          className={`${inputClass} min-w-0 flex-1`}
                          id="settings-join-org-slug"
                          name="join_organization_slug"
                          required
                          minLength={1}
                          maxLength={64}
                          autoComplete="off"
                        />
                        <button
                          type="button"
                          className="h-11 shrink-0 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700"
                          onClick={() => {
                            const el = document.getElementById("settings-join-org-slug") as HTMLInputElement | null;
                            void runJoinLookup(el?.value ?? "");
                          }}
                        >
                          {t(locale, "lookupOrganization")}
                        </button>
                      </div>
                    </Field>
                    {joinLookup === null ? <p className="text-sm text-red-600">{t(locale, "lookupFailed")}</p> : null}
                    {joinLookup ? (
                      <p className="text-sm text-slate-600">
                        {t(locale, "organizationFoundName")}:{" "}
                        <span className="font-medium text-ink">{joinLookup.name}</span>
                      </p>
                    ) : null}
                    <Field label={t(locale, "firstName")}>
                      <input className={inputClass} name="join_first_name" required minLength={1} autoComplete="given-name" />
                    </Field>
                    <Field label={t(locale, "lastName")}>
                      <input className={inputClass} name="join_last_name" required minLength={1} autoComplete="family-name" />
                    </Field>
                    <Field label={t(locale, "password")}>
                      <input
                        className={inputClass}
                        name="join_password"
                        type="password"
                        required
                        autoComplete="current-password"
                      />
                    </Field>
                    <Field label={t(locale, "joinMessageOptional")}>
                      <textarea className={`${inputClass} min-h-[88px] py-2`} name="join_message" maxLength={2000} />
                    </Field>
                    <button
                      type="submit"
                      disabled={joinBusy}
                      className="h-11 rounded-lg bg-emerald-700 px-4 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-50"
                    >
                      {t(locale, "settingsJoinAnotherSubmit")}
                    </button>
                    {joinMsg ? <p className="text-sm text-red-600">{joinMsg}</p> : null}
                  </form>
                </div>
              </div>
            </div>
          </Card>
        </div>
      ) : null}
      {me ? (
        <div className="md:col-span-2">
          <Card>
            <div className="flex items-start gap-4">
              <Trash2 className="shrink-0 text-red-600" aria-hidden />
              <div className="min-w-0 flex-1">
                <h2 className="text-xl font-semibold text-red-900">{t(locale, "deleteAccountTitle")}</h2>
                <p className="mt-2 text-sm text-slate-600">{t(locale, "deleteAccountWarning")}</p>
                <form className="mt-4 grid max-w-md gap-3" onSubmit={(e) => void deleteAccount(e)}>
                  <Field label={t(locale, "deleteAccountPasswordLabel")}>
                    <input
                      className={inputClass}
                      name="delete_password"
                      type="password"
                      required
                      autoComplete="current-password"
                    />
                  </Field>
                  <button
                    type="submit"
                    className="h-11 rounded-lg bg-red-700 px-4 text-sm font-semibold text-white hover:bg-red-800"
                  >
                    {t(locale, "deleteAccountButton")}
                  </button>
                  {deleteMsg ? <p className="text-sm text-red-600">{deleteMsg}</p> : null}
                </form>
              </div>
            </div>
          </Card>
        </div>
      ) : null}
    </div>
  );
}

export default function SettingsPage() {
  return <SettingsContent />;
}
