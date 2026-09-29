"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useWishesHistory } from "@/components/planning/WishesHistory";
import { t, type Locale } from "@/lib/i18n";
import {
  planningDayStatusBadgeClass,
  planningDayStatusByCode,
  planningDayStatusLabel
} from "@/lib/planningDayStatus";
import type { WishesBundle } from "@/lib/queries/planning";
import { teamMemberPlanningDisplayName } from "@/lib/teamMemberDisplay";
import { saveWishesIntent, saveWishesNote } from "@/lib/wishesEdit";

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
  onChanged
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
}) {
  const history = useWishesHistory();
  const member = matrix.team_members.find((row) => String(row.id) === memberId);
  const cell = matrix.cells.find((row) => String(row.team_member_id) === memberId && row.cell_date === day);
  const definition = cell?.status ? planningDayStatusByCode(matrix.day_status_definitions ?? []).get(cell.status) : undefined;
  const templates = useMemo(() => {
    const groupId = Number(shiftGroupId);
    return (matrix.shift_templates ?? [])
      .filter((row) => row.is_active)
      .slice()
      .sort((left, right) => left.name.localeCompare(right.name, undefined, { sensitivity: "base" }) || left.id - right.id)
      .map((row) => ({ id: row.id, name: row.name, shiftGroupId: groupId }));
  }, [matrix.shift_templates, shiftGroupId]);
  const intents = (matrix.shift_intents ?? []).filter((row) => String(row.team_member_id) === memberId && row.cell_date === day);
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

  async function saveIntent(templateId: number, groupId: number, kind: "wish" | "no_go" | null) {
    if (readOnly || !member || !Number.isFinite(groupId)) {
      return;
    }
    await saveWishesIntent({
      periodId,
      teamMemberId: member.id,
      date: day,
      shiftGroupId: groupId,
      shiftTemplateId: templateId,
      kind
    });
    onChanged();
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
        {templates.map((template) => {
          const intent = intents.find((row) => row.shift_template_id === template.id && row.shift_group_id === template.shiftGroupId);
          return (
            <label key={`${template.id}-${template.shiftGroupId}`} className="grid gap-1">
              <span>{template.name}</span>
              <select
                className="h-9 rounded-token-md border border-default bg-surface px-2"
                disabled={readOnly || !shiftGroupId}
                value={intent?.kind ?? ""}
                onChange={(event) => {
                  const value = event.target.value;
                  void saveIntent(template.id, template.shiftGroupId, value === "wish" || value === "no_go" ? value : null);
                }}
              >
                <option value="">{t(locale, "wishesIntentNone")}</option>
                <option value="wish">{t(locale, "wishShort")}</option>
                <option value="no_go">{t(locale, "noGoShort")}</option>
              </select>
            </label>
          );
        })}
      </section>
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
