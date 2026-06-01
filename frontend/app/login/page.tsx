"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogIn } from "lucide-react";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale, useSession, type SessionMe } from "@/components/LocaleProvider";
import { apiFetch } from "@/lib/api";
import { membershipDefaultPath } from "@/lib/membershipRouting";
import { t } from "@/lib/i18n";

function LoginContent() {
  const { locale } = useLocale();
  const { refreshMe } = useSession();
  const router = useRouter();
  const [message, setMessage] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") ?? "")
      .trim()
      .toLowerCase();
    const password = String(form.get("password") ?? "");
    try {
      const session = await apiFetch<SessionMe>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email,
          password,
        }),
      });
      await refreshMe();
      router.push(membershipDefaultPath(session));
      router.refresh();
    } catch {
      setMessage(t(locale, "loginFailed"));
    }
  }

  return (
    <Card>
      <form className="grid max-w-md gap-4" onSubmit={submit}>
        <h1 className="text-2xl font-semibold text-ink">{t(locale, "adminLogin")}</h1>
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
        <Link href="/register" className="text-sm font-medium text-emerald-800 underline">
          {t(locale, "registerPageTitle")}
        </Link>
        <p className="text-xs text-slate-500">{t(locale, "loginForgotPasswordHint")}</p>
        <p className="text-xs text-slate-500">{t(locale, "loginRemovedAccountHint")}</p>
        {message ? <p className="text-sm text-slate-600">{message}</p> : null}
      </form>
    </Card>
  );
}

export default function LoginPage() {
  return <LoginContent />;
}
