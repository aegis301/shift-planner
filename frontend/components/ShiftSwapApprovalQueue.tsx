"use client";

import { useCallback, useEffect, useState } from "react";
import { Card } from "@/components/Card";
import { useLocale } from "@/components/LocaleProvider";
import { t } from "@/lib/i18n";
import {
  applyShiftSwap,
  approveShiftSwap,
  assigneeForSlot,
  listShiftSwaps,
  rejectShiftSwap,
  shiftSwapErrorText,
  shiftSwapFindingText,
  shiftSwapKindLabel,
  shiftSwapStatusLabel,
  swapMemberName,
  swapSlotById,
  swapSlotSummary,
  type ShiftSwapRequestRead,
  type SwapRosterSlice
} from "@/lib/shiftSwaps";

const QUEUE_STATUSES = new Set(["claimed", "accepted", "approved"]);

export function ShiftSwapApprovalQueue({
  periodId,
  shiftGroupId,
  roster,
  reloadToken,
  onApplied
}: {
  periodId: string;
  shiftGroupId: string;
  roster: SwapRosterSlice | null;
  reloadToken: number;
  onApplied: () => void;
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
      setRows(next.filter((row) => QUEUE_STATUSES.has(row.status)));
      setLoadError("");
    } catch {
      setRows([]);
      setLoadError(t(locale, "shiftSwapLoadError"));
    }
  }, [locale, periodId, shiftGroupId]);

  useEffect(() => {
    void reload();
  }, [reload, reloadToken]);

  async function run(requestId: number, action: () => Promise<unknown>, applied = false) {
    setBusyId(requestId);
    setActionError("");
    try {
      await action();
      await reload();
      if (applied) {
        onApplied();
      }
    } catch (error) {
      setActionError(shiftSwapErrorText(locale, error));
      await reload();
    } finally {
      setBusyId(null);
    }
  }

  async function approveAndApply(row: ShiftSwapRequestRead) {
    setBusyId(row.id);
    setActionError("");
    try {
      if (row.status !== "approved") {
        await approveShiftSwap(row.id);
      }
      await applyShiftSwap(row.id);
      await reload();
      onApplied();
    } catch (error) {
      setActionError(shiftSwapErrorText(locale, error));
      await reload();
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="grid gap-3">
      <div>
        <h2 className="text-lg font-semibold text-ink">{t(locale, "shiftSwapQueueTitle")}</h2>
        <p className="mt-1 text-sm text-slate-600">{t(locale, "shiftSwapQueueHelp")}</p>
      </div>
      {loadError ? <p className="text-sm text-rose-800">{loadError}</p> : null}
      {actionError ? (
        <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-900 ring-1 ring-rose-200">{actionError}</p>
      ) : null}
      {rows.length === 0 && !loadError ? (
        <p className="text-sm text-slate-500">{t(locale, "shiftSwapQueueEmpty")}</p>
      ) : (
        <div className="grid gap-3">
          {rows.map((row) => {
            const offered = swapSlotById(roster, row.offered_slot_id);
            const counterpart = swapSlotById(roster, row.counterparty_slot_id);
            const offeredBefore = assigneeForSlot(roster, row.offered_slot_id);
            const counterpartBefore =
              row.counterparty_slot_id != null ? assigneeForSlot(roster, row.counterparty_slot_id) : null;
            return (
              <Card key={row.id}>
                <div className="grid gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">
                      {shiftSwapKindLabel(locale, row.kind)}
                    </span>
                    <span className="rounded-full bg-mint/40 px-2 py-0.5 text-xs font-semibold text-ink">
                      {shiftSwapStatusLabel(locale, row.status)}
                    </span>
                  </div>
                  <RosterChangeBlock
                    afterId={row.target_team_member_id}
                    beforeId={offeredBefore}
                    label={t(locale, "shiftSwapChangeOffered")}
                    roster={roster}
                    slotLabel={swapSlotSummary(locale, offered)}
                  />
                  {row.counterparty_slot_id != null ? (
                    <RosterChangeBlock
                      afterId={row.offered_by_team_member_id}
                      beforeId={counterpartBefore}
                      label={t(locale, "shiftSwapChangeCounterparty")}
                      roster={roster}
                      slotLabel={swapSlotSummary(locale, counterpart)}
                    />
                  ) : null}
                  <div className="grid gap-1">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      {t(locale, "shiftSwapWarningsTitle")}
                    </p>
                    {row.warning_findings.length === 0 ? (
                      <p className="text-sm text-slate-500">{t(locale, "shiftSwapNoWarnings")}</p>
                    ) : (
                      <ul className="grid gap-1">
                        {row.warning_findings.map((finding, index) => (
                          <li
                            className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-950 ring-1 ring-amber-200"
                            key={`${finding.code}-${index}`}
                          >
                            {shiftSwapFindingText(locale, finding)}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {row.status === "approved" ? (
                      <button
                        className="inline-flex min-h-11 w-full items-center justify-center rounded-xl bg-ink px-4 text-sm font-semibold text-white disabled:opacity-50"
                        disabled={busyId === row.id}
                        onClick={() => void run(row.id, () => applyShiftSwap(row.id), true)}
                        type="button"
                      >
                        {t(locale, "shiftSwapApply")}
                      </button>
                    ) : (
                      <button
                        className="inline-flex min-h-11 w-full items-center justify-center rounded-xl bg-ink px-4 text-sm font-semibold text-white disabled:opacity-50"
                        disabled={busyId === row.id}
                        onClick={() => void approveAndApply(row)}
                        type="button"
                      >
                        {t(locale, "shiftSwapApproveAndApply")}
                      </button>
                    )}
                    <button
                      className="inline-flex min-h-11 w-full items-center justify-center rounded-xl border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 disabled:opacity-50"
                      disabled={busyId === row.id}
                      onClick={() => void run(row.id, () => rejectShiftSwap(row.id))}
                      type="button"
                    >
                      {t(locale, "shiftSwapReject")}
                    </button>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </section>
  );
}

function RosterChangeBlock({
  label,
  slotLabel,
  beforeId,
  afterId,
  roster
}: {
  label: string;
  slotLabel: string;
  beforeId: number | null;
  afterId: number | null;
  roster: SwapRosterSlice | null;
}) {
  const { locale } = useLocale();
  const before = beforeId != null ? swapMemberName(roster, beforeId) : t(locale, "shiftSwapUnassigned");
  const after = afterId != null ? swapMemberName(roster, afterId) : t(locale, "shiftSwapUnassigned");
  return (
    <div className="grid gap-1 rounded-lg bg-slate-50 px-3 py-2 ring-1 ring-slate-200">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className="text-sm font-medium text-ink">{slotLabel}</p>
      <p className="text-sm text-slate-700">
        {t(locale, "shiftSwapBefore")}: {before}
        <span className="px-2 text-slate-400">→</span>
        {t(locale, "shiftSwapAfter")}: {after}
      </p>
    </div>
  );
}
