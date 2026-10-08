"use client";

import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarX2, Check, Pencil, Trash2, X } from "lucide-react";
import { Card, Field, inputClass } from "@/components/Card";
import { useLocale, useSession } from "@/components/LocaleProvider";
import { ApiError, apiFetch } from "@/lib/api";
import { apiClient } from "@/lib/api/client";
import type {
  OrganizationHolidayDeleteRead,
  OrganizationHolidayRosterSyncRead,
  OrganizationHolidayWriteRead
} from "@/lib/api/types";
import { t } from "@/lib/i18n";
import { isUserSession } from "@/lib/membershipRouting";
import { rosterSyncSummary } from "@/lib/organizationHolidays";
import { invalidateQueryKeys, organizationHolidayRosterKeys } from "@/lib/queries/invalidation";
import { readData } from "@/lib/queries/read";
import { queryKeys } from "@/lib/queryKeys";

function formatHolidayDate(locale: "de" | "en", isoDate: string): string {
  return new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-GB", {
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
    year: "numeric"
  }).format(new Date(`${isoDate}T12:00:00`));
}

function errorMessage(locale: "de" | "en", error: unknown): string {
  if (error instanceof ApiError && typeof error.detail === "string") {
    return error.detail;
  }
  return t(locale, "organizationHolidaysSaveError");
}

