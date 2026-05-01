"use client";

import { BrainCircuit, CalendarCheck, ShieldCheck } from "lucide-react";
import { Card } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";
import { t } from "@/lib/i18n";

function DashboardContent() {
  const { locale } = useLocale();
  return (
    <div className="grid gap-5 lg:grid-cols-[1.25fr_0.75fr]">
      <Card>
        <div className="flex items-start gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-mint/15 text-emerald-700">
            <CalendarCheck aria-hidden />
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-normal text-ink">{t(locale, "currentFocus")}</h1>
            <p className="mt-2 max-w-2xl text-slate-600">{t(locale, "mvpFocus")}</p>
          </div>
        </div>
      </Card>
      <Card>
        <div className="flex items-start gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-coral/15 text-coral">
            <BrainCircuit aria-hidden />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-ink">{t(locale, "mcpStatus")}</h2>
            <p className="mt-2 text-sm text-slate-600">{t(locale, "mcpText")}</p>
          </div>
        </div>
      </Card>
      <Card>
        <div className="flex items-center gap-3">
          <ShieldCheck className="text-emerald-700" aria-hidden />
          <p className="text-sm text-slate-600">{t(locale, "freshStart")}</p>
        </div>
      </Card>
    </div>
  );
}

export function Dashboard() {
  return <DashboardContent />;
}

