import { useQuery } from "@tanstack/react-query";
import { FairnessMemberRollingSummary } from "@/components/FairnessAccountsPanel";
import { apiClient } from "@/lib/api/client";
import type { FairnessAccountsRead, SlotCandidatesRead } from "@/lib/api/types";
import { t, type Locale } from "@/lib/i18n";
import { formatShiftTimeRange } from "@/lib/shiftDisplay";
import {
  fairnessValueForMember,
  formatFairnessDeviation,
  indexFairnessMembers,
  relevantFairnessDimension
} from "@/lib/fairness";
import { workloadRowForMember } from "@/lib/rosterWorkload";
import type { RosterMatrix } from "@/components/RosterMatrixEditor";

type Warning = {
  code: string;
  severity?: "info" | "warning" | "error";
  message: string;
  team_member_id: number | null;
  date: string | null;
};

export function PlanningInspector({
  locale,
  periodId,
  shiftGroupId,
  slotId,
  memberId,
  day,
  findingKey,
  roster,
  warnings,
  fairness,
  timeZone,
  canAssign,
  onAssign,
  onSelectMember,
  onSelectSlot
}: {
  locale: Locale;
  periodId: string;
  shiftGroupId: string;
  slotId: string;
  memberId: string;
  day: string;
  findingKey: string;
  roster: RosterMatrix | null;
  warnings: Warning[];
  fairness: FairnessAccountsRead | null;
  timeZone: string;
  canAssign: boolean;
  onAssign: (memberId: number) => void;
  onSelectMember: (memberId: string) => void;
  onSelectSlot: (slotId: string) => void;
}) {
  const candidates = useQuery({
    queryKey: ["slot-candidates", periodId, slotId, shiftGroupId],
    enabled: slotId !== "" && periodId !== "" && shiftGroupId !== "",
    queryFn: async () => {
      const response = await apiClient.GET("/api/v1/roster-matrix/{planning_period_id}/slots/{roster_slot_id}/candidates", {
        params: {
          path: { planning_period_id: Number(periodId), roster_slot_id: Number(slotId) },
          query: { shift_group_id: Number(shiftGroupId) }
        }
      });
      return response.data as SlotCandidatesRead;
    }
  });
  if (findingKey) {
    const [code, member, date] = findingKey.split("|");
    const warning = warnings.find((row) => row.code === code && String(row.team_member_id ?? "") === member && (row.date ?? "") === date);
    return (
      <div className="grid gap-3 text-sm">
        <h3 className="font-semibold text-ink">{t(locale, "inspectorFinding")}</h3>
        {warning ? (
          <>
            <p className="font-mono text-xs text-slate-500">{warning.code}</p>
            <p>{warning.message}</p>
            {warning.team_member_id != null ? (
              <button className="text-left font-semibold text-ink" type="button" onClick={() => onSelectMember(String(warning.team_member_id))}>
                {t(locale, "inspectorMember")} {warning.team_member_id}
              </button>
            ) : null}
          </>
        ) : (
          <p className="text-slate-500">{t(locale, "noData")}</p>
        )}
      </div>
    );
  }
  if (slotId && candidates.data) {
    const slot = roster?.slots.find((row) => String(row.id) === slotId);
    const fairnessIndex = indexFairnessMembers(fairness);
    const dimension = slot
      ? relevantFairnessDimension(
          {
            slot_date: slot.slot_date,
            starts_at: slot.starts_at,
            ends_at: slot.ends_at,
            day_class: slot.day_class,
            category: slot.category
          },
          fairness?.dimensions ?? [],
          timeZone
        )
      : undefined;
    return (
      <div className="grid gap-4 text-sm">
        <div>
          <h3 className="font-semibold text-ink">{candidates.data.template_name}</h3>
          <p className="text-slate-600">
            {candidates.data.slot_date} · {candidates.data.variant_label} · {candidates.data.day_class}
          </p>
          <p className="text-slate-600">
            {formatShiftTimeRange(candidates.data.starts_at ?? null, candidates.data.ends_at ?? null, timeZone)}
          </p>
        </div>
        <CandidateGroup locale={locale} title={t(locale, "candidatesOk")} rows={candidates.data.candidates.filter((row) => row.status === "ok")} dimension={dimension} fairnessIndex={fairnessIndex} canAssign={canAssign} onAssign={onAssign} />
        <CandidateGroup locale={locale} title={t(locale, "candidatesWarning")} rows={candidates.data.candidates.filter((row) => row.status === "warning")} dimension={dimension} fairnessIndex={fairnessIndex} canAssign={canAssign} onAssign={onAssign} />
        <CandidateGroup locale={locale} title={t(locale, "candidatesBlocked")} rows={candidates.data.candidates.filter((row) => row.status === "blocked")} dimension={dimension} fairnessIndex={fairnessIndex} canAssign={canAssign} onAssign={onAssign} />
        <CandidateGroup locale={locale} title={t(locale, "candidatesIneligible")} rows={candidates.data.candidates.filter((row) => row.status === "ineligible")} dimension={dimension} fairnessIndex={fairnessIndex} canAssign={canAssign} onAssign={onAssign} />
        <section>
          <h4 className="font-semibold text-ink">{t(locale, "inspectorHistory")}</h4>
          <ul className="mt-1 grid gap-1 text-xs text-slate-600">
            {(candidates.data.assignment_history ?? []).map((row) => (
              <li key={row.id}>
                {row.action} · {row.actor}
              </li>
            ))}
          </ul>
        </section>
        <section>
          <h4 className="font-semibold text-ink">{t(locale, "inspectorSwaps")}</h4>
          <ul className="mt-1 grid gap-1 text-xs text-slate-600">
            {(candidates.data.swap_requests ?? []).map((row) => (
              <li key={row.id}>
                {row.kind} · {row.status}
              </li>
            ))}
          </ul>
        </section>
      </div>
    );
  }
  if (memberId && roster) {
    const id = Number(memberId);
    const row = workloadRowForMember(roster, warnings, id);
    return (
      <div className="grid gap-3 text-sm">
        <h3 className="font-semibold text-ink">{row?.name ?? t(locale, "inspectorMember")}</h3>
        <FairnessMemberRollingSummary accounts={fairness} teamMemberId={id} />
        {row ? (
          <dl className="grid grid-cols-2 gap-1">
            <dt>{t(locale, "employment")}</dt>
            <dd className="text-right tabular-nums">{row.employmentPercentage}%</dd>
            <dt>{t(locale, "totalShifts")}</dt>
            <dd className="text-right tabular-nums">{row.total}</dd>
          </dl>
        ) : null}
        <div id="workbench-member-note" />
      </div>
    );
  }
  if (day && roster) {
    const slots = roster.slots.filter((slot) => slot.slot_date === day);
    return (
      <div className="grid gap-2 text-sm">
        <h3 className="font-semibold text-ink">{day}</h3>
        {slots.map((slot) => {
          const assignment = roster.assignments.find((row) => row.roster_slot_id === slot.id);
          return (
            <button key={slot.id} className="rounded-md border border-slate-200 px-2 py-2 text-left" type="button" onClick={() => onSelectSlot(String(slot.id))}>
              {slot.template_name ?? slot.label} · {assignment ? t(locale, "candidateAssign") : t(locale, "emptyValue")}
            </button>
          );
        })}
      </div>
    );
  }
  return <p className="text-sm text-slate-600">{t(locale, "inspectorEmpty")}</p>;
}

