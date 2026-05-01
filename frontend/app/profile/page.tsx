"use client";

import { FormEvent, useEffect, useState } from "react";
import { Card, Field, inputClass } from "@/components/Card";
import { LocaleShell, useLocale, useSession } from "@/components/LocaleProvider";
import { apiFetch } from "@/lib/api";
import { t } from "@/lib/i18n";
import { useRouter } from "next/navigation";

type DoctorRead = {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
  employment_percentage: number;
  notes: string | null;
};

function ProfileContent() {
  const { locale } = useLocale();
  const { me, loading, refreshMe } = useSession();
  const router = useRouter();
  const [doctor, setDoctor] = useState<DoctorRead | null>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (loading) {
      return;
    }
    if (!me || !me.capabilities?.doctor_portal) {
      router.replace(me?.capabilities?.planning ? "/planning" : "/");
    }
  }, [loading, me, router]);

  useEffect(() => {
    if (!me || !me.capabilities?.doctor_portal) {
      return;
    }
    void apiFetch<DoctorRead>("/api/v1/auth/me/doctor")
      .then(setDoctor)
      .catch(() => setDoctor(null));
  }, [me]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await apiFetch<DoctorRead>("/api/v1/auth/me/doctor", {
      method: "PATCH",
      body: JSON.stringify({
        first_name: form.get("first_name"),
        last_name: form.get("last_name"),
        email: form.get("email"),
        employment_percentage: Number(form.get("employment_percentage")),
        notes: form.get("notes") || null
      })
    });
    setMessage(t(locale, "saved"));
    await refreshMe();
  }

  if (loading || !me || !me.capabilities?.doctor_portal) {
    return null;
  }

  if (!doctor) {
    return (
      <Card>
        <p className="text-sm text-slate-600">{t(locale, "noData")}</p>
      </Card>
    );
  }

  return (
    <Card>
      <h1 className="text-2xl font-semibold text-ink">{t(locale, "profileTitle")}</h1>
      <p className="mt-2 text-sm text-slate-600">{t(locale, "profileHelp")}</p>
      <p className="mt-2 text-sm text-slate-700">
        <span className="font-semibold">{t(locale, "id")}:</span> {doctor.id}
      </p>
      <form className="mt-6 grid max-w-lg gap-4" onSubmit={submit}>
        <Field label={t(locale, "firstName")}>
          <input className={inputClass} name="first_name" defaultValue={doctor.first_name} required />
        </Field>
        <Field label={t(locale, "lastName")}>
          <input className={inputClass} name="last_name" defaultValue={doctor.last_name} required />
        </Field>
        <Field label={t(locale, "email")}>
          <input className={inputClass} name="email" type="email" defaultValue={doctor.email} required />
        </Field>
        <Field label={t(locale, "employment")}>
          <input className={inputClass} name="employment_percentage" type="number" min={1} max={100} defaultValue={doctor.employment_percentage} />
        </Field>
        <Field label={t(locale, "notes")}>
          <input className={inputClass} name="notes" defaultValue={doctor.notes ?? ""} />
        </Field>
        <button type="submit" className="inline-flex h-11 items-center justify-center rounded-lg bg-ink px-4 text-sm font-semibold text-white">
          {t(locale, "save")}
        </button>
        {message ? <p className="text-sm text-emerald-700">{message}</p> : null}
      </form>
    </Card>
  );
}

export default function ProfilePage() {
  return (
    <LocaleShell>
      <ProfileContent />
    </LocaleShell>
  );
}
