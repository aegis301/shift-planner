"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowDown, ArrowDownUp, ArrowUp } from "lucide-react";
import { Card } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";
import { dataTableScrollShellClassName } from "@/lib/dataTableLayout";
import {
  fairnessDeviationChipClass,
  fairnessDimensionLabel,
  formatFairnessDeviation,
  formatFairnessQuantity,
  formatFairnessWindowRange,
  type FairnessAccountsRead,
  type FairnessDimension,
  type FairnessMemberAccount
} from "@/lib/fairness";
import { t, type Locale } from "@/lib/i18n";

type SortField = "name" | "actual" | "expected" | "deviation";

function defaultSortDir(field: SortField): "asc" | "desc" {
  return field === "name" ? "asc" : "desc";
}

function memberValue(member: FairnessMemberAccount, dimensionId: string) {
  return member.dimensions.find((row) => row.dimension_id === dimensionId);
}

function compareMembers(
  a: FairnessMemberAccount,
  b: FairnessMemberAccount,
  field: SortField,
  dimensionId: string | null,
  dir: "asc" | "desc"
): number {
  const mul = dir === "asc" ? 1 : -1;
  if (field === "name" || !dimensionId) {
    return a.display_name.localeCompare(b.display_name, undefined, { sensitivity: "base" }) * mul;
  }
  const av = memberValue(a, dimensionId);
  const bv = memberValue(b, dimensionId);
  const aNum = field === "actual" ? (av?.actual ?? 0) : field === "expected" ? (av?.expected ?? 0) : (av?.deviation_absolute ?? 0);
  const bNum = field === "actual" ? (bv?.actual ?? 0) : field === "expected" ? (bv?.expected ?? 0) : (bv?.deviation_absolute ?? 0);
  if (aNum !== bNum) {
    return (aNum - bNum) * mul;
  }
  return a.display_name.localeCompare(b.display_name, undefined, { sensitivity: "base" });
}

function SortableFairnessTh({
  locale,
  label,
  field,
  dimensionId,
  active,
  dir,
  onSort
}: {
  locale: Locale;
  label: string;
  field: SortField;
  dimensionId: string | null;
  active: boolean;
  dir: "asc" | "desc";
  onSort: (field: SortField, dimensionId: string | null) => void;
}) {
  return (
    <th
      scope="col"
      aria-sort={active ? (dir === "asc" ? "ascending" : "descending") : "none"}
      className={`sticky top-0 z-10 bg-teal-50 p-0 font-semibold shadow-[0_1px_0_0_rgb(153_246_228)] ${field === "name" ? "text-left" : "text-right"}`}
    >
      <button
        type="button"
        title={t(locale, "workloadTableSortHint")}
        onClick={() => onSort(field, dimensionId)}
        className={`flex w-full items-center gap-1 px-3 py-3 text-teal-950 hover:bg-teal-100/70 ${field === "name" ? "justify-start" : "justify-end"}`}
      >
        <span>{label}</span>
        {active ? (
          dir === "asc" ? (
            <ArrowUp className="h-3.5 w-3.5 shrink-0 text-teal-900" strokeWidth={2} aria-hidden />
          ) : (
            <ArrowDown className="h-3.5 w-3.5 shrink-0 text-teal-900" strokeWidth={2} aria-hidden />
          )
        ) : (
          <ArrowDownUp className="h-3.5 w-3.5 shrink-0 opacity-35" strokeWidth={2} aria-hidden />
        )}
      </button>
    </th>
  );
}

function DimensionCell({
  member,
  dimension,
  locale
}: {
  member: FairnessMemberAccount;
  dimension: FairnessDimension;
  locale: Locale;
}) {
  const value = memberValue(member, dimension.id);
  if (!value) {
    return <td className="p-3 text-right text-slate-400">—</td>;
  }
  return (
    <td className="p-3 text-right">
      <div className="grid justify-items-end gap-1">
        <span
          className={`inline-flex rounded-md px-1.5 py-0.5 font-mono text-xs font-semibold tabular-nums ring-1 ${fairnessDeviationChipClass(value.deviation_absolute)}`}
        >
          {formatFairnessDeviation(value.deviation_absolute, dimension.metric, locale)}
        </span>
        <span className="text-[0.65rem] tabular-nums text-teal-900/80">
          {t(locale, "fairnessActual")} {formatFairnessQuantity(value.actual, dimension.metric, locale)}
          {" · "}
          {t(locale, "fairnessExpected")} {formatFairnessQuantity(value.expected, dimension.metric, locale)}
        </span>
      </div>
    </td>
  );
}

