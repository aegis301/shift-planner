"use client";

import Link from "next/link";
import { Card } from "@/components/Card";
import type { DashboardPeriodCard } from "@/lib/dashboard";
import { fillPercent, periodLabel } from "@/lib/dashboard";
import type { Locale, TranslationKey } from "@/lib/i18n";
import { t } from "@/lib/i18n";

export function DashboardKpiTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-ink">{value}</p>
    </div>
  );
}

function statusLabel(locale: Locale, status: string): string {
  const map: Record<string, TranslationKey> = {
    draft: "periodStatusDraft",
    preliminary: "periodStatusPreliminary",
    published: "periodStatusPublished",
  };
  const key = map[status];
  return key ? t(locale, key) : status;
}

function statusClass(status: string): string {
  if (status === "published") {
    return "bg-emerald-100 text-emerald-800";
  }
  if (status === "preliminary") {
    return "bg-amber-100 text-amber-900";
  }
  return "bg-slate-100 text-slate-700";
}

export function DashboardPeriodCards({
  locale,
  periods,
  hrefForPeriod,
}: {
  locale: Locale;
  periods: DashboardPeriodCard[];
  hrefForPeriod: (periodId: number) => string;
}) {
  if (periods.length === 0) {
    return <p className="text-sm text-slate-500">{t(locale, "dashboardNoPeriods")}</p>;
  }
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {periods.map((period) => (
        <Link
          key={period.period_id}
          href={hrefForPeriod(period.period_id)}
          className="block rounded-lg border border-slate-200 bg-white p-4 shadow-sm transition hover:border-mint/40 hover:shadow-md"
        >
          <div className="flex items-center justify-between gap-2">
            <span className="font-semibold text-ink">{periodLabel(period.year, period.month)}</span>
            <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${statusClass(period.status)}`}>
              {statusLabel(locale, period.status)}
            </span>
          </div>
          <p className="mt-2 text-sm text-slate-600">
            {t(locale, "dashboardFillRate")}: {fillPercent(period)}%
          </p>
          <p className="text-sm text-slate-600">
            {t(locale, "dashboardUnassigned")}: {period.unassigned_count}
          </p>
          {(period.validation_errors > 0 || period.validation_warnings > 0) && (
            <p className="mt-1 text-xs text-coral">
              {period.validation_errors} {t(locale, "dashboardErrors")} · {period.validation_warnings}{" "}
              {t(locale, "dashboardWarnings")}
            </p>
          )}
        </Link>
      ))}
    </div>
  );
}

export function DashboardSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card>
      <h2 className="text-lg font-semibold text-ink">{title}</h2>
      <div className="mt-4">{children}</div>
    </Card>
  );
}
