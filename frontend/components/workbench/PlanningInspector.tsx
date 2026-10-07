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
import type { RosterChangeNotice } from "@/components/planning/RosterGrid";
import { IntentChip } from "@/components/planning/WishesCell";
import { WishesCellPanel, WishesMemberNotes, WishesMonthOverview } from "@/components/planning/WishesInspectorPanels";
import { planningDayStatusBadgeClass, planningDayStatusByCode, planningDayStatusLabel } from "@/lib/planningDayStatus";
import type { WishesBundle } from "@/lib/queries/planning";
import { wishesMonthOverview, type WishesMonthCell, type WishesMonthIntent, type WishesMonthTemplate } from "@/lib/wishesMonth";

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
  changeNotice = null,
  wishes = null,
  wishesNotes = [],
  wishesReadOnly = true,
  onWishesChanged,
  onAssign,
  onSelectMember,
  onSelectSlot,
  onSelectDay
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
  changeNotice?: RosterChangeNotice | null;
  wishes?: WishesBundle["matrix"] | null;
  wishesNotes?: WishesBundle["notes"];
  wishesReadOnly?: boolean;
  onWishesChanged?: () => void;
  onAssign: (memberId: number) => void;
  onSelectMember: (memberId: string) => void;
  onSelectSlot: (slotId: string) => void;
  onSelectDay: (day: string) => void;
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
  const notice = changeNotice ? <ChangeSetNotice locale={locale} notice={changeNotice} /> : null;
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
        {notice}
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
        <AssigneeDayWishes locale={locale} roster={roster} slotId={slotId} wishes={wishes} />
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
  if (memberId && day && wishes && onWishesChanged) {
    return (
      <div className="grid gap-4">
        {notice}
        <WishesCellPanel
          day={day}
          locale={locale}
          matrix={wishes}
          memberId={memberId}
          notes={wishesNotes}
          periodId={periodId}
          readOnly={wishesReadOnly}
          shiftGroupId={shiftGroupId}
          onChanged={onWishesChanged}
          onSelectDay={onSelectDay}
        />
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
        {wishes && onWishesChanged ? (
          <>
            <WishesMonthOverview locale={locale} matrix={wishes} memberId={Number(memberId)} onSelectDay={onSelectDay} />
            <WishesMemberNotes
              locale={locale}
              matrix={wishes}
              memberId={Number(memberId)}
              notes={wishesNotes}
              periodId={periodId}
              readOnly={wishesReadOnly}
              shiftGroupId={shiftGroupId}
              onChanged={onWishesChanged}
            />
          </>
        ) : null}
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
  if (notice) {
    return notice;
  }
  return <p className="text-sm text-slate-600">{t(locale, "inspectorEmpty")}</p>;
}

function AssigneeDayWishes({
  locale,
  roster,
  wishes,
  slotId
}: {
  locale: Locale;
  roster: RosterMatrix | null;
  wishes: WishesBundle["matrix"] | null;
  slotId: string;
}) {
  const slot = roster?.slots.find((row) => String(row.id) === slotId);
  const assignment = roster?.assignments.find((row) => String(row.roster_slot_id) === slotId);
  if (!slot || !assignment) {
    return null;
  }
  const cells: (WishesMonthCell & { status?: string | null })[] = wishes?.cells ?? roster?.planning_cells ?? [];
  const intents: WishesMonthIntent[] = wishes?.shift_intents ?? roster?.shift_intents ?? [];
  const templates: WishesMonthTemplate[] = wishes?.shift_templates ?? roster?.shift_templates ?? [];
  const definitions = wishes?.day_status_definitions ?? roster?.day_status_definitions ?? [];
  const cell = cells.find((row) => row.team_member_id === assignment.team_member_id && row.cell_date === slot.slot_date);
  const definition = cell?.status ? planningDayStatusByCode(definitions).get(cell.status) : undefined;
  const comment = cell?.comment?.trim() ?? "";
  const dayIntents = wishesMonthOverview(assignment.team_member_id, [], intents, templates).filter((row) => row.date === slot.slot_date);
  return (
    <section className="grid gap-2">
      <h4 className="font-semibold text-ink">{t(locale, "wishesAssigneeDay")}</h4>
      {definition ? (
        <p>
          <span className={`rounded-token-sm px-1 ring-1 ${planningDayStatusBadgeClass(definition.color_preset)}`}>
            {planningDayStatusLabel(definition, locale)}
          </span>
        </p>
      ) : (
        <p className="text-muted">{t(locale, "wishesNoStatus")}</p>
      )}
      <p className="text-ink">{comment || t(locale, "emptyValue")}</p>
      {dayIntents.map((row) =>
        row.kind === "comment" ? null : (
          <p key={`${row.kind}-${row.templateId}-${row.band}`} className="flex min-w-0 items-center gap-1">
            <span className="truncate">{row.templateName}</span>
            {row.band !== "all" ? <span className="text-muted">{t(locale, row.band === "day" ? "rosterViewDay" : "rosterViewNight")}</span> : null}
            <IntentChip kind={row.kind} locale={locale} />
          </p>
        )
      )}
    </section>
  );
}

function ChangeSetNotice({ locale, notice }: { locale: Locale; notice: RosterChangeNotice }) {
  const refused = notice.changeSet?.items.filter((item) => item.outcome === "refused") ?? [];
  if (refused.length === 0 && notice.unresolvedNames.length === 0) {
    return null;
  }
  return (
    <section className="grid gap-2 rounded-token-md bg-severity-error p-2">
      <h3 className="font-semibold text-ink">{t(locale, "changeSetRefusedTitle")}</h3>
      {notice.unresolvedNames.length > 0 ? <p>{t(locale, "gridPasteUnresolved", { names: notice.unresolvedNames.join(", ") })}</p> : null}
      {refused.map((item) => (
        <p key={item.id} className="text-xs">
          {item.roster_slot_id}: {item.refusal_code === "changed_since" ? t(locale, "changeSetChangedSince") : item.refusal_code ?? item.findings?.[0]?.message ?? ""}
        </p>
      ))}
      {notice.applyLegal ? (
        <button className="rounded-token-md bg-ink px-2 py-1 text-xs font-semibold text-white" type="button" onClick={notice.applyLegal}>
          {t(locale, "changeSetApplyLegal")}
        </button>
      ) : null}
    </section>
  );
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
