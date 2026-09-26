"use client";

import { useEffect, useState } from "react";
import { useLocale, useSession } from "@/components/LocaleProvider";
import { sessionTimeZone } from "@/lib/orgTime";
import { inputClass } from "@/components/Card";
import { t } from "@/lib/i18n";
import {
  createShiftSwap,
  fetchEligibleMembers,
  shiftSwapErrorText,
  slotsAssignedToMember,
  swapMemberName,
  swapSlotSummary,
  type ShiftSwapKind,
  type SwapRosterSlice
} from "@/lib/shiftSwaps";

export function ShiftSwapOfferDialog({
  open,
  onClose,
  periodId,
  shiftGroupId,
  offeredSlotId,
  roster,
  onSubmitted
}: {
  open: boolean;
  onClose: () => void;
  periodId: string;
  shiftGroupId: string;
  offeredSlotId: number;
  roster: SwapRosterSlice | null;
  onSubmitted: () => void;
}) {
  const { locale } = useLocale();
  const { me } = useSession();
  const timeZone = sessionTimeZone(me);
  const [kind, setKind] = useState<ShiftSwapKind>("giveaway");
  const [targetId, setTargetId] = useState("");
  const [counterpartySlotId, setCounterpartySlotId] = useState("");
  const [eligibleIds, setEligibleIds] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) {
      return;
    }
    setKind("giveaway");
    setTargetId("");
    setCounterpartySlotId("");
    setError("");
    setEligibleIds([]);
    void fetchEligibleMembers(offeredSlotId, shiftGroupId)
      .then((ids) => setEligibleIds(ids))
      .catch((err) => setError(shiftSwapErrorText(locale, err)));
  }, [open, offeredSlotId, shiftGroupId, locale]);

  if (!open) {
    return null;
  }

  const offeredSlot = roster?.slots.find((row) => row.id === offeredSlotId);
  const partnerSlots =
    kind === "direct" && targetId ? slotsAssignedToMember(roster, Number(targetId)).filter((slot) => slot.id !== offeredSlotId) : [];

  async function submit() {
    setBusy(true);
    setError("");
    try {
      await createShiftSwap({
        planning_period_id: Number(periodId),
        shift_group_id: Number(shiftGroupId),
        kind,
        offered_slot_id: offeredSlotId,
        target_team_member_id: kind === "direct" && targetId ? Number(targetId) : null,
        counterparty_slot_id: kind === "direct" && counterpartySlotId ? Number(counterpartySlotId) : null,
        open_immediately: true
      });
      onSubmitted();
      onClose();
    } catch (err) {
      setError(shiftSwapErrorText(locale, err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-[600] flex items-end justify-center bg-slate-900/40 p-4 sm:items-center sm:p-6"
      onClick={onClose}
    >
      <div
        className="grid w-full max-w-lg gap-4 rounded-2xl bg-white p-5 shadow-lg sm:p-6"
        onClick={(event) => event.stopPropagation()}
      >
        <div>
          <h2 className="text-lg font-semibold text-ink">{t(locale, "shiftSwapOfferTitle")}</h2>
          <p className="mt-1 text-sm text-slate-600">{t(locale, "shiftSwapOfferHelp")}</p>
          {offeredSlot ? <p className="mt-2 text-sm font-medium text-ink">{swapSlotSummary(locale, offeredSlot, timeZone)}</p> : null}
        </div>
        <fieldset className="grid gap-2">
          <legend className="text-sm font-medium text-slate-700">{t(locale, "shiftSwapKindGiveaway")}</legend>
          <label className="flex min-h-11 items-center gap-2 rounded-lg border border-slate-200 px-3 text-sm">
            <input
              checked={kind === "giveaway"}
              name="shift-swap-kind"
              onChange={() => {
                setKind("giveaway");
                setTargetId("");
                setCounterpartySlotId("");
              }}
              type="radio"
            />
            {t(locale, "shiftSwapOfferGiveaway")}
          </label>
          <label className="flex min-h-11 items-center gap-2 rounded-lg border border-slate-200 px-3 text-sm">
            <input
              checked={kind === "direct"}
              name="shift-swap-kind"
              onChange={() => setKind("direct")}
              type="radio"
            />
            {t(locale, "shiftSwapOfferDirect")}
          </label>
        </fieldset>
        {kind === "direct" ? (
          <label className="grid gap-1 text-sm font-medium text-slate-700">
            {t(locale, "shiftSwapPickPartner")}
            <select
              className={inputClass}
              onChange={(event) => {
                setTargetId(event.target.value);
                setCounterpartySlotId("");
              }}
              value={targetId}
            >
              <option value="">{t(locale, "emptyValue")}</option>
              {eligibleIds.map((memberId) => (
                <option key={memberId} value={memberId}>
                  {swapMemberName(roster, memberId)}
                </option>
              ))}
            </select>
            <span className="font-normal text-xs text-slate-500">{t(locale, "shiftSwapPickPartnerHint")}</span>
            {eligibleIds.length === 0 ? (
              <span className="font-normal text-xs text-amber-800">{t(locale, "shiftSwapNoEligiblePartners")}</span>
            ) : null}
          </label>
        ) : null}
        {kind === "direct" && targetId ? (
          <label className="grid gap-1 text-sm font-medium text-slate-700">
            {t(locale, "shiftSwapCounterpartySlot")}
            <select
              className={inputClass}
              onChange={(event) => setCounterpartySlotId(event.target.value)}
              value={counterpartySlotId}
            >
              <option value="">{t(locale, "shiftSwapCounterpartyNone")}</option>
              {partnerSlots.map((slot) => (
                <option key={slot.id} value={slot.id}>
                  {swapSlotSummary(locale, slot, timeZone)}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        {error ? <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-900 ring-1 ring-rose-200">{error}</p> : null}
        <div className="grid gap-2 sm:grid-cols-2">
          <button
            className="inline-flex min-h-11 items-center justify-center rounded-xl border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700"
            onClick={onClose}
            type="button"
          >
            {t(locale, "shiftSwapOfferCancel")}
          </button>
          <button
            className="inline-flex min-h-11 items-center justify-center rounded-xl bg-ink px-4 text-sm font-semibold text-white disabled:opacity-50"
            disabled={busy || (kind === "direct" && !targetId)}
            onClick={() => void submit()}
            type="button"
          >
            {t(locale, "shiftSwapOfferSubmit")}
          </button>
        </div>
      </div>
    </div>
  );
}
