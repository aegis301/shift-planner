"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Download, X } from "lucide-react";
import { Card, Field, inputClass } from "@/components/Card";
import { DashboardUpcomingShiftsTable } from "@/components/DashboardUpcomingShiftsTable";
import { DutyActivityLiveBanner } from "@/components/DutyActivityControl";
import { DutyActivityShiftList } from "@/components/DutyActivityShiftList";
import { useLocale, useSession, type MeUser } from "@/components/LocaleProvider";
import { MatrixEditor } from "@/components/MatrixEditor";
import { PlanningDayIntervalBar } from "@/components/PlanningDayIntervalBar";
import { PlanningDayStatusLegend } from "@/components/PlanningDayStatusLegend";
import { RosterMatrixEditor } from "@/components/RosterMatrixEditor";
import { ShiftSwapMarketplace } from "@/components/ShiftSwapMarketplace";
import { ShiftSwapOfferDialog } from "@/components/ShiftSwapOfferDialog";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { API_BASE_URL } from "@/lib/api";
import { monthDateBounds } from "@/lib/planningDates";
import { t } from "@/lib/i18n";
import { isUserSession } from "@/lib/membershipRouting";
import {
  useDayStatusDefinitions,
  useMemberDashboard,
  usePlanningPeriods,
  useRosterMatrix,
  useWishesMatrix
} from "@/lib/queries/planning";
import { invalidateQueryKeys, rosterAssignmentKeys, wishesEditKeys } from "@/lib/queries/invalidation";
import { useQueryClient } from "@tanstack/react-query";
import type { SwapOfferContext } from "@/lib/shiftSwaps";

type MemberTab = "wishes" | "roster" | "shifts";

function monthLabel(period: { year: number; month: number }) {
  return `${period.year}-${String(period.month).padStart(2, "0")}`;
}

