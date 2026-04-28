"use client";

import { FormEvent, useState } from "react";
import { LogIn } from "lucide-react";
import { Card, Field, inputClass } from "@/components/Card";
import { LocaleShell, useLocale } from "@/components/LocaleProvider";
import { apiFetch } from "@/lib/api";
import { t } from "@/lib/i18n";

function LoginContent() {
  const { locale } = useLocale();
  const [message, setMessage] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await apiFetch("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: form.get("email"), password: form.get("password") })
      });
      setMessage(t(locale, "signedIn"));
    } catch {
      setMessage(t(locale, "loginFailed"));
    }
  }

  return (
    <Card>
      <form className="grid max-w-md gap-4" onSubmit={submit}>
        <h1 className="text-2xl font-semibold text-ink">{t(locale, "adminLogin")}</h1>
        <Field label={t(locale, "email")}>
          <input className={inputClass} name="email" type="email" required />
        </Field>
        <Field label={t(locale, "password")}>
          <input className={inputClass} name="password" type="password" required />
        </Field>
        <button className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white">
          <LogIn aria-hidden size={17} />
          {t(locale, "login")}
        </button>
        {message ? <p className="text-sm text-slate-600">{message}</p> : null}
      </form>
    </Card>
  );
}

export default function LoginPage() {
  return (
    <LocaleShell>
      <LoginContent />
    </LocaleShell>
  );
}

