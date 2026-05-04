"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogIn } from "lucide-react";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale, useSession, type MeUser } from "@/components/LocaleProvider";
import { ApiError, apiFetch } from "@/lib/api";
import { membershipDefaultPath } from "@/lib/membershipRouting";
import { t } from "@/lib/i18n";

type OrgChoice = { slug: string; name: string; organization_id: number };

function LoginContent() {
  const { locale } = useLocale();
  const { refreshMe } = useSession();
  const router = useRouter();
  const [message, setMessage] = useState("");
  const [orgChoices, setOrgChoices] = useState<OrgChoice[] | null>(null);
  const [pending, setPending] = useState<{ email: string; password: string } | null>(null);

  function routeAfterLogin(user: MeUser) {
    router.push(membershipDefaultPath(user));
    router.refresh();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    setOrgChoices(null);
    setPending(null);
    const form = new FormData(event.currentTarget);
    const organization_slug = String(form.get("organization_slug") ?? "")
      .trim()
      .toLowerCase();
    const email = String(form.get("email") ?? "")
      .trim()
      .toLowerCase();
    const password = String(form.get("password") ?? "");
    try {
      const user = await apiFetch<MeUser>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email,
          password,
          organization_slug,
        }),
      });
      await refreshMe();
      routeAfterLogin(user);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        const d = e.detail;
        if (
          d &&
          typeof d === "object" &&
          "code" in d &&
          (d as { code: string }).code === "organization_slug_required" &&
          "organizations" in d
        ) {
          const orgs = (d as { organizations: OrgChoice[] }).organizations;
          setOrgChoices(orgs);
          setPending({ email, password });
          setMessage(t(locale, "loginPickOrganization"));
          return;
        }
      }
      setMessage(t(locale, "loginFailed"));
    }
  }

  async function completeWithSlug(slug: string) {
    if (!pending) return;
    setMessage("");
    try {
      const user = await apiFetch<MeUser>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: pending.email,
          password: pending.password,
          organization_slug: slug,
        }),
      });
      setPending(null);
      setOrgChoices(null);
      await refreshMe();
      routeAfterLogin(user);
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
        <Field label={t(locale, "organizationSlugLabel")}>
          <input
            className={inputClass}
            name="organization_slug"
            maxLength={64}
            placeholder={t(locale, "organizationSlugPlaceholder")}
            autoComplete="organization"
          />
        </Field>
        <p className="text-xs text-slate-500">{t(locale, "organizationSlugHint")}</p>
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
        <p className="text-xs text-slate-500">{t(locale, "loginRemovedAccountHint")}</p>
        {message ? <p className="text-sm text-slate-600">{message}</p> : null}
      </form>
      {orgChoices && orgChoices.length > 0 ? (
        <div className="mt-4 flex max-w-md flex-col gap-2 rounded-lg border border-amber-200 bg-amber-50/80 p-3">
          <p className="text-sm font-medium text-amber-950">{t(locale, "loginPickOrganization")}</p>
          <div className="flex flex-wrap gap-2">
            {orgChoices.map((o) => (
              <button
                key={o.slug}
                type="button"
                className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-left text-sm font-medium text-slate-800 shadow-sm hover:bg-slate-50"
                onClick={() => void completeWithSlug(o.slug)}
              >
                <span className="block font-medium">{o.name}</span>
                <span className="font-mono text-xs text-slate-500">{o.slug}</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </Card>
  );
}

export default function LoginPage() {
  return <LoginContent />;
}
