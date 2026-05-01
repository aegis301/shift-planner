"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Bot, Building2, Languages, Trash2 } from "lucide-react";
import { useLocale, useSession } from "@/components/LocaleProvider";
import { Card, Field, inputClass } from "@/components/Card";
import { ApiError, apiFetch } from "@/lib/api";
import { t } from "@/lib/i18n";

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
  const [deleteMsg, setDeleteMsg] = useState("");

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
              <Building2 className="text-emerald-700" aria-hidden />
              <div className="min-w-0 flex-1">
                <h2 className="text-xl font-semibold text-ink">{t(locale, "organization")}</h2>
                <p className="mt-2 truncate text-sm text-slate-700">
                  {me.organization.name.trim() ? me.organization.name : t(locale, "emptyValue")}
                </p>
                <p className="mt-1 font-mono text-xs text-slate-600">{me.organization.slug}</p>
                <p className="mt-1 text-xs text-slate-500">
                  {t(locale, "organizationIdLabel")}: {me.organization.id}
                </p>
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
