"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Building2, LogIn } from "lucide-react";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale, useSession, type MeUser } from "@/components/LocaleProvider";
import { apiFetch } from "@/lib/api";
import { isAccountSession, membershipDefaultPath } from "@/lib/membershipRouting";
import { t } from "@/lib/i18n";

type LookupResult = { slug: string; name: string };

export default function OnboardingPage() {
  const { locale } = useLocale();
  const { me, loading, refreshMe } = useSession();
  const router = useRouter();
  const [createMsg, setCreateMsg] = useState("");
  const [joinMsg, setJoinMsg] = useState("");
  const [joinLookup, setJoinLookup] = useState<LookupResult | null | undefined>(undefined);

  useEffect(() => {
    if (loading || !me) return;
    if (!isAccountSession(me)) {
      router.replace(membershipDefaultPath(me));
    }
  }, [loading, me, router]);

  async function runLookup(slug: string) {
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

  async function submitCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreateMsg("");
    const form = new FormData(event.currentTarget);
    const slug = String(form.get("organization_slug") ?? "")
      .trim()
      .toLowerCase();
    try {
      const user = await apiFetch<MeUser>("/api/v1/auth/me/onboarding/create-organization", {
        method: "POST",
        body: JSON.stringify({
          organization_name: String(form.get("organization_name") ?? "").trim(),
          organization_slug: slug,
        }),
      });
      await refreshMe();
      router.push(membershipDefaultPath(user));
      router.refresh();
    } catch {
      setCreateMsg(t(locale, "registrationFailed"));
    }
  }

  async function submitJoin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setJoinMsg("");
    const form = new FormData(event.currentTarget);
    const organization_slug = String(form.get("organization_slug") ?? "")
      .trim()
      .toLowerCase();
    try {
      const user = await apiFetch<MeUser>("/api/v1/auth/me/onboarding/join-organization", {
        method: "POST",
        body: JSON.stringify({
          organization_slug,
          first_name: String(form.get("first_name") ?? "").trim(),
          last_name: String(form.get("last_name") ?? "").trim(),
          message: (() => {
            const m = String(form.get("message") ?? "").trim();
            return m.length ? m : null;
          })(),
        }),
      });
      await refreshMe();
      router.push(membershipDefaultPath(user));
      router.refresh();
    } catch {
      setJoinMsg(t(locale, "registrationFailed"));
    }
  }

  if (loading || !me || !isAccountSession(me)) {
    return null;
  }

  return (
    <div className="mx-auto grid max-w-2xl gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink">{t(locale, "onboardingPageTitle")}</h1>
        <p className="mt-2 text-sm text-slate-600">{t(locale, "onboardingPageIntro")}</p>
      </div>

      <Card>
        <form className="grid gap-4" onSubmit={(e) => void submitCreate(e)}>
          <div className="flex items-center gap-2">
            <Building2 className="text-emerald-700" aria-hidden />
            <h2 className="text-lg font-semibold text-ink">{t(locale, "onboardingCreateSectionTitle")}</h2>
          </div>
          <p className="text-sm text-slate-600">{t(locale, "registerCreateIntro")}</p>
          <Field label={t(locale, "organizationNameField")}>
            <input className={inputClass} name="organization_name" required minLength={1} />
          </Field>
          <Field label={t(locale, "organizationSlugField")}>
            <input className={inputClass} name="organization_slug" required minLength={3} maxLength={64} />
          </Field>
          <button
            type="submit"
            className="inline-flex h-11 items-center justify-center rounded-lg bg-ink px-4 text-sm font-semibold text-white"
          >
            {t(locale, "onboardingCreateSubmit")}
          </button>
          {createMsg ? <p className="text-sm text-red-600">{createMsg}</p> : null}
        </form>
      </Card>

      <Card>
        <form className="grid gap-4" onSubmit={(e) => void submitJoin(e)}>
          <div className="flex items-center gap-2">
            <LogIn className="text-emerald-700" aria-hidden />
            <h2 className="text-lg font-semibold text-ink">{t(locale, "onboardingJoinSectionTitle")}</h2>
          </div>
          <p className="text-sm text-slate-600">{t(locale, "registerJoinIntro")}</p>
          <Field label={t(locale, "organizationSlugLabel")}>
            <div className="flex gap-2">
              <input
                className={`${inputClass} min-w-0 flex-1`}
                name="organization_slug"
                id="onboarding-org-slug"
                required
                minLength={1}
                maxLength={64}
              />
              <button
                type="button"
                className="h-11 shrink-0 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700"
                onClick={() => {
                  const el = document.getElementById("onboarding-org-slug") as HTMLInputElement | null;
                  void runLookup(el?.value ?? "");
                }}
              >
                {t(locale, "lookupOrganization")}
              </button>
            </div>
          </Field>
          {joinLookup === null ? <p className="text-sm text-red-600">{t(locale, "lookupFailed")}</p> : null}
          {joinLookup ? (
            <p className="text-sm text-slate-600">
              {t(locale, "organizationFoundName")}: <span className="font-medium text-ink">{joinLookup.name}</span>
            </p>
          ) : null}
          <Field label={t(locale, "firstName")}>
            <input className={inputClass} name="first_name" required minLength={1} />
          </Field>
          <Field label={t(locale, "lastName")}>
            <input className={inputClass} name="last_name" required minLength={1} />
          </Field>
          <Field label={t(locale, "joinMessageOptional")}>
            <textarea className={`${inputClass} min-h-[88px] py-2`} name="message" maxLength={2000} />
          </Field>
          <button
            type="submit"
            className="inline-flex h-11 items-center justify-center rounded-lg bg-emerald-700 px-4 text-sm font-semibold text-white hover:bg-emerald-800"
          >
            {t(locale, "joinOrganizationSubmit")}
          </button>
          {joinMsg ? <p className="text-sm text-red-600">{joinMsg}</p> : null}
        </form>
      </Card>
    </div>
  );
}
