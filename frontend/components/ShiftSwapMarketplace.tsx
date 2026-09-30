"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Card } from "@/components/Card";
import { useLocale, useSession } from "@/components/LocaleProvider";
import type { MemberSwapListItemRead } from "@/lib/api/types";
import { useMemberSwaps } from "@/lib/queries/member";
import { usePlanningOrganizationId } from "@/lib/queries/planning";
import { sessionTimeZone } from "@/lib/orgTime";
import { t } from "@/lib/i18n";
import {
  acceptShiftSwap,
  claimShiftSwap,
  declineShiftSwap,
  shiftSwapErrorText,
  shiftSwapKindLabel,
  shiftSwapReasonLabel,
  shiftSwapStatusLabel,
  swapAvailability,
  swapAvailabilityMessageKey,
  swapMemberName,
  swapSlotById,
  swapSlotSummary,
  withdrawShiftSwap,
  type SwapPortalVariant,
  type SwapRosterSlice
} from "@/lib/shiftSwaps";

export function ShiftSwapMarketplace({
  periodId,
  shiftGroupId,
  roster,
  teamMemberId,
  groupStatus,
  variant,
  capabilities,
  onChanged
}: {
  periodId: string;
  shiftGroupId: string;
  roster: SwapRosterSlice | null;
  teamMemberId: number | null;
  groupStatus: string | null | undefined;
  variant: SwapPortalVariant;
  capabilities: { team_member_portal: boolean };
  onChanged?: () => void;
}) {
  const { locale } = useLocale();
  const { me } = useSession();
  const queryClient = useQueryClient();
  const organizationId = usePlanningOrganizationId();
  const timeZone = sessionTimeZone(me);
  const swapsQuery = useMemberSwaps(Boolean(periodId && shiftGroupId));
  const rows = (swapsQuery.data ?? []).filter(
    (row) => String(row.planning_period_id) === periodId && String(row.shift_group_id) === shiftGroupId
  );
  const loadError = swapsQuery.isError ? t(locale, "shiftSwapLoadError") : "";
  const [actionError, setActionError] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);
  const availability = swapAvailability({
    variant,
    capabilities,
    teamMemberId,
    shiftGroupId: shiftGroupId || null,
    periodId: periodId || null,
    groupStatus
  });
  const unavailableKey = availability.available ? null : swapAvailabilityMessageKey("marketplace", availability.reason);

  async function refreshSwaps() {
    if (organizationId == null) {
      return;
    }
    await queryClient.invalidateQueries({ queryKey: ["member-swaps", organizationId] });
    await queryClient.invalidateQueries({ queryKey: ["member-home", organizationId] });
  }

  async function runAction(requestId: number, action: () => Promise<unknown>) {
    setBusyId(requestId);
    setActionError("");
    try {
      await action();
      await refreshSwaps();
      onChanged?.();
    } catch (error) {
      setActionError(shiftSwapErrorText(locale, error));
    } finally {
      setBusyId(null);
    }
  }

  const giveaways = rows.filter(
    (row) =>
      row.kind === "giveaway" &&
      row.status === "open" &&
      row.offered_by_team_member_id !== teamMemberId
  );
  const own = rows.filter(
    (row) => row.offered_by_team_member_id === teamMemberId || row.target_team_member_id === teamMemberId
  );

  return (
    <div className="grid gap-4">
      <div>
        <h3 className="text-base font-semibold text-ink">{t(locale, "shiftSwapMarketplaceTitle")}</h3>
        <p className="mt-1 text-sm text-slate-600">{t(locale, "shiftSwapMarketplaceHelp")}</p>
      </div>
      {unavailableKey ? <p className="text-sm text-amber-800">{t(locale, unavailableKey)}</p> : null}
      {loadError ? <p className="text-sm text-rose-800">{loadError}</p> : null}
      {actionError ? (
        <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-900 ring-1 ring-rose-200">{actionError}</p>
      ) : null}
      {availability.available ? (
        <div className="grid gap-4">
          <div className="grid gap-2">
            <h4 className="text-sm font-semibold text-ink">{t(locale, "shiftSwapOpenGiveawaysTitle")}</h4>
            {giveaways.length === 0 ? (
              <p className="text-sm text-slate-500">{t(locale, "shiftSwapOpenGiveawaysEmpty")}</p>
            ) : (
              <div className="grid gap-3">
                {giveaways.map((row) => (
                  <Card key={row.id}>
                    <SwapRequestSummary roster={roster} row={row} />
                    <SwapActionButtons busy={busyId === row.id} onRun={(action) => void runAction(row.id, action)} row={row} />
                  </Card>
                ))}
              </div>
            )}
          </div>
          <div className="grid gap-2">
            <h4 className="text-sm font-semibold text-ink">{t(locale, "shiftSwapOwnRequestsTitle")}</h4>
            {own.length === 0 ? (
              <p className="text-sm text-slate-500">{t(locale, "shiftSwapOwnRequestsEmpty")}</p>
            ) : (
              <div className="grid gap-3">
                {own.map((row) => (
                  <Card key={row.id}>
                    <SwapRequestSummary roster={roster} row={row} />
                    <SwapActionButtons busy={busyId === row.id} onRun={(action) => void runAction(row.id, action)} row={row} />
                  </Card>
                ))}
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

const SWAP_ACTION_LABEL = {
  claim: "shiftSwapClaim",
  accept: "shiftSwapAccept",
  decline: "shiftSwapDecline",
  withdraw: "shiftSwapWithdraw"
} as const;

const SWAP_ACTION_RUN = {
  claim: claimShiftSwap,
  accept: acceptShiftSwap,
  decline: declineShiftSwap,
  withdraw: withdrawShiftSwap
} as const;

function SwapActionButtons({
  row,
  busy,
  onRun
}: {
  row: MemberSwapListItemRead;
  busy: boolean;
  onRun: (action: () => Promise<unknown>) => void;
}) {
  const { locale } = useLocale();
  const order = ["claim", "accept", "decline", "withdraw"] as const;
  const visible = order.filter((action) => row.allowed_actions.includes(action) || action in row.disabled_reasons);
  if (visible.length === 0) {
    return null;
  }
  return (
    <div className="mt-3 grid gap-2">
      {visible.map((action) => {
        const allowed = row.allowed_actions.includes(action);
        const reason = row.disabled_reasons[action];
        const primary = action === "claim" || action === "accept";
        return (
          <button
            key={action}
            className={
              primary
                ? "inline-flex min-h-11 w-full items-center justify-center rounded-xl bg-ink px-4 text-sm font-semibold text-white disabled:opacity-50"
                : "inline-flex min-h-11 w-full items-center justify-center rounded-xl border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 disabled:opacity-50"
            }
            disabled={busy || !allowed}
            onClick={() => {
              if (allowed) {
                onRun(() => SWAP_ACTION_RUN[action](row.id));
              }
            }}
            title={reason ? shiftSwapReasonLabel(locale, reason) : undefined}
            type="button"
          >
            {t(locale, SWAP_ACTION_LABEL[action])}
          </button>
        );
      })}
    </div>
  );
}

function SwapRequestSummary({
  row,
  roster
}: {
  row: MemberSwapListItemRead;
  roster: SwapRosterSlice | null;
}) {
  const { locale } = useLocale();
  const { me } = useSession();
  const timeZone = sessionTimeZone(me);
  const offered = swapSlotById(roster, row.offered_slot_id);
  return (
    <div className="grid gap-1.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">
          {shiftSwapKindLabel(locale, row.kind)}
        </span>
        <span className="rounded-full bg-mint/40 px-2 py-0.5 text-xs font-semibold text-ink">
          {shiftSwapStatusLabel(locale, row.status)}
        </span>
      </div>
      <p className="text-sm font-medium text-ink">{swapSlotSummary(locale, offered, timeZone)}</p>
      <p className="text-sm text-slate-600">
        {t(locale, "shiftSwapOfferedBy")}: {swapMemberName(roster, row.offered_by_team_member_id)}
        {row.target_team_member_id != null
          ? ` · ${t(locale, "shiftSwapTarget")}: ${swapMemberName(roster, row.target_team_member_id)}`
          : ""}
      </p>
    </div>
  );
}
