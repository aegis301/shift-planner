"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import {
  DUTY_ACTIVITY_REASON_CODES,
  type DutyActivityEpisode,
  type DutyActivitySlotRef,
  isSlotRunning,
  kindForCategory,
  reasonLabelKey,
  runningCapturableSlot
} from "@/lib/dutyActivity";
import { useLocale } from "@/components/LocaleProvider";
import { t } from "@/lib/i18n";

type Purpose = {
  purpose_statement: string;
  acknowledged: boolean;
};

function isRetryable(error: unknown): boolean {
  if (error instanceof ApiError) {
    return error.status >= 500;
  }
  return true;
}

async function withRetry<T>(run: () => Promise<T>): Promise<T> {
  let lastError: unknown;
  for (let attempt = 0; attempt < 6; attempt += 1) {
    try {
      return await run();
    } catch (error) {
      lastError = error;
      if (!isRetryable(error) || attempt === 5) {
        throw error;
      }
      await new Promise((resolve) => setTimeout(resolve, 700));
    }
  }
  throw lastError;
}

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return fallback;
}

export function DutyActivityControl({
  slot,
  onChanged
}: {
  slot: DutyActivitySlotRef;
  onChanged?: () => void;
}) {
  const { locale } = useLocale();
  const kind = kindForCategory(slot.category);
  const [purpose, setPurpose] = useState<Purpose | null>(null);
  const [episode, setEpisode] = useState<DutyActivityEpisode | null>(null);
  const [busy, setBusy] = useState(false);
  const [pendingStartAt, setPendingStartAt] = useState<string | null>(null);
  const [pendingStopAt, setPendingStopAt] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [askReason, setAskReason] = useState(false);
  const running = isSlotRunning(slot);

  const reload = useCallback(async () => {
    const [nextPurpose, rows] = await Promise.all([
      apiFetch<Purpose>("/api/v1/duty-activity/purpose"),
      apiFetch<DutyActivityEpisode[]>(`/api/v1/duty-activity?roster_slot_id=${slot.roster_slot_id}`)
    ]);
    setPurpose(nextPurpose);
    const open = rows.find((row) => row.ended_at == null) ?? null;
    setEpisode(open);
  }, [slot.roster_slot_id]);

  useEffect(() => {
    void reload().catch(() => {
      setMessage(t(locale, "dutyActivitySaveError"));
    });
  }, [locale, reload]);

  async function acknowledge() {
    setMessage("");
    setBusy(true);
    try {
      const next = await apiFetch<Purpose>("/api/v1/duty-activity/purpose/acknowledge", { method: "POST" });
      setPurpose(next);
    } catch (error) {
      setMessage(errorMessage(error, t(locale, "dutyActivitySaveError")));
    } finally {
      setBusy(false);
    }
  }

  async function start() {
    if (!kind) {
      return;
    }
    const startedAt = pendingStartAt ?? new Date().toISOString();
    setPendingStartAt(startedAt);
    setMessage("");
    setBusy(true);
    try {
      const row = await withRetry(() =>
        apiFetch<DutyActivityEpisode>("/api/v1/duty-activity", {
          method: "POST",
          body: JSON.stringify({
            roster_slot_id: slot.roster_slot_id,
            kind,
            started_at: startedAt
          })
        })
      );
      setEpisode(row);
      setPendingStartAt(null);
      onChanged?.();
    } catch (error) {
      setMessage(errorMessage(error, t(locale, "dutyActivitySaveError")));
    } finally {
      setBusy(false);
    }
  }

  async function stop() {
    if (episode == null) {
      return;
    }
    const endedAt = pendingStopAt ?? new Date().toISOString();
    setPendingStopAt(endedAt);
    setMessage("");
    setBusy(true);
    try {
      const row = await withRetry(() =>
        apiFetch<DutyActivityEpisode>(`/api/v1/duty-activity/${episode.id}`, {
          method: "PATCH",
          body: JSON.stringify({ ended_at: endedAt })
        })
      );
      setEpisode(null);
      setPendingStopAt(null);
      setAskReason(true);
      onChanged?.();
      if (row.ended_at == null) {
        setEpisode(row);
      }
    } catch (error) {
      setMessage(errorMessage(error, t(locale, "dutyActivitySaveError")));
    } finally {
      setBusy(false);
    }
  }

  async function saveReason(code: string) {
    if (episode?.id == null && pendingStopAt == null) {
      const rows = await apiFetch<DutyActivityEpisode[]>(
        `/api/v1/duty-activity?roster_slot_id=${slot.roster_slot_id}`
      );
      const latest = rows.at(-1);
      if (!latest) {
        setAskReason(false);
        return;
      }
      await apiFetch(`/api/v1/duty-activity/${latest.id}`, {
        method: "PATCH",
        body: JSON.stringify({ reason: { code } })
      });
      setAskReason(false);
      onChanged?.();
      return;
    }
    const rows = await apiFetch<DutyActivityEpisode[]>(
      `/api/v1/duty-activity?roster_slot_id=${slot.roster_slot_id}`
    );
    const latest = rows.at(-1);
    if (!latest) {
      setAskReason(false);
      return;
    }
    try {
      await apiFetch(`/api/v1/duty-activity/${latest.id}`, {
        method: "PATCH",
        body: JSON.stringify({ reason: { code } })
      });
      setAskReason(false);
      onChanged?.();
    } catch (error) {
      setMessage(errorMessage(error, t(locale, "dutyActivitySaveError")));
    }
  }

  if (!kind || (!running && episode == null && !askReason)) {
    return null;
  }

  return (
    <div className="rounded-xl bg-mint/20 p-4 ring-1 ring-mint/40">
      <p className="text-sm font-semibold text-ink">{t(locale, "dutyActivityLiveTitle")}</p>
      <p className="mt-1 text-sm text-slate-700">{t(locale, "dutyActivityLiveHelp")}</p>
      {purpose && !purpose.acknowledged ? (
        <div className="mt-3 grid gap-3">
          <p className="whitespace-pre-wrap text-sm text-slate-800">
            {purpose.purpose_statement.trim()
              ? purpose.purpose_statement
              : t(locale, "dutyActivityPurposeEmpty")}
          </p>
          <button
            className="inline-flex min-h-14 w-full items-center justify-center rounded-xl bg-ink px-4 text-base font-semibold text-white"
            disabled={busy}
            onClick={() => void acknowledge()}
            type="button"
          >
            {t(locale, "dutyActivityPurposeAcknowledge")}
          </button>
        </div>
      ) : episode != null ? (
        <button
          className="mt-4 inline-flex min-h-14 w-full items-center justify-center rounded-xl bg-ink px-4 text-base font-semibold text-white"
          disabled={busy}
          onClick={() => void stop()}
          type="button"
        >
          {t(locale, "dutyActivityStop")}
        </button>
      ) : running ? (
        <button
          className="mt-4 inline-flex min-h-14 w-full items-center justify-center rounded-xl bg-ink px-4 text-base font-semibold text-white"
          disabled={busy}
          onClick={() => void start()}
          type="button"
        >
          {t(locale, "dutyActivityStart")}
        </button>
      ) : null}
      {askReason ? (
        <div className="mt-3 rounded-lg bg-white p-3 ring-1 ring-slate-200">
          <p className="text-sm font-medium text-slate-800">{t(locale, "dutyActivityReasonPrompt")}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {DUTY_ACTIVITY_REASON_CODES.map((code) => (
              <button
                key={code}
                className="inline-flex h-10 items-center rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold"
                onClick={() => void saveReason(code)}
                type="button"
              >
                {t(locale, reasonLabelKey(code))}
              </button>
            ))}
            <button
              className="inline-flex h-10 items-center rounded-lg px-3 text-sm font-semibold text-slate-600"
              onClick={() => setAskReason(false)}
              type="button"
            >
              {t(locale, "dutyActivityReasonSkip")}
            </button>
          </div>
        </div>
      ) : null}
      {message ? <p className="mt-2 text-sm text-rose-700">{message}</p> : null}
    </div>
  );
}

export function DutyActivityLiveBanner({ slots }: { slots: DutyActivitySlotRef[] }) {
  const running = runningCapturableSlot(slots);
  if (!running) {
    return null;
  }
  return <DutyActivityControl slot={running} />;
}
