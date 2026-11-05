"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useLocale } from "@/components/LocaleProvider";
import type { ShiftGroupMembershipRead } from "@/lib/api/types";
import { t, type TranslationKey } from "@/lib/i18n";
import { formatIsoDate, isoDateRangeStatus, type DateRangeStatus } from "@/lib/planningDates";
import { useShiftGroupsIncludingInactive } from "@/lib/queries/planning";

export const SHIFT_GROUP_MEMBERSHIP_EDITOR_PATH = "/organization/shifts/groups";

const STATUS_LABEL: Record<DateRangeStatus, TranslationKey> = {
  active: "membershipStatusActive",
  planned: "membershipStatusPlanned",
  ended: "membershipStatusEnded"
};

const STATUS_BADGE: Record<DateRangeStatus, string> = {
  active: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  planned: "bg-sky-50 text-sky-800 ring-sky-200",
  ended: "bg-slate-100 text-slate-600 ring-slate-200"
};

function ShiftGroupEditorLink() {
  const { locale } = useLocale();
  return (
    <Link className="text-xs font-semibold text-ink underline underline-offset-2" href={SHIFT_GROUP_MEMBERSHIP_EDITOR_PATH}>
      {t(locale, "teamMemberShiftGroupsEditLink")}
    </Link>
  );
}

export function TeamMemberShiftGroupPeriods({ memberships }: { memberships: ShiftGroupMembershipRead[] }) {
  const { locale } = useLocale();
  const groups = useShiftGroupsIncludingInactive(true);
  const groupNameById = useMemo(
    () => new Map((groups.data ?? []).map((group) => [group.id, group.name] as const)),
    [groups.data]
  );
  const sorted = useMemo(
    () =>
      [...memberships].sort(
        (left, right) => left.shift_group_id - right.shift_group_id || left.start_date.localeCompare(right.start_date)
      ),
    [memberships]
  );

  return (
    <section className="mt-4 rounded-lg border border-slate-200 p-3" data-testid="team-member-shift-group-periods">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-ink">{t(locale, "teamMemberShiftGroups")}</p>
          <p className="mt-1 text-xs text-slate-600">{t(locale, "teamMemberShiftGroupPeriodsHelp")}</p>
        </div>
        <ShiftGroupEditorLink />
      </div>
      {sorted.length === 0 ? (
        <p className="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">{t(locale, "membershipNoneYet")}</p>
      ) : (
        <ul className="mt-2 grid gap-1.5 text-sm">
          {sorted.map((row) => {
            const status = isoDateRangeStatus(row.start_date, row.end_date ?? null);
            return (
              <li key={row.id} className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-ink">{groupNameById.get(row.shift_group_id) ?? `#${row.shift_group_id}`}</span>
                <span className="text-xs text-slate-500">
                  {formatIsoDate(row.start_date, locale)} –{" "}
                  {row.end_date ? formatIsoDate(row.end_date, locale) : t(locale, "membershipOpenEnded")}
                </span>
                <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ${STATUS_BADGE[status]}`}>
                  {t(locale, STATUS_LABEL[status])}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

export function TeamMemberShiftGroupCreateHint() {
  const { locale } = useLocale();
  return (
    <section className="mt-4 flex flex-wrap items-start justify-between gap-2 rounded-lg border border-slate-200 p-3">
      <div>
        <p className="text-sm font-semibold text-ink">{t(locale, "teamMemberShiftGroups")}</p>
        <p className="mt-1 text-xs text-slate-600">{t(locale, "teamMemberCreateShiftGroupsHint")}</p>
      </div>
      <ShiftGroupEditorLink />
    </section>
  );
}
