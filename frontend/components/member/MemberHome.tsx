"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Card } from "@/components/Card";
import { DashboardMemberPanel } from "@/components/DashboardMemberPanel";
import { useLocale, useSession } from "@/components/LocaleProvider";
import { t } from "@/lib/i18n";
import { memberAreaHref } from "@/lib/memberAreaHref";
import { isActionableMemberSwap } from "@/lib/memberSwapActions";
import { isUserSession } from "@/lib/membershipRouting";
import { useMemberDashboard } from "@/lib/queries/planning";
import { useShiftSwapList } from "@/lib/queries/activity";

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

  const dashboard = useMemberDashboard({
    year: new Date().getFullYear(),
    shiftGroupId,
    enabled: Boolean(user?.capabilities.team_member_portal && shiftGroupId)
  });
  const swaps = useShiftSwapList({
    periodId: dashboard.data?.current_period ? String(dashboard.data.current_period.period_id) : "",
    shiftGroupId,
    scope: "member-home",
    enabled: Boolean(shiftGroupId && dashboard.data?.current_period)
  });
  const draft = dashboard.data?.periods.find((period) => period.status === "draft");
  const teamMemberId = user?.team_member_id ?? null;
  const openSwaps = (swaps.data ?? []).filter((row) => isActionableMemberSwap(row, teamMemberId));
  const swapsPeriodId = dashboard.data?.current_period?.period_id;

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
          <p className="text-sm text-slate-800">{t(locale, "memberWishesDeadline", { period: `${draft.year}-${String(draft.month).padStart(2, "0")}` })}</p>
          <Link href={`/my-planning?period=${draft.period_id}&shiftGroup=${shiftGroupId}`} className="mt-2 inline-flex min-h-11 items-center font-semibold text-ink">
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
      <Link href={memberAreaHref("/my-hours", new URLSearchParams(shiftGroupId ? { shiftGroup: shiftGroupId } : undefined))} className="inline-flex min-h-11 items-center text-sm font-semibold text-ink">
        {t(locale, "myHoursNav")}
      </Link>
      {dashboard.data ? <DashboardMemberPanel locale={locale} data={dashboard.data} shiftGroupId={shiftGroupId} /> : null}
    </div>
  );
}
