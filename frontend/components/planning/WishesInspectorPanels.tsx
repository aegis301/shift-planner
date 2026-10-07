"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { IntentChip } from "@/components/planning/WishesCell";
import { useWishesHistory } from "@/components/planning/WishesHistory";
import { t, type Locale } from "@/lib/i18n";
import {
  planningDayStatusBadgeClass,
  planningDayStatusByCode,
  planningDayStatusLabel
} from "@/lib/planningDayStatus";
import type { WishesBundle } from "@/lib/queries/planning";
import { teamMemberPlanningDisplayName } from "@/lib/teamMemberDisplay";
import {
  anyShiftNoGoWrites,
  bandWrite,
  dayTemplateOptions,
  effectiveKind,
  isAnyShiftNoGo,
  type DayTemplateOption,
  type IntentBand,
  type IntentKind,
  type IntentWrite
} from "@/lib/wishesDay";
import { saveWishesIntents, saveWishesNote } from "@/lib/wishesEdit";
import { wishesMonthOverview } from "@/lib/wishesMonth";

type Matrix = WishesBundle["matrix"];

export function WishesCellPanel({
  locale,
  periodId,
  shiftGroupId,
  matrix,
  notes,
  memberId,
  day,
  readOnly,
  onChanged,
  onSelectDay
}: {
  locale: Locale;
  periodId: string;
  shiftGroupId: string;
  matrix: Matrix;
  notes: WishesBundle["notes"];
  memberId: string;
  day: string;
  readOnly: boolean;
  onChanged: () => void;
  onSelectDay: (day: string) => void;
}) {
  const history = useWishesHistory();
  const member = matrix.team_members.find((row) => String(row.id) === memberId);
  const cell = matrix.cells.find((row) => String(row.team_member_id) === memberId && row.cell_date === day);
  const definition = cell?.status ? planningDayStatusByCode(matrix.day_status_definitions ?? []).get(cell.status) : undefined;
  const options = useMemo(
    () => dayTemplateOptions(matrix.template_slot_days ?? [], matrix.shift_templates ?? [], day, Number(shiftGroupId)),
    [matrix.template_slot_days, matrix.shift_templates, day, shiftGroupId]
  );
  const intents = matrix.shift_intents ?? [];
  const memberNumber = Number(memberId);
  const anyShiftNoGo = isAnyShiftNoGo(intents, options, memberNumber, day);
  const [comment, setComment] = useState(cell?.comment ?? "");
  useEffect(() => {
    setComment(cell?.comment ?? "");
  }, [cell?.comment, cell?.updated_at, memberId, day]);

  async function saveComment() {
    if (readOnly || !member || !cell?.status || (cell.comment ?? "") === comment) {
      return;
    }
    await history.applyEdit(
      [
        {
          teamMemberId: member.id,
          date: day,
          status: cell.status,
          comment: cell.comment ?? null,
          updatedAt: cell.updated_at
        }
      ],
      [
        {
          teamMemberId: member.id,
          date: day,
          status: cell.status,
          comment: comment.trim() === "" ? null : comment,
          expectedUpdatedAt: cell.updated_at
        }
      ]
    );
  }

  async function writeIntents(writes: IntentWrite[]) {
    if (readOnly || !member || !shiftGroupId) {
      return;
    }
    await saveWishesIntents({ periodId, intents: writes });
    onChanged();
  }

  function saveBand(option: DayTemplateOption, band: IntentBand, kind: IntentKind | null) {
    void writeIntents([bandWrite(intents, memberNumber, day, option, band, kind)]);
  }

  return (
    <div className="grid gap-4 text-sm">
      <div>
        <h3 className="font-semibold text-ink">{member ? teamMemberPlanningDisplayName(member) : t(locale, "inspectorMember")}</h3>
        <p className="text-muted">{day}</p>
      </div>
      <section className="grid gap-1">
        <h4 className="font-semibold text-ink">{t(locale, "wishesStatusLabel")}</h4>
        {definition ? (
          <p>
            <span className={`rounded-token-sm px-1 ring-1 ${planningDayStatusBadgeClass(definition.color_preset)}`}>
              {planningDayStatusLabel(definition, locale)}
            </span>
          </p>
        ) : (
          <p className="text-muted">{t(locale, "wishesNoStatus")}</p>
        )}
        {cell ? (
          <p className="text-xs text-muted">
            {t(locale, "wishesLastChange", { when: cell.updated_at, source: cell.source })}
          </p>
        ) : null}
      </section>
      <label className="grid gap-1">
        <span className="font-semibold text-ink">{t(locale, "cellComment")}</span>
        <textarea
          className="min-h-16 rounded-token-md border border-default bg-surface p-2 text-sm"
          disabled={readOnly || !cell?.status}
          value={comment}
          onBlur={() => void saveComment()}
          onChange={(event) => setComment(event.target.value)}
        />
        {!cell?.status ? <span className="text-xs text-muted">{t(locale, "wishesCommentNeedsStatus")}</span> : null}
      </label>
      <section className="grid gap-2">
        <h4 className="font-semibold text-ink">{t(locale, "wishesIntentTitle")}</h4>
        {options.length === 0 ? <p className="text-muted">{t(locale, "wishesNoShiftThatDay")}</p> : null}
        {options.length > 0 && !readOnly ? (
          <button
            className={`h-9 rounded-token-md border px-2 text-left font-semibold ${
              anyShiftNoGo ? "border-default bg-surface text-ink" : "border-rose-800 bg-rose-800 text-white"
            }`}
            disabled={!shiftGroupId}
            type="button"
            onClick={() => void writeIntents(anyShiftNoGoWrites(options, memberNumber, day, !anyShiftNoGo))}
          >
            {t(locale, anyShiftNoGo ? "wishesAnyShiftNoGoClear" : "wishesAnyShiftNoGo")}
          </button>
        ) : null}
        {options.flatMap((option) =>
          (option.split ? (["day", "night"] as const) : (["all"] as const)).map((band) => (
            <IntentPicker
              key={`${option.templateId}-${option.shiftGroupId}-${band}`}
              disabled={readOnly || !shiftGroupId}
              label={band === "all" ? option.name : `${option.name} · ${t(locale, band === "day" ? "rosterViewDay" : "rosterViewNight")}`}
              locale={locale}
              value={effectiveKind(intents, memberNumber, day, option, band)}
              onChange={(kind) => saveBand(option, band, kind)}
            />
          ))
        )}
      </section>
      <WishesMonthOverview locale={locale} matrix={matrix} memberId={Number(memberId)} onSelectDay={onSelectDay} />
      {member ? (
        <WishesMemberNotes
          locale={locale}
          matrix={matrix}
          memberId={member.id}
          notes={notes}
          periodId={periodId}
          readOnly={readOnly}
          shiftGroupId={shiftGroupId}
          onChanged={onChanged}
        />
      ) : null}
    </div>
  );
}