export function FairnessMemberRollingSummary({
  accounts,
  teamMemberId
}: {
  accounts: FairnessAccountsRead | null;
  teamMemberId: number;
}) {
  const { locale } = useLocale();
  const member = accounts?.members.find((row) => row.team_member_id === teamMemberId);
  if (!accounts || !member) {
    return null;
  }
  const windowLabel = t(locale, "fairnessWindowLabel", {
    months: String(accounts.window.months),
    range: formatFairnessWindowRange(accounts.window)
  });
  return (
    <div className="border-b border-teal-100 bg-teal-50/60 px-4 py-4 sm:px-5">
      <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-teal-800">{t(locale, "fairnessRollingBadge")}</p>
      <h3 className="mt-0.5 text-sm font-semibold text-teal-950">{t(locale, "fairnessModalRollingTitle")}</h3>
      <p className="mt-0.5 text-xs text-teal-900">{windowLabel}</p>
      <dl className="mt-3 grid grid-cols-[1fr_auto] gap-x-4 gap-y-2 text-sm">
        {accounts.dimensions.map((dimension) => {
          const value = memberValue(member, dimension.id);
          return (
            <div key={dimension.id} className="col-span-2 grid grid-cols-[1fr_auto] gap-x-4 gap-y-0.5">
              <dt className="text-teal-900">{fairnessDimensionLabel(locale, dimension)}</dt>
              <dd
                className={`text-right font-mono text-xs font-semibold tabular-nums ${value ? "" : "text-slate-400"}`}
              >
                {value ? formatFairnessDeviation(value.deviation_absolute, dimension.metric, locale) : "—"}
              </dd>
              {value ? (
                <dd className="col-span-2 text-[0.65rem] tabular-nums text-teal-900/80">
                  {t(locale, "fairnessActual")} {formatFairnessQuantity(value.actual, dimension.metric, locale)}
                  {" · "}
                  {t(locale, "fairnessExpected")} {formatFairnessQuantity(value.expected, dimension.metric, locale)}
                </dd>
              ) : null}
            </div>
          );
        })}
      </dl>
    </div>
  );
}

export function FairnessAccountsPanel({
  accounts,
  loadError
}: {
  accounts: FairnessAccountsRead | null;
  loadError: string;
}) {
  const { locale } = useLocale();
  const firstDimensionId = accounts?.dimensions[0]?.id ?? null;
  const [sort, setSort] = useState<{ field: SortField; dimensionId: string | null; dir: "asc" | "desc" }>({
    field: "deviation",
    dimensionId: firstDimensionId,
    dir: "desc"
  });

  useEffect(() => {
    if (!accounts?.dimensions.length) {
      return;
    }
    setSort((prev) => {
      if (prev.field === "name") {
        return prev;
      }
      const stillValid = prev.dimensionId != null && accounts.dimensions.some((row) => row.id === prev.dimensionId);
      if (stillValid) {
        return prev;
      }
      return { field: "deviation", dimensionId: accounts.dimensions[0].id, dir: "desc" };
    });
  }, [accounts]);

  const sortedMembers = useMemo(() => {
    if (!accounts) {
      return [];
    }
    const next = [...accounts.members];
    next.sort((a, b) => compareMembers(a, b, sort.field, sort.dimensionId, sort.dir));
    return next;
  }, [accounts, sort]);

  const activateSort = useCallback((field: SortField, dimensionId: string | null) => {
    setSort((prev) => {
      const same = prev.field === field && prev.dimensionId === dimensionId;
      if (same) {
        return { field, dimensionId, dir: prev.dir === "asc" ? "desc" : "asc" };
      }
      return { field, dimensionId, dir: defaultSortDir(field) };
    });
  }, []);

  const windowLabel = accounts
    ? t(locale, "fairnessWindowLabel", {
        months: String(accounts.window.months),
        range: formatFairnessWindowRange(accounts.window)
      })
    : "";

  return (
    <Card>
      <div className="grid gap-4">
        <div>
          <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-teal-800">{t(locale, "fairnessRollingBadge")}</p>
          <h2 className="text-lg font-semibold text-ink">{t(locale, "fairnessAccountsTitle")}</h2>
          <p className="mt-1 text-sm text-slate-600">{t(locale, "fairnessAccountsHelp")}</p>
          {windowLabel ? <p className="mt-1 text-sm font-medium text-teal-900">{windowLabel}</p> : null}
        </div>
        {loadError ? <p className="text-sm text-rose-700">{loadError}</p> : null}
        {accounts?.members.length ? (
          <div className={`${dataTableScrollShellClassName} rounded-lg border border-teal-200`}>
            <table className="min-w-full text-sm">
              <thead className="text-teal-950">
                <tr className="border-b border-teal-200">
                  <SortableFairnessTh
                    locale={locale}
                    label={t(locale, "teamMembers")}
                    field="name"
                    dimensionId={null}
                    active={sort.field === "name"}
                    dir={sort.dir}
                    onSort={activateSort}
                  />
                  {accounts.dimensions.map((dimension) => (
                    <SortableFairnessTh
                      key={dimension.id}
                      locale={locale}
                      label={`${fairnessDimensionLabel(locale, dimension)} · ${t(locale, "fairnessDeviation")}`}
                      field="deviation"
                      dimensionId={dimension.id}
                      active={sort.field === "deviation" && sort.dimensionId === dimension.id}
                      dir={sort.dir}
                      onSort={activateSort}
                    />
                  ))}
                </tr>
              </thead>
              <tbody>
                {sortedMembers.map((member) => (
                  <tr key={member.team_member_id} className="border-t border-teal-100">
                    <td className="p-3 font-medium text-ink">{member.display_name}</td>
                    {accounts.dimensions.map((dimension) => (
                      <DimensionCell key={dimension.id} member={member} dimension={dimension} locale={locale} />
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : !loadError ? (
          <p className="text-sm text-slate-500">{t(locale, "noData")}</p>
        ) : null}
      </div>
    </Card>
  );
}
