"use client";

import { FormEvent, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Field, inputClass } from "@/components/Card";
import { useLocale, useSession } from "@/components/LocaleProvider";
import { sessionTimeZone } from "@/lib/orgTime";
import { ApiError, apiFetch } from "@/lib/api";
import {
  bandLabelKey,
  formatMinutes,
  fromDatetimeLocalValue,
  isCapturableSlot,
  isSlotEnded,
  isSlotRunning,
  kindForCategory,
  slotTitle,
  toDatetimeLocalValue,
  utilizationPercentLabel,
  type DutyActivitySlotRef,
} from "@/lib/dutyActivity";
import { formatPlanningDate, formatShiftTimeRange } from "@/lib/shiftDisplay";
import { t } from "@/lib/i18n";
import { queryKeys } from "@/lib/queryKeys";
import { useDutyUtilization, usePlanningOrganizationId } from "@/lib/queries/planning";

function DutyActivitySummary({ rosterSlotId }: { rosterSlotId: number }) {
  const { locale } = useLocale();
  const summaryQuery = useDutyUtilization(rosterSlotId, true);
  const summary = summaryQuery.data ?? null;

  if (!summary) {
    return null;
  }

  return (
    <p className="text-sm text-slate-700">
      {t(locale, "dutyActivitySummary", {
        minutes: formatMinutes(locale, summary.worked_minutes),
        percent: utilizationPercentLabel(summary.utilization_percent),
        band: summary.band ? t(locale, bandLabelKey(summary.band)) : "—"
      })}
      {summary.exceeds_on_call_threshold ? ` · ${t(locale, "dutyActivityExceedsThreshold")}` : ""}
    </p>
  );
}

function DutyActivityRetrospective({
  slot,
  onSaved
}: {
  slot: DutyActivitySlotRef;
  onSaved: () => void;
}) {
  const { locale } = useLocale();
  const { me } = useSession();
  const queryClient = useQueryClient();
  const organizationId = usePlanningOrganizationId();
  const timeZone = sessionTimeZone(me);
  const kind = kindForCategory(slot.category);
  const [startedAt, setStartedAt] = useState(slot.starts_at ? toDatetimeLocalValue(slot.starts_at, timeZone) : "");
  const [endedAt, setEndedAt] = useState(slot.ends_at ? toDatetimeLocalValue(slot.ends_at, timeZone) : "");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!kind) {
      return;
    }
    setMessage("");
    setBusy(true);
    try {
      await apiFetch("/api/v1/duty-activity", {
        method: "POST",
        body: JSON.stringify({
          roster_slot_id: slot.roster_slot_id,
          kind,
          started_at: fromDatetimeLocalValue(startedAt, timeZone),
          ended_at: fromDatetimeLocalValue(endedAt, timeZone)
        })
      });
      if (organizationId != null) {
        await queryClient.invalidateQueries({
          queryKey: queryKeys.dutyUtilization(organizationId, slot.roster_slot_id)
        });
      }
      onSaved();
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : t(locale, "dutyActivitySaveError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="mt-3 grid gap-3" onSubmit={save}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t(locale, "dutyActivityStartedAt")}>
          <input
            className={`${inputClass} min-w-0`}
            onChange={(event) => setStartedAt(event.target.value)}
            required
            type="datetime-local"
            value={startedAt}
          />
        </Field>
        <Field label={t(locale, "dutyActivityEndedAt")}>
          <input
            className={`${inputClass} min-w-0`}
            onChange={(event) => setEndedAt(event.target.value)}
            required
            type="datetime-local"
            value={endedAt}
          />
        </Field>
      </div>
      <button
        className="inline-flex h-11 items-center justify-center rounded-lg bg-ink px-4 text-sm font-semibold text-white"
        disabled={busy}
        type="submit"
      >
        {t(locale, "dutyActivityRecordRetrospective")}
      </button>
      {message ? <p className="text-sm text-rose-700">{message}</p> : null}
    </form>
  );
}

export function DutyActivityShiftList({ slots }: { slots: DutyActivitySlotRef[] }) {
  const { locale } = useLocale();
  const { me } = useSession();
  const timeZone = sessionTimeZone(me);
  const [formGeneration, setFormGeneration] = useState(0);
  const capturable = slots.filter(isCapturableSlot);

  if (capturable.length === 0) {
    return <p className="text-sm text-slate-500">{t(locale, "dutyActivityNoDuties")}</p>;
  }

  return (
    <div className="grid gap-3">
      {capturable.map((slot) => {
        const running = isSlotRunning(slot);
        const ended = isSlotEnded(slot);
        return (
          <article
            key={slot.roster_slot_id}
            className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
          >
            <h3 className="text-base font-semibold text-ink">{slotTitle(slot) || t(locale, "dutyActivityLiveTitle")}</h3>
            <p className="mt-1 text-sm text-slate-600">
              {formatPlanningDate(locale, slot.slot_date)}
              {slot.starts_at && slot.ends_at ? ` · ${formatShiftTimeRange(slot.starts_at, slot.ends_at, timeZone)}` : ""}
            </p>
            <div className="mt-2">
              <DutyActivitySummary rosterSlotId={slot.roster_slot_id} />
            </div>
            {running ? null : ended ? (
              <DutyActivityRetrospective
                key={`${slot.roster_slot_id}-${formGeneration}`}
                slot={slot}
                onSaved={() => setFormGeneration((value) => value + 1)}
              />
            ) : null}
          </article>
        );
      })}
    </div>
  );
}