function IntentPicker({
  label,
  value,
  disabled,
  locale,
  onChange
}: {
  label: string;
  value: IntentKind | null;
  disabled: boolean;
  locale: Locale;
  onChange: (kind: IntentKind | null) => void;
}) {
  return (
    <label className="grid gap-1">
      <span>{label}</span>
      <select
        className="h-9 rounded-token-md border border-default bg-surface px-2"
        disabled={disabled}
        value={value ?? ""}
        onChange={(event) => {
          const next = event.target.value;
          onChange(next === "wish" || next === "no_go" ? next : null);
        }}
      >
        <option value="">{t(locale, "wishesIntentNone")}</option>
        <option value="wish">{t(locale, "wishShort")}</option>
        <option value="no_go">{t(locale, "noGoShort")}</option>
      </select>
    </label>
  );
}

export function WishesMonthOverview({
  locale,
  matrix,
  memberId,
  onSelectDay
}: {
  locale: Locale;
  matrix: Matrix;
  memberId: number;
  onSelectDay: (day: string) => void;
}) {
  const rows = useMemo(
    () => wishesMonthOverview(memberId, matrix.cells, matrix.shift_intents ?? [], matrix.shift_templates ?? []),
    [matrix.cells, matrix.shift_intents, matrix.shift_templates, memberId]
  );
  return (
    <section className="grid gap-2">
      <h4 className="font-semibold text-ink">{t(locale, "wishesMonthTitle")}</h4>
      {rows.length === 0 ? <p className="text-sm text-muted">{t(locale, "wishesMonthEmpty")}</p> : null}
      {rows.map((row) => (
        <button
          key={row.kind === "comment" ? `comment-${row.date}` : `${row.kind}-${row.date}-${row.templateId}-${row.band}`}
          className="rounded-token-md border border-default px-2 py-2 text-left"
          type="button"
          onClick={() => onSelectDay(row.date)}
        >
          <span className="font-medium text-ink">{row.date}</span>
          {row.kind === "comment" ? (
            <span className="block text-ink">{row.text}</span>
          ) : (
            <span className="mt-1 flex min-w-0 items-center gap-1">
              <span className="truncate">{row.templateName}</span>
              {row.band !== "all" ? <span className="text-muted">{t(locale, row.band === "day" ? "rosterViewDay" : "rosterViewNight")}</span> : null}
              <IntentChip kind={row.kind} locale={locale} />
            </span>
          )}
        </button>
      ))}
    </section>
  );
}

