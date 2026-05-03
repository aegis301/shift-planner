"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogIn } from "lucide-react";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale, useSession, type MeUser } from "@/components/LocaleProvider";
import { apiFetch } from "@/lib/api";
import { t } from "@/lib/i18n";

type LookupResult = { slug: string; name: string };

export default function RegisterJoinOrganizationPage() {
  const { locale } = useLocale();
  const { refreshMe } = useSession();
  const router = useRouter();
  const [message, setMessage] = useState("");
  const [lookup, setLookup] = useState<LookupResult | null | undefined>(undefined);

  async function runLookup(slug: string) {
    const s = slug.trim();
    if (!s) {
      setLookup(undefined);
      return;
    }
    try {
      const res = await apiFetch<LookupResult>(
        `/api/v1/organizations/lookup?slug=${encodeURIComponent(s)}`
      );
      setLookup(res);
    } catch {
      setLookup(null);
    }
  }

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
      await apiFetch<MeUser>("/api/v1/auth/register/join-organization", {
        method: "POST",
        body: JSON.stringify({
          organization_slug: String(form.get("organization_slug") ?? "")
            .trim()
            .toLowerCase(),
          email: form.get("email"),
          password,
          password_confirm: passwordConfirm,
          first_name: form.get("first_name"),
          last_name: form.get("last_name"),
          message: form.get("message") || null,
          locale: form.get("locale") || locale
        })
      });
      await refreshMe();
      router.push("/pending-onboarding");
      router.refresh();
    } catch {
      setMessage(t(locale, "registrationFailed"));
    }
  }

  return (
    <Card>
      <form className="grid max-w-md gap-4" onSubmit={submit}>
        <div className="flex items-center gap-2">
          <LogIn className="text-emerald-700" aria-hidden />
          <h1 className="text-2xl font-semibold text-ink">{t(locale, "registerJoinTitle")}</h1>
        </div>
        <p className="text-sm text-slate-600">{t(locale, "registerJoinIntro")}</p>
        <Field label={t(locale, "organizationSlugLabel")}>
          <div className="flex gap-2">
            <input
              className={`${inputClass} min-w-0 flex-1`}
              name="organization_slug"
              id="org-slug"
              required
              minLength={1}
              maxLength={64}
            />
            <button
              type="button"
              className="h-11 shrink-0 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700"
              onClick={() => {
                const el = document.getElementById("org-slug") as HTMLInputElement | null;
                void runLookup(el?.value ?? "");
              }}
            >
              {t(locale, "lookupOrganization")}
            </button>
          </div>
        </Field>
        {lookup === null ? <p className="text-sm text-red-600">{t(locale, "lookupFailed")}</p> : null}
        {lookup ? (
          <p className="text-sm text-slate-600">
            {t(locale, "organizationFoundName")}: <span className="font-medium text-ink">{lookup.name}</span>
          </p>
        ) : null}
        <Field label={t(locale, "firstName")}>
          <input className={inputClass} name="first_name" required minLength={1} />
        </Field>
        <Field label={t(locale, "lastName")}>
          <input className={inputClass} name="last_name" required minLength={1} />
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
        <Field label={t(locale, "joinMessageOptional")}>
          <textarea className={`${inputClass} min-h-[88px] py-2`} name="message" maxLength={2000} />
        </Field>
        <input type="hidden" name="locale" value={locale} />
        <button
          type="submit"
          className="inline-flex h-11 items-center justify-center rounded-lg bg-ink px-4 text-sm font-semibold text-white"
        >
          {t(locale, "joinOrganizationSubmit")}
        </button>
        <Link href="/login" className="text-sm font-medium text-emerald-800 underline">
          {t(locale, "registerGoLogin")}
        </Link>
        {message ? <p className="text-sm text-red-600">{message}</p> : null}
      </form>
    </Card>
  );
}