export function OrganizationHolidaysPanel() {
  const { locale } = useLocale();
  const { me } = useSession();
  const organizationId = me && isUserSession(me) ? me.organization_id : null;
  const queryClient = useQueryClient();
  const queryKey = queryKeys.organizationHolidays(organizationId ?? 0);
  const [holidayDate, setHolidayDate] = useState("");
  const [label, setLabel] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editLabel, setEditLabel] = useState("");
  const [message, setMessage] = useState("");
  const [syncLines, setSyncLines] = useState<string[]>([]);

  const holidays = useQuery({
    queryKey,
    enabled: organizationId != null,
    queryFn: async () => readData(await apiClient.GET("/api/v1/organization-holidays"))
  });

  async function refresh(sync?: OrganizationHolidayRosterSyncRead) {
    setSyncLines(sync ? rosterSyncSummary(locale, sync) : []);
    await queryClient.invalidateQueries({ queryKey });
    if (sync && organizationId != null) {
      await invalidateQueryKeys(queryClient, organizationHolidayRosterKeys(organizationId));
    }
  }

  const create = useMutation({
    mutationFn: (body: { holiday_date: string; label: string }) =>
      apiFetch<OrganizationHolidayWriteRead>("/api/v1/organization-holidays", {
        method: "POST",
        body: JSON.stringify(body)
      }),
    onSuccess: async (result) => {
      setHolidayDate("");
      setLabel("");
      setMessage("");
      await refresh(result.roster_sync);
    },
    onError: (error) => setMessage(errorMessage(locale, error))
  });

  const rename = useMutation({
    mutationFn: (args: { id: number; label: string }) =>
      apiFetch<OrganizationHolidayWriteRead>(`/api/v1/organization-holidays/${args.id}`, {
        method: "PATCH",
        body: JSON.stringify({ label: args.label })
      }),
    onSuccess: async () => {
      setEditingId(null);
      setMessage("");
      // A rename never touches rosters.
      await refresh();
    },
    onError: (error) => setMessage(errorMessage(locale, error))
  });

  const remove = useMutation({
    mutationFn: (id: number) =>
      apiFetch<OrganizationHolidayDeleteRead>(`/api/v1/organization-holidays/${id}`, { method: "DELETE" }),
    onSuccess: async (result) => {
      setMessage("");
      await refresh(result.roster_sync);
    },
    onError: (error) => setMessage(errorMessage(locale, error))
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!holidayDate || !label.trim()) return;
    create.mutate({ holiday_date: holidayDate, label: label.trim() });
  }

  const rows = holidays.data ?? [];

  return (
    <Card>
      <div className="flex items-start gap-3">
        <CalendarX2 className="mt-1 shrink-0 text-emerald-700" aria-hidden />
        <div className="min-w-0 flex-1">
          <h2 className="text-xl font-semibold text-ink">{t(locale, "organizationHolidaysTitle")}</h2>
          <p className="mt-1 text-sm text-muted">{t(locale, "organizationHolidaysIntro")}</p>
          <p className="mt-1 text-sm text-muted">{t(locale, "organizationHolidaysSyncHint")}</p>
        </div>
      </div>

      <form className="mt-4 grid gap-3 sm:grid-cols-[12rem_1fr_auto] sm:items-end" onSubmit={submit}>
        <Field label={t(locale, "organizationHolidaysDate")}>
          <input
            type="date"
            className={inputClass}
            required
            value={holidayDate}
            onChange={(event) => setHolidayDate(event.target.value)}
          />
        </Field>
        <Field label={t(locale, "organizationHolidaysLabel")}>
          <input
            className={inputClass}
            required
            maxLength={128}
            placeholder={t(locale, "organizationHolidaysLabelPlaceholder")}
            value={label}
            onChange={(event) => setLabel(event.target.value)}
          />
        </Field>
        <button
          type="submit"
          className="h-10 rounded-lg bg-emerald-700 px-4 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-50"
          disabled={create.isPending}
        >
          {t(locale, "organizationHolidaysAdd")}
        </button>
      </form>

      {syncLines.length > 0 ? (
        <div role="status" className="mt-3 space-y-1 text-sm text-ink">
          {syncLines.map((line) => (
            <p key={line}>{line}</p>
          ))}
        </div>
      ) : null}
      {message ? (
        <p role="alert" className="mt-3 text-sm text-danger">
          {message}
        </p>
      ) : null}
      {holidays.isError ? <p className="mt-3 text-sm text-danger">{t(locale, "organizationHolidaysLoadError")}</p> : null}

      {holidays.isSuccess && rows.length === 0 ? (
        <p className="mt-4 text-sm text-muted">{t(locale, "organizationHolidaysEmpty")}</p>
      ) : null}
      {rows.length > 0 ? (
        <table className="mt-4 w-full text-sm">
          <thead>
            <tr className="border-b border-default text-left text-xs uppercase tracking-wide text-muted">
              <th className="py-2 pr-4 font-semibold">{t(locale, "organizationHolidaysDate")}</th>
              <th className="py-2 pr-4 font-semibold">{t(locale, "organizationHolidaysLabel")}</th>
              <th className="py-2 text-right font-semibold">
                <span className="sr-only">{t(locale, "organizationHolidaysActions")}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-b border-default last:border-0">
                <td className="py-2 pr-4 tabular-nums text-ink">{formatHolidayDate(locale, row.holiday_date)}</td>
                <td className="py-2 pr-4">
                  {editingId === row.id ? (
                    <input
                      className={inputClass}
                      aria-label={t(locale, "organizationHolidaysLabel")}
                      maxLength={128}
                      value={editLabel}
                      autoFocus
                      onChange={(event) => setEditLabel(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" && editLabel.trim()) {
                          rename.mutate({ id: row.id, label: editLabel.trim() });
                        }
                        if (event.key === "Escape") setEditingId(null);
                      }}
                    />
                  ) : (
                    <span className="text-ink">{row.label}</span>
                  )}
                </td>
                <td className="py-2 text-right">
                  <div className="inline-flex gap-1">
                    {editingId === row.id ? (
                      <>
                        <button
                          type="button"
                          className="rounded-lg p-2 text-emerald-700 hover:bg-slate-100 disabled:opacity-50"
                          aria-label={t(locale, "save")}
                          disabled={!editLabel.trim() || rename.isPending}
                          onClick={() => rename.mutate({ id: row.id, label: editLabel.trim() })}
                        >
                          <Check size={16} />
                        </button>
                        <button
                          type="button"
                          className="rounded-lg p-2 text-slate-600 hover:bg-slate-100"
                          aria-label={t(locale, "organizationHolidaysCancel")}
                          onClick={() => setEditingId(null)}
                        >
                          <X size={16} />
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        className="rounded-lg p-2 text-slate-600 hover:bg-slate-100"
                        aria-label={t(locale, "organizationHolidaysRename")}
                        onClick={() => {
                          setEditingId(row.id);
                          setEditLabel(row.label);
                        }}
                      >
                        <Pencil size={16} />
                      </button>
                    )}
                    <button
                      type="button"
                      className="rounded-lg p-2 text-danger hover:bg-slate-100 disabled:opacity-50"
                      aria-label={t(locale, "organizationHolidaysDelete")}
                      disabled={remove.isPending}
                      onClick={() => remove.mutate(row.id)}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </Card>
  );
}