export function WishesMemberNotes({
  locale,
  periodId,
  shiftGroupId,
  matrix,
  notes,
  memberId,
  readOnly,
  onChanged
}: {
  locale: Locale;
  periodId: string;
  shiftGroupId: string;
  matrix: Matrix;
  notes: WishesBundle["notes"];
  memberId: number;
  readOnly: boolean;
  onChanged: () => void;
}) {
  const member = matrix.team_members.find((row) => row.id === memberId);
  const note = notes.find((row) => row.team_member_id === memberId);
  const [summary, setSummary] = useState(note?.summary ?? "");
  const [preferences, setPreferences] = useState(member?.planning_preferences ?? "");
  const [received, setReceived] = useState(note?.wishes_response_received ?? false);
  useEffect(() => {
    setSummary(note?.summary ?? "");
    setPreferences(member?.planning_preferences ?? "");
    setReceived(note?.wishes_response_received ?? false);
  }, [member?.planning_preferences, memberId, note?.summary, note?.wishes_response_received, note?.updated_at]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (readOnly || !shiftGroupId) {
      return;
    }
    await saveWishesNote({
      periodId,
      shiftGroupId,
      teamMemberId: memberId,
      summary,
      planningPreferences: preferences,
      wishesResponseReceived: received
    });
    onChanged();
  }

  const wishCount = (matrix.shift_intents ?? []).filter((row) => row.team_member_id === memberId && row.kind === "wish").length;
  const noGoCount = (matrix.shift_intents ?? []).filter((row) => row.team_member_id === memberId && row.kind === "no_go").length;

  return (
    <form className="grid gap-3" onSubmit={(event) => void save(event)}>
      <p className="text-xs text-muted">
        {t(locale, "wishShort")} {wishCount} · {t(locale, "noGoShort")} {noGoCount}
      </p>
      <label className="grid gap-1">
        <span className="font-semibold text-ink">{t(locale, "planningPreferencesField")}</span>
        <textarea
          className="min-h-20 rounded-token-md border border-default bg-surface p-2 text-sm"
          disabled={readOnly}
          value={preferences}
          onChange={(event) => setPreferences(event.target.value)}
        />
      </label>
      <label className="grid gap-1">
        <span className="font-semibold text-ink">{t(locale, "monthlyComment")}</span>
        <textarea
          className="min-h-16 rounded-token-md border border-default bg-surface p-2 text-sm"
          disabled={readOnly}
          value={summary}
          onChange={(event) => setSummary(event.target.value)}
        />
      </label>
      <label className="flex items-center gap-2">
        <input checked={received} disabled={readOnly} type="checkbox" onChange={(event) => setReceived(event.target.checked)} />
        {t(locale, "wishesResponseAcknowledged")}
      </label>
      {readOnly ? null : (
        <button className="h-10 rounded-token-md bg-ink px-3 text-sm font-semibold text-white" type="submit">
          {t(locale, "save")}
        </button>
      )}
    </form>
  );
}
