"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Card } from "@/components/Card";
import { DashboardUpcomingShiftsTable } from "@/components/DashboardUpcomingShiftsTable";
import { useLocale, useSession } from "@/components/LocaleProvider";
import { t } from "@/lib/i18n";
import { memberAreaHref } from "@/lib/memberAreaHref";
import { isUserSession } from "@/lib/membershipRouting";
import { useMemberHome } from "@/lib/queries/member";

export function MemberHome() {
  const { locale } = useLocale();
  const { me, loading } = useSession();
  const searchParams = useSearchParams();
  const user = me && isUserSession(me) ? me : null;
  const groups = user?.shift_groups ?? [];
  const [shiftGroupId, setShiftGroupId] = useState(searchParams.get("shiftGroup") ?? "");

  useEffect(() => {
    if (!shiftGroupId && groups.length === 1) {
      setShiftGroupId(String(groups[0].id));
    }
  }, [groups, shiftGroupId]);

  const home = useMemberHome(Boolean(user?.capabilities.team_member_portal));
  const draft = home.data?.draft_wishes ?? null;
  const duties = (home.data?.duties ?? []).filter(
    (duty) => !shiftGroupId || String(duty.shift_group_id ?? "") === shiftGroupId
  );
  const openSwaps = (home.data?.swap_actions ?? []).filter(
    (row) => !shiftGroupId || String(row.shift_group_id) === shiftGroupId
  );
  const swapsPeriodId = openSwaps[0]?.planning_period_id;
  const wishesGroupId = draft ? String(draft.shift_group_id) : shiftGroupId;
  const wishesPeriod = draft ? `${draft.year}-${String(draft.month).padStart(2, "0")}` : "";

  if (loading) {
    return <p className="text-sm text-slate-600">{t(locale, "planningSessionLoading")}</p>;
  }

  return (
    <div className="grid gap-5">
      <h1 className="text-2xl font-semibold text-ink">{t(locale, "memberHome")}</h1>
      {groups.length > 1 ? (
        <label className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
          {t(locale, "selectPlanningShiftGroup")}
          <select
            className="min-h-11 min-w-44 rounded-md border border-slate-200 bg-white px-2"
            value={shiftGroupId}
            onChange={(event) => setShiftGroupId(event.target.value)}
          >
            <option value="">{t(locale, "emptyValue")}</option>
            {groups.map((group) => (
              <option key={group.id} value={String(group.id)}>
                {group.name}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {draft ? (
        <Card>
          <p className="text-sm text-slate-800">{t(locale, "memberWishesDeadline", { period: wishesPeriod })}</p>
          <Link
            href={`/my-planning?period=${draft.planning_period_id}&shiftGroup=${wishesGroupId}`}
            className="mt-2 inline-flex min-h-11 items-center font-semibold text-ink"
          >
            {t(locale, "memberTabWishes")}
          </Link>
        </Card>
      ) : null}
      {openSwaps.length > 0 ? (
        <Card>
          <p className="text-sm font-semibold text-ink">
            {t(locale, "memberOpenSwaps")}: {openSwaps.length}
          </p>
          <Link
            href={`/my-planning?tab=shifts&period=${swapsPeriodId ?? ""}&shiftGroup=${shiftGroupId}`}
            className="mt-2 inline-flex min-h-11 items-center font-semibold text-ink"
          >
            {t(locale, "memberTabSwaps")}
          </Link>
        </Card>
      ) : null}
      <section className="grid gap-2">
        <h2 className="text-lg font-semibold text-ink">{t(locale, "dashboardUpcomingShifts")}</h2>
        <DashboardUpcomingShiftsTable locale={locale} slots={duties} />
      </section>
      <Link
        href={memberAreaHref("/my-hours", new URLSearchParams(shiftGroupId ? { shiftGroup: shiftGroupId } : undefined))}
        className="inline-flex min-h-11 items-center text-sm font-semibold text-ink"
      >
        {t(locale, "myHoursNav")}
      </Link>
    </div>
  );
}
