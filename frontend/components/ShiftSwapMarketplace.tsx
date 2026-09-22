"use client";

import { useCallback, useEffect, useState } from "react";
import { Card } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";
import { t } from "@/lib/i18n";
import {
  acceptShiftSwap,
  claimShiftSwap,
  declineShiftSwap,
  listShiftSwaps,
  shiftSwapErrorText,
  shiftSwapFindingText,
  shiftSwapKindLabel,
  shiftSwapStatusLabel,
  swapMemberName,
  swapSlotById,
  swapSlotSummary,
  withdrawShiftSwap,
  type ShiftSwapRequestRead,
  type SwapRosterSlice
} from "@/lib/shiftSwaps";

export function ShiftSwapMarketplace({
  periodId,
  shiftGroupId,
  roster,
  teamMemberId,
  reloadToken,
  onChanged
}: {
  periodId: string;
  shiftGroupId: string;
  roster: SwapRosterSlice | null;
  teamMemberId: number;
  reloadToken: number;
  onChanged?: () => void;
}) {
  const { locale } = useLocale();
  const [rows, setRows] = useState<ShiftSwapRequestRead[]>([]);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  const reload = useCallback(async () => {
    if (!periodId || !shiftGroupId) {
      setRows([]);
      return;
    }
    try {
      const next = await listShiftSwaps(periodId, shiftGroupId);
      setRows(next);
      setLoadError("");
    } catch {
      setRows([]);
      setLoadError(t(locale, "shiftSwapLoadError"));
    }
  }, [locale, periodId, shiftGroupId]);

  useEffect(() => {
    void reload();
  }, [reload, reloadToken]);

  async function runAction(requestId: number, action: () => Promise<unknown>) {
    setBusyId(requestId);
    setActionError("");
    try {
      await action();
      await reload();
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
      {loadError ? <p className="text-sm text-rose-800">{loadError}</p> : null}
      {actionError ? (
        <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-900 ring-1 ring-rose-200">{actionError}</p>
      ) : null}
      <div className="grid gap-2">
        <h4 className="text-sm font-semibold text-ink">{t(locale, "shiftSwapOpenGiveawaysTitle")}</h4>
        {giveaways.length === 0 ? (
          <p className="text-sm text-slate-500">{t(locale, "shiftSwapOpenGiveawaysEmpty")}</p>
        ) : (
          <div className="grid gap-3">
            {giveaways.map((row) => (
              <Card key={row.id}>
                <SwapRequestSummary roster={roster} row={row} />
                <button
                  className="mt-3 inline-flex min-h-11 w-full items-center justify-center rounded-xl bg-ink px-4 text-sm font-semibold text-white disabled:opacity-50"
                  disabled={busyId === row.id}
                  onClick={() => void runAction(row.id, () => claimShiftSwap(row.id))}
                  type="button"
                >
                  {t(locale, "shiftSwapClaim")}
                </button>
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
            {own.map((row) => {
              const isOfferer = row.offered_by_team_member_id === teamMemberId;
              const isTarget = row.target_team_member_id === teamMemberId;
              const canWithdraw = isOfferer && !["applied", "withdrawn", "rejected", "expired"].includes(row.status);
              const canAccept = isTarget && row.status === "targeted";
              return (
                <Card key={row.id}>
                  <SwapRequestSummary roster={roster} row={row} />
                  <div className="mt-3 grid gap-2">
                    {canAccept ? (
                      <button
                        className="inline-flex min-h-11 w-full items-center justify-center rounded-xl bg-ink px-4 text-sm font-semibold text-white disabled:opacity-50"
                        disabled={busyId === row.id}
                        onClick={() => void runAction(row.id, () => acceptShiftSwap(row.id))}
                        type="button"
                      >
                        {t(locale, "shiftSwapAccept")}
                      </button>
                    ) : null}
                    {canAccept ? (
                      <button
                        className="inline-flex min-h-11 w-full items-center justify-center rounded-xl border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 disabled:opacity-50"
                        disabled={busyId === row.id}
                        onClick={() => void runAction(row.id, () => declineShiftSwap(row.id))}
                        type="button"
                      >
                        {t(locale, "shiftSwapDecline")}
                      </button>
                    ) : null}
                    {canWithdraw ? (
                      <button
                        className="inline-flex min-h-11 w-full items-center justify-center rounded-xl border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 disabled:opacity-50"
                        disabled={busyId === row.id}
                        onClick={() => void runAction(row.id, () => withdrawShiftSwap(row.id))}
                        type="button"
                      >
                        {t(locale, "shiftSwapWithdraw")}
                      </button>
                    ) : null}
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function SwapRequestSummary({
  row,
  roster
}: {
  row: ShiftSwapRequestRead;
  roster: SwapRosterSlice | null;
}) {
  const { locale } = useLocale();
  const offered = swapSlotById(roster, row.offered_slot_id);
  const counterparty = swapSlotById(roster, row.counterparty_slot_id);
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
      <p className="text-sm font-medium text-ink">{swapSlotSummary(locale, offered)}</p>
      <p className="text-sm text-slate-600">
        {t(locale, "shiftSwapOfferedBy")}: {swapMemberName(roster, row.offered_by_team_member_id)}
        {row.target_team_member_id != null
          ? ` · ${t(locale, "shiftSwapTarget")}: ${swapMemberName(roster, row.target_team_member_id)}`
          : ""}
      </p>
      {counterparty ? (
        <p className="text-sm text-slate-600">
          {t(locale, "shiftSwapChangeCounterparty")}: {swapSlotSummary(locale, counterparty)}
        </p>
      ) : null}
      {row.warning_findings.length > 0 ? (
        <ul className="grid gap-1">
          {row.warning_findings.map((finding, index) => (
            <li className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-950 ring-1 ring-amber-200" key={`${finding.code}-${index}`}>
              {shiftSwapFindingText(locale, finding)}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
