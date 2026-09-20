"use client";

import { useCallback, useEffect, useState } from "react";
import { Card } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";
import { ApiError, apiFetch } from "@/lib/api";
import { t } from "@/lib/i18n";

type DutyActivityPurpose = {
  purpose_statement: string;
  acknowledged: boolean;
  acknowledged_at: string | null;
};

export function DutyActivityPurposeSection() {
  const { locale } = useLocale();
  const [purpose, setPurpose] = useState<DutyActivityPurpose | null>(null);
  const [message, setMessage] = useState("");

  const reload = useCallback(async () => {
    const next = await apiFetch<DutyActivityPurpose>("/api/v1/duty-activity/purpose");
    setPurpose(next);
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function acknowledge() {
    setMessage("");
    try {
      const next = await apiFetch<DutyActivityPurpose>("/api/v1/duty-activity/purpose/acknowledge", {
        method: "POST"
      });
      setPurpose(next);
    } catch (e) {
      if (e instanceof ApiError && typeof e.detail === "string") {
        setMessage(e.detail);
      } else {
        setMessage(t(locale, "dutyActivitySaveError"));
      }
    }
  }

  if (!purpose) {
    return null;
  }

  return (
    <Card>
      <h2 className="text-lg font-semibold text-ink">{t(locale, "dutyActivityPurposeTitle")}</h2>
      <p className="mt-1 text-sm text-slate-600">{t(locale, "dutyActivityPurposeHelp")}</p>
      <p className="mt-3 whitespace-pre-wrap text-sm text-slate-800">
        {purpose.purpose_statement.trim() ? purpose.purpose_statement : t(locale, "dutyActivityPurposeEmpty")}
      </p>
      {purpose.acknowledged ? (
        <p className="mt-3 text-sm text-emerald-700">{t(locale, "dutyActivityPurposeAcknowledged")}</p>
      ) : (
        <button
          type="button"
          className="mt-4 inline-flex h-11 items-center justify-center rounded-lg bg-ink px-4 text-sm font-semibold text-white"
          onClick={() => void acknowledge()}
        >
          {t(locale, "dutyActivityPurposeAcknowledge")}
        </button>
      )}
      {message ? <p className="mt-2 text-sm text-rose-700">{message}</p> : null}
    </Card>
  );
}