function CandidateGroup({
  locale,
  title,
  rows,
  dimension,
  fairnessIndex,
  canAssign,
  onAssign
}: {
  locale: Locale;
  title: string;
  rows: SlotCandidatesRead["candidates"];
  dimension: ReturnType<typeof relevantFairnessDimension>;
  fairnessIndex: ReturnType<typeof indexFairnessMembers>;
  canAssign: boolean;
  onAssign: (memberId: number) => void;
}) {
  if (rows.length === 0) {
    return null;
  }
  return (
    <section className="grid gap-2">
      <h4 className="font-semibold text-ink">{title}</h4>
      {rows.map((row) => {
        const value = dimension ? fairnessValueForMember(fairnessIndex, row.team_member_id, dimension.id) : undefined;
        const deviation = value && dimension ? formatFairnessDeviation(value.deviation_absolute, dimension.metric, locale) : null;
        return (
          <div key={row.team_member_id} className="rounded-md border border-slate-200 p-2">
            <div className="flex items-center justify-between gap-2">
              <p className="font-medium text-ink">{row.display_name}</p>
              {deviation ? <span className="font-mono text-xs">Δ {deviation}</span> : null}
            </div>
            <p className="text-xs text-slate-500">
              {row.wish ? t(locale, "wishShort") : null} {row.no_go ? t(locale, "noGoShort") : null} {row.day_status}
            </p>
            {(row.findings ?? []).slice(0, 2).map((finding) => (
              <p key={finding.code} className="text-xs text-slate-600">
                {finding.message}
              </p>
            ))}
            {canAssign && row.status !== "blocked" && row.status !== "ineligible" ? (
              <button className="mt-2 inline-flex min-h-11 items-center rounded-md bg-ink px-3 text-xs font-semibold text-white" type="button" onClick={() => onAssign(row.team_member_id)}>
                {t(locale, "candidateAssign")}
              </button>
            ) : null}
          </div>
        );
      })}
    </section>
  );
}
