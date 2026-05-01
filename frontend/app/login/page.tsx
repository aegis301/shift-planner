"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogIn } from "lucide-react";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale, useSession, type MeUser } from "@/components/LocaleProvider";
import { apiFetch } from "@/lib/api";
import { t } from "@/lib/i18n";

function LoginContent() {
  const { locale } = useLocale();
  const { refreshMe } = useSession();
  const router = useRouter();
  const [message, setMessage] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const organization_slug = String(form.get("organization_slug") ?? "")
      .trim()
      .toLowerCase();
    try {
      const user = await apiFetch<MeUser>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: form.get("email"),
          password: form.get("password"),
          organization_slug
        })
      });
      await refreshMe();
      let path = "/";
      if (user.role === "applicant") {
        path = "/pending-onboarding";
      } else if (user.capabilities.planning) {
        path = "/planning";
      } else if (user.capabilities.doctor_portal) {
        path = "/my-planning";
      }
      router.push(path);
      router.refresh();
    } catch {
      setMessage(t(locale, "loginFailed"));
    }
  }

  return (
    <Card>
      <form className="grid max-w-md gap-4" onSubmit={submit}>
        <h1 className="text-2xl font-semibold text-ink">{t(locale, "adminLogin")}</h1>
        <Field label={t(locale, "organizationSlugLabel")}>
          <input
            className={inputClass}
            name="organization_slug"
            required
            minLength={1}
            maxLength={64}
            defaultValue="default"
            autoComplete="organization"
          />
        </Field>
        <p className="text-xs text-slate-500">{t(locale, "organizationSlugHint")}</p>
        <Field label={t(locale, "email")}>
          <input className={inputClass} name="email" type="email" required autoComplete="username" />
        </Field>
        <Field label={t(locale, "password")}>
          <input className={inputClass} name="password" type="password" required autoComplete="current-password" />
        </Field>
        <button
          type="submit"
          className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white"
        >
          <LogIn aria-hidden size={17} />
          {t(locale, "login")}
        </button>
        <div className="flex flex-wrap gap-3 text-sm">
          <Link href="/register/create" className="font-medium text-emerald-800 underline">
            {t(locale, "registerCreateTitle")}
          </Link>
          <Link href="/register/join" className="font-medium text-emerald-800 underline">
            {t(locale, "registerJoinTitle")}
          </Link>
        </div>
        {message ? <p className="text-sm text-slate-600">{message}</p> : null}
      </form>
    </Card>
  );
}

export default function LoginPage() {
  return <LoginContent />;
}
