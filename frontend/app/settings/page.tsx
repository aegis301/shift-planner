"use client";

import { Bot, Languages } from "lucide-react";
import { LocaleShell, useLocale } from "@/components/LocaleProvider";
import { Card } from "@/components/Card";
import { t } from "@/lib/i18n";

function SettingsContent() {
  const { locale, setLocale } = useLocale();
  return (
    <div className="grid gap-5 md:grid-cols-2">
      <Card>
        <div className="flex items-start gap-4">
          <Languages className="text-emerald-700" aria-hidden />
          <div>
            <h1 className="text-xl font-semibold text-ink">{t(locale, "language")}</h1>
            <button
              className="mt-4 h-11 rounded-lg bg-ink px-4 text-sm font-semibold text-white"
              onClick={() => setLocale(locale === "de" ? "en" : "de")}
            >
              {locale.toUpperCase()}
            </button>
          </div>
        </div>
      </Card>
      <Card>
        <div className="flex items-start gap-4">
          <Bot className="text-coral" aria-hidden />
          <div>
            <h2 className="text-xl font-semibold text-ink">{t(locale, "mcpStatus")}</h2>
            <p className="mt-2 text-sm text-slate-600">{t(locale, "mcpText")}</p>
          </div>
        </div>
      </Card>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <LocaleShell>
      <SettingsContent />
    </LocaleShell>
  );
}