export function MemberPlanning() {
  const { locale } = useLocale();
  const { me, loading } = useSession();
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const userMe: MeUser | null = me && isUserSession(me) ? me : null;
  const [periodId, setPeriodId] = useState("");
  const [shiftGroupId, setShiftGroupId] = useState("");
  const [message, setMessage] = useState("");
  const [exportOpen, setExportOpen] = useState(false);
  const [offerSlotId, setOfferSlotId] = useState<number | null>(null);
  const [icsStart, setIcsStart] = useState("");
  const [icsEnd, setIcsEnd] = useState("");
  const tab = (searchParams.get("tab") as MemberTab | null) ?? "wishes";
  const activeTab: MemberTab = tab === "roster" || tab === "shifts" ? tab : "wishes";

  useEffect(() => {
    if (!loading && userMe && !userMe.capabilities.team_member_portal) {
      router.replace(userMe.capabilities.planning ? "/planning" : "/");
    }
  }, [loading, router, userMe]);

  useEffect(() => {
    setShiftGroupId(searchParams.get("shiftGroup") ?? "");
    const period = searchParams.get("period");
    if (period) {
      setPeriodId(period);
    }
  }, [searchParams]);

  const periodsQuery = usePlanningPeriods(Boolean(userMe?.capabilities.team_member_portal));
  const periods = periodsQuery.data ?? [];
  const shiftGroups = (userMe?.shift_groups ?? []).map((group) => ({ id: group.id, code: group.code, name: group.name }));
  const dayStatusDefinitions = useDayStatusDefinitions(Boolean(userMe)).data ?? [];
  const wishesQuery = useWishesMatrix({
    periodId,
    shiftGroupId,
    teamMemberPortal: true,
    enabled: Boolean(periodId && shiftGroupId)
  });
  const status = wishesQuery.data?.matrix.shift_group_planning_status?.status;
  const rosterVisible = status === "preliminary" || status === "published";
  const wishesEditable = status === "draft" || status === "preliminary";
  const rosterQuery = useRosterMatrix({
    periodId,
    shiftGroupId,
    teamMemberPortal: true,
    enabled: Boolean(periodId && shiftGroupId && rosterVisible)
  });
  const activePeriod = periods.find((period) => String(period.id) === periodId);
  const memberDashboard = useMemberDashboard({
    year: activePeriod?.year ?? new Date().getFullYear(),
    shiftGroupId,
    enabled: Boolean(shiftGroupId)
  });

  useEffect(() => {
    if (!periods.length || periodId) {
      return;
    }
    const fromUrl = searchParams.get("period");
    if (fromUrl && periods.some((row) => String(row.id) === fromUrl)) {
      setPeriodId(fromUrl);
      return;
    }
    if (periods[0]) {
      setPeriodId(String(periods[0].id));
    }
  }, [periodId, periods, searchParams]);

  useEffect(() => {
    if (shiftGroupId || (userMe?.shift_groups ?? []).length !== 1) {
      return;
    }
    const id = String(userMe?.shift_groups?.[0]?.id ?? "");
    if (!id) {
      return;
    }
    setShiftGroupId(id);
    const params = new URLSearchParams(searchParams.toString());
    params.set("shiftGroup", id);
    router.replace(`/my-planning?${params.toString()}`, { scroll: false });
  }, [router, searchParams, shiftGroupId, userMe]);

  useEffect(() => {
    const now = new Date();
    const bounds = activePeriod ? monthDateBounds(activePeriod.year, activePeriod.month) : monthDateBounds(now.getFullYear(), now.getMonth() + 1);
    setIcsStart(bounds.min);
    setIcsEnd(bounds.max);
  }, [activePeriod]);

  useEffect(() => {
    if (shiftGroupId && status && status !== "preliminary" && status !== "published") {
      setMessage(t(locale, "rosterNotVisibleYet"));
    }
  }, [locale, shiftGroupId, status]);

  const rosterMatrix = rosterQuery.data?.matrix ?? null;
  const rosterSlotIds = useMemo(() => new Set(rosterMatrix?.slots.map((slot) => slot.id) ?? []), [rosterMatrix]);
  const memberPortal = "team_member" as const;
  const swapOffer: SwapOfferContext | undefined = userMe
    ? {
        variant: memberPortal,
        capabilities: { team_member_portal: true },
        teamMemberId: userMe.team_member_id ?? null,
        shiftGroupId: shiftGroupId || null,
        periodId: periodId || null,
        groupStatus: status,
        rosterSlotIds,
        onOffer: (slotId) => setOfferSlotId(slotId)
      }
    : undefined;

  function selectTab(next: MemberTab) {
    const params = new URLSearchParams(searchParams.toString());
    if (next === "wishes") {
      params.delete("tab");
    } else {
      params.set("tab", next);
    }
    const query = params.toString();
    router.replace(query ? `/my-planning?${query}` : "/my-planning", { scroll: false });
  }

  async function refreshAfterEdit() {
    if (!userMe) {
      return;
    }
    const scope = {
      organizationId: userMe.organization_id,
      periodId,
      shiftGroupId,
      teamMemberPortal: true
    };
    await invalidateQueryKeys(queryClient, wishesEditKeys(scope));
    await invalidateQueryKeys(queryClient, rosterAssignmentKeys(scope));
  }

  const icsQuery = shiftGroupId ? `?shift_group_id=${encodeURIComponent(shiftGroupId)}` : "";
  const rangeQuery = new URLSearchParams();
  if (shiftGroupId) {
    rangeQuery.set("shift_group_id", shiftGroupId);
  }
  if (icsStart) {
    rangeQuery.set("start_date", icsStart);
  }
  if (icsEnd) {
    rangeQuery.set("end_date", icsEnd);
  }

  return (
    <div className="grid min-w-0 gap-5">
      <Card>
        <div className="grid gap-3">
          <h1 className="text-2xl font-semibold text-ink">{t(locale, "myPlanning")}</h1>
          <div className="flex flex-wrap items-end gap-2">
            <Field label={t(locale, "planningPeriod")}>
              <select className={`${inputClass} h-11 min-w-40`} value={periodId} onChange={(event) => setPeriodId(event.target.value)}>
                <option value="">{t(locale, "emptyValue")}</option>
                {periods.map((period) => (
                  <option key={period.id} value={period.id}>
                    {monthLabel(period)}
                  </option>
                ))}
              </select>
            </Field>
            <Field label={t(locale, "selectPlanningShiftGroup")}>
              <select
                className={`${inputClass} h-11 min-w-44`}
                value={shiftGroupId}
                onChange={(event) => setShiftGroupId(event.target.value)}
              >
                {shiftGroups.map((group) => (
                  <option key={group.id} value={String(group.id)}>
                    {group.name} ({group.code})
                  </option>
                ))}
              </select>
            </Field>
            <button
              type="button"
              aria-label={t(locale, "exports")}
              className="inline-flex h-11 w-11 items-center justify-center rounded-lg border border-slate-200 bg-white"
              disabled={!shiftGroupId}
              onClick={() => setExportOpen(true)}
            >
              <Download size={18} />
            </button>
          </div>
          {message ? <p className="text-sm text-slate-600">{message}</p> : null}
          <PlanningDayStatusLegend locale={locale} definitions={dayStatusDefinitions} />
          {periodId && shiftGroupId ? (
            <PlanningDayIntervalBar
              periodId={periodId}
              shiftGroupId={shiftGroupId}
              readOnly={!wishesEditable}
              teamMemberPortal
              editableMemberId={userMe?.team_member_id ?? undefined}
              dayStatusDefinitions={dayStatusDefinitions}
              onApplied={refreshAfterEdit}
            />
          ) : null}
        </div>
      </Card>
      {memberDashboard.data ? <DutyActivityLiveBanner slots={[...memberDashboard.data.upcoming_slots, ...memberDashboard.data.past_slots]} /> : null}
      <div className="flex gap-2 overflow-x-auto rounded-lg border border-slate-200 bg-white p-1">
        {(["wishes", "roster", "shifts"] as const).map((item) => (
          <button
            key={item}
            type="button"
            className={`inline-flex h-11 min-w-11 items-center justify-center rounded-md px-3 text-sm font-semibold ${
              activeTab === item ? "bg-ink text-white" : "text-slate-600"
            }`}
            onClick={() => selectTab(item)}
          >
            {t(locale, item === "wishes" ? "wishesSection" : item === "roster" ? "rosterSection" : "myPlanningShiftsSection")}
          </button>
        ))}
      </div>
      {activeTab === "wishes" && periodId && shiftGroupId ? (
        <section className="grid gap-3">
          <h2 className="text-xl font-semibold text-ink">{t(locale, "wishesSection")}</h2>
          {wishesEditable ? (
            <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800">
              {status === "preliminary" ? t(locale, "myPlanningWishesFeedbackHintPreliminary") : t(locale, "myPlanningWishesFeedbackHintDraft")}
            </p>
          ) : null}
          <MatrixEditor
            periodId={periodId}
            compact
            phoneLayout
            shiftGroupId={shiftGroupId}
            editableMemberId={wishesEditable ? userMe?.team_member_id ?? undefined : undefined}
            teamMemberPortal
            readOnly={!wishesEditable}
            dayFeedbackAlwaysVisible={wishesEditable}
            onChanged={refreshAfterEdit}
          />
        </section>
      ) : null}
      {activeTab === "roster" && periodId ? (
        <section className="grid gap-3">
          <h2 className="text-xl font-semibold text-ink">{t(locale, "rosterSection")}</h2>
          {!rosterVisible ? (
            <p className="text-sm text-slate-600">{t(locale, "rosterNotVisibleYet")}</p>
          ) : (
            <RosterMatrixEditor
              periodId={periodId}
              compact
              readOnly
              teamMemberPortal
              shiftGroupId={shiftGroupId}
              highlightTeamMemberId={userMe?.team_member_id ?? undefined}
              swapOffer={swapOffer}
            />
          )}
        </section>
      ) : null}
      {activeTab === "shifts" ? (
        <section className="grid gap-4">
          <h2 className="text-xl font-semibold text-ink">{t(locale, "myPlanningShiftsSection")}</h2>
          {memberDashboard.data ? (
            <>
              <DashboardUpcomingShiftsTable locale={locale} slots={memberDashboard.data.upcoming_slots} showIcsExport swapOffer={swapOffer} />
              <DashboardUpcomingShiftsTable
                locale={locale}
                slots={memberDashboard.data.past_slots}
                emptyLabelKey="dashboardPastShiftsEmpty"
                showIcsExport
              />
              <DutyActivityShiftList slots={[...memberDashboard.data.upcoming_slots, ...memberDashboard.data.past_slots]} />
            </>
          ) : (
            <p className="text-sm text-slate-500">{t(locale, "noData")}</p>
          )}
          <ShiftSwapMarketplace
            capabilities={{ team_member_portal: true }}
            groupStatus={status}
            onChanged={() => void refreshAfterEdit()}
            periodId={periodId}
            roster={rosterMatrix}
            shiftGroupId={shiftGroupId}
            teamMemberId={userMe?.team_member_id ?? null}
            variant={memberPortal}
          />
        </section>
      ) : null}
      <Dialog open={exportOpen} onOpenChange={setExportOpen}>
        <DialogContent>
          <div className="mb-4 flex items-center justify-between">
            <DialogTitle>{t(locale, "exports")}</DialogTitle>
            <button type="button" aria-label={t(locale, "close")} onClick={() => setExportOpen(false)}>
              <X size={17} />
            </button>
          </div>
          <a className="inline-flex h-11 items-center justify-center rounded-lg border border-slate-200 px-4 text-sm font-semibold" href={`${API_BASE_URL}/api/v1/exports/my-shifts.ics${icsQuery}`}>
            {t(locale, "myShiftsIcsExport")}
          </a>
          <a
            className="mt-3 inline-flex h-11 items-center justify-center rounded-lg border border-slate-200 px-4 text-sm font-semibold"
            href={`${API_BASE_URL}/api/v1/exports/my-shifts.ics?${rangeQuery.toString()}`}
          >
            {t(locale, "myShiftsRangeIcsExport")}
          </a>
        </DialogContent>
      </Dialog>
      {periodId && shiftGroupId && offerSlotId != null ? (
        <ShiftSwapOfferDialog
          open
          offeredSlotId={offerSlotId}
          onClose={() => setOfferSlotId(null)}
          onSubmitted={() => {
            setOfferSlotId(null);
            setMessage(t(locale, "shiftSwapOffered"));
          }}
          periodId={periodId}
          roster={rosterMatrix}
          shiftGroupId={shiftGroupId}
        />
      ) : null}
    </div>
  );
}
