"use client";

import { FormEvent, useEffect, useState } from "react";
import { Card, Field, inputClass } from "@/components/Card";
import { TeamMemberPlanningPatternsEditor } from "@/components/TeamMemberPlanningPatternsEditor";
import { TeamMemberPropertyValuesEditor } from "@/components/TeamMemberPropertyValuesEditor";
import { useLocale, useSession } from "@/components/LocaleProvider";
import { apiFetch } from "@/lib/api";
import { isUserSession } from "@/lib/membershipRouting";
import { t } from "@/lib/i18n";
import { useRouter } from "next/navigation";

type TeamMemberRead = {
  id: number;
  first_name: string;
  last_name: string;
  nickname: string | null;
  email: string;
  employment_percentage: number;
  notes: string | null;
  planning_preferences: string | null;
};

function ProfileContent() {
  const { locale } = useLocale();
  const { me, loading, refreshMe } = useSession();
  const router = useRouter();
  const [member, setMember] = useState<TeamMemberRead | null>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (loading) {
      return;
    }
    if (!me || !isUserSession(me)) {
      router.replace("/");
      return;
    }
    if (!me.capabilities.team_member_portal) {
      router.replace(me.capabilities.planning ? "/planning" : "/");
    }
  }, [loading, me, router]);

  useEffect(() => {
    if (!me || !isUserSession(me) || !me.capabilities.team_member_portal) {
      return;
    }
    void apiFetch<TeamMemberRead>("/api/v1/auth/me/team-member")
      .then(setMember)
      .catch(() => setMember(null));
  }, [me]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await apiFetch<TeamMemberRead>("/api/v1/auth/me/team-member", {
      method: "PATCH",
      body: JSON.stringify({
        first_name: form.get("first_name"),
        last_name: form.get("last_name"),
        nickname: form.get("nickname") || null,
        email: form.get("email"),
        employment_percentage: Number(form.get("employment_percentage")),
        notes: form.get("notes") || null,
        planning_preferences: form.get("planning_preferences") || null
      })
    });
    setMessage(t(locale, "saved"));
    await refreshMe();
  }

  if (loading || !me || !isUserSession(me) || !me.capabilities.team_member_portal) {
    return null;
  }

  if (!member) {
    return (
      <Card>
        <p className="text-sm text-slate-600">{t(locale, "noData")}</p>
      </Card>
    );
  }

  return (
    <div className="grid gap-6">
      <Card>
        <h1 className="text-2xl font-semibold text-ink">{t(locale, "profileTitle")}</h1>
        <p className="mt-2 text-sm text-slate-600">{t(locale, "profileHelp")}</p>
        <p className="mt-2 text-sm text-slate-700">
          <span className="font-semibold">{t(locale, "id")}:</span> {member.id}
        </p>
        <form className="mt-6 grid max-w-lg gap-4" onSubmit={submit}>
          <Field label={t(locale, "firstName")}>
            <input className={inputClass} name="first_name" defaultValue={member.first_name} required />
          </Field>
          <Field label={t(locale, "lastName")}>
            <input className={inputClass} name="last_name" defaultValue={member.last_name} required />
          </Field>
          <Field label={t(locale, "nickname")}>
            <input className={inputClass} name="nickname" maxLength={64} defaultValue={member.nickname ?? ""} />
            <p className="mt-1 text-xs text-slate-500">{t(locale, "nicknameHelp")}</p>
          </Field>
          <Field label={t(locale, "email")}>
            <input className={inputClass} name="email" type="email" defaultValue={member.email} required />
          </Field>
          <Field label={t(locale, "employment")}>
            <input className={inputClass} name="employment_percentage" type="number" min={1} max={100} defaultValue={member.employment_percentage} />
          </Field>
          <Field label={t(locale, "planningPreferencesField")}>
            <textarea
              className={`${inputClass} min-h-32`}
              name="planning_preferences"
              defaultValue={member.planning_preferences ?? ""}
              rows={5}
            />
          </Field>
          <p className="text-xs text-slate-500">{t(locale, "planningPreferencesMatrixHelp")}</p>
          <Field label={t(locale, "notes")}>
            <input className={inputClass} name="notes" defaultValue={member.notes ?? ""} />
          </Field>
          <button type="submit" className="inline-flex h-11 items-center justify-center rounded-lg bg-ink px-4 text-sm font-semibold text-white">
            {t(locale, "save")}
          </button>
          {message ? <p className="text-sm text-emerald-700">{message}</p> : null}
        </form>
      </Card>
      <Card>
        <TeamMemberPropertyValuesEditor teamMemberId={member.id} />
      </Card>
      <Card>
        <TeamMemberPlanningPatternsEditor teamMemberId={member.id} />
      </Card>
    </div>
  );
}

export default function ProfilePage() {
  return <ProfileContent />;
}
