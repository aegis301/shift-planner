"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { UserPlus } from "lucide-react";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale, useSession, type MeUser } from "@/components/LocaleProvider";
import { apiFetch } from "@/lib/api";
import { t } from "@/lib/i18n";

export default function RegisterCreateOrganizationPage() {
  const { locale } = useLocale();
  const { refreshMe } = useSession();
  const router = useRouter();
  const [message, setMessage] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setMessage("");
    const password = String(form.get("password") ?? "");
    const passwordConfirm = String(form.get("password_confirm") ?? "");
    if (password !== passwordConfirm) {
      setMessage(t(locale, "registerPasswordMismatch"));
      return;
    }
    try {
      const slug = String(form.get("organization_slug") ?? "")
        .trim()
        .toLowerCase();
      const user = await apiFetch<MeUser>("/api/v1/auth/register/create-organization", {
        method: "POST",
        body: JSON.stringify({
          organization_name: form.get("organization_name"),
          organization_slug: slug,
          email: form.get("email"),
          password,
          password_confirm: passwordConfirm,
          locale: form.get("locale") || locale
        })
      });
      await refreshMe();
      const path = user.capabilities.admin ? "/organization/team" : "/";
      router.push(path);
      router.refresh();
    } catch {
      setMessage(t(locale, "registrationFailed"));
    }
  }

  return (
    <Card>
      <form className="grid max-w-md gap-4" onSubmit={submit}>
        <div className="flex items-center gap-2">
          <UserPlus className="text-emerald-700" aria-hidden />
          <h1 className="text-2xl font-semibold text-ink">{t(locale, "registerCreateTitle")}</h1>
        </div>
        <p className="text-sm text-slate-600">{t(locale, "registerCreateIntro")}</p>
        <Field label={t(locale, "organizationNameField")}>
          <input className={inputClass} name="organization_name" required minLength={1} />
        </Field>
        <Field label={t(locale, "organizationSlugField")}>
          <input
            className={inputClass}
            name="organization_slug"
            required
            minLength={3}
            maxLength={64}
          />
        </Field>
        <Field label={t(locale, "email")}>
          <input className={inputClass} name="email" type="email" required />
        </Field>
        <Field label={t(locale, "password")}>
          <input className={inputClass} name="password" type="password" required minLength={8} autoComplete="new-password" />
        </Field>
        <Field label={t(locale, "registerPasswordConfirmLabel")}>
          <input
            className={inputClass}
            name="password_confirm"
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
          />
        </Field>
        <input type="hidden" name="locale" value={locale} />
        <button
          type="submit"
          className="inline-flex h-11 items-center justify-center rounded-lg bg-ink px-4 text-sm font-semibold text-white"
        >
          {t(locale, "createOrganizationSubmit")}
        </button>
        <Link href="/login" className="text-sm font-medium text-emerald-800 underline">
          {t(locale, "registerGoLogin")}
        </Link>
        {message ? <p className="text-sm text-red-600">{message}</p> : null}
      </form>
    </Card>
  );
}
