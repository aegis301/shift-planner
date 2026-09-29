"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Grid } from "@/components/grid/Grid";
import { WishesCellView } from "@/components/planning/WishesCell";
import { useWishesHistory } from "@/components/planning/WishesHistory";
import { WishesStatusEditor } from "@/components/planning/WishesStatusEditor";
import { useLocale } from "@/components/LocaleProvider";
import { toTsv } from "@/lib/grid/clipboard";
import { rangeOf, selectionAt, type GridSelection } from "@/lib/grid/selection";
import { t, type Locale } from "@/lib/i18n";
import {
  activePlanningDayStatusDefinitions,
  planningDayStatusByCode,
  planningDayStatusLabel
} from "@/lib/planningDayStatus";
import { useWishesMatrix, type WishesBundle } from "@/lib/queries/planning";
import { teamMemberPlanningDisplayName } from "@/lib/teamMemberDisplay";
import {
  cellKey,
  parseWishesPaste,
  resolveStatusToken,
  toWishesInternal,
  type WishesCellState,
  type WishesCellWrite
} from "@/lib/wishesUndo";

type Matrix = WishesBundle["matrix"];
type Member = Matrix["team_members"][number];

export function WishesGrid({
  periodId,
  shiftGroupId,
  versionId = null,
  readOnly = false,
  readOnlyReason = "",
  onSelectCell
}: {
  periodId: string;
  shiftGroupId?: string;
  versionId?: number | null;
  readOnly?: boolean;
  readOnlyReason?: string;
  onSelectCell?: (date: string, teamMemberId: number) => void;
}) {
  const { locale } = useLocale();
  const history = useWishesHistory();
  const wishesQuery = useWishesMatrix({
    periodId,
    shiftGroupId: shiftGroupId ?? "",
    teamMemberPortal: false,
    versionId,
    enabled: periodId !== ""
  });
  const matrix = wishesQuery.data?.matrix ?? null;
  const [selection, setSelection] = useState<GridSelection>(selectionAt({ row: 0, col: 0 }, { rows: 1, cols: 1 }));
  const [editorFilter, setEditorFilter] = useState<string | null>(null);
  const lastCopy = useRef<{ tsv: string; json: string } | null>(null);

  useEffect(() => {
    setSelection(selectionAt({ row: 0, col: 0 }, { rows: 1, cols: 1 }));
    setEditorFilter(null);
  }, [periodId, shiftGroupId, versionId]);

  const memberRows = matrix?.team_members;
  const noteRows = wishesQuery.data?.notes;
  const members = memberRows ?? [];
  const days = matrix?.days ?? [];
  const definitions = useMemo(
    () => activePlanningDayStatusDefinitions(matrix?.day_status_definitions ?? []),
    [matrix?.day_status_definitions]
  );
  const statusByCode = useMemo(() => planningDayStatusByCode(definitions), [definitions]);
  const cellIndex = useMemo(() => {
    const index = new Map<string, Matrix["cells"][number]>();
    for (const cell of matrix?.cells ?? []) {
      index.set(cellKey(cell.team_member_id, cell.cell_date), cell);
    }
    return index;
  }, [matrix?.cells]);
  const intentIndex = useMemo(() => {
    const index = new Map<string, { wish: number; noGo: number }>();
    for (const row of matrix?.shift_intents ?? []) {
      const key = cellKey(row.team_member_id, row.cell_date);
      const current = index.get(key) ?? { wish: 0, noGo: 0 };
      if (row.kind === "wish") {
        current.wish += 1;
      } else if (row.kind === "no_go") {
        current.noGo += 1;
      }
      index.set(key, current);
    }
    return index;
  }, [matrix?.shift_intents]);
  const columns = useMemo(() => {
    if (!matrix) {
      return [];
    }
    const labels = uniqueNames(memberRows ?? []);
    return (memberRows ?? []).map((member) => ({
      id: String(member.id),
      group: labels.get(member.id) ?? teamMemberPlanningDisplayName(member),
      header: columnHeader(member, matrix, noteRows ?? [], locale)
    }));
  }, [locale, matrix, memberRows, noteRows]);

  function stateAt(row: number, col: number): WishesCellState | null {
    const member = members[col];
    const date = days[row]?.date;
    if (!member || !date) {
      return null;
    }
    const cell = cellIndex.get(cellKey(member.id, date));
    return {
      teamMemberId: member.id,
      date,
      status: cell?.status ?? null,
      comment: cell?.comment ?? null,
      updatedAt: cell?.updated_at ?? null
    };
  }

  function selectedStates(): WishesCellState[] {
    const range = rangeOf(selection);
    const states: WishesCellState[] = [];
    for (let row = range.rowStart; row <= range.rowEnd; row += 1) {
      for (let col = range.colStart; col <= range.colEnd; col += 1) {
        const state = stateAt(row, col);
        if (state) {
          states.push(state);
        }
      }
    }
    return states;
  }

  function refocus() {
    window.setTimeout(() => document.querySelector<HTMLElement>("[data-grid-active='true']")?.focus(), 0);
  }

  async function applyStates(before: WishesCellState[], writes: WishesCellWrite[], unresolved: string[] = []) {
    setEditorFilter(null);
    await history.applyEdit(before, writes, unresolved);
    refocus();
  }

  async function applyStatus(status: string | null) {
    const before = selectedStates();
    const writes = before.map((state) => ({
      teamMemberId: state.teamMemberId,
      date: state.date,
      status,
      comment: status == null ? null : state.comment,
      expectedUpdatedAt: state.updatedAt
    }));
    await applyStates(before, writes);
  }

  async function copySelection() {
    const range = rangeOf(selection);
    const labels: (string | null)[][] = [];
    const internal: { status: string | null; comment: string | null }[][] = [];
    for (let row = range.rowStart; row <= range.rowEnd; row += 1) {
      const labelRow: (string | null)[] = [];
      const internalRow: { status: string | null; comment: string | null }[] = [];
      for (let col = range.colStart; col <= range.colEnd; col += 1) {
        const state = stateAt(row, col);
        const definition = state?.status ? statusByCode.get(state.status) : undefined;
        labelRow.push(definition ? planningDayStatusLabel(definition, locale) : "");
        internalRow.push({ status: state?.status ?? null, comment: state?.comment ?? null });
      }
      labels.push(labelRow);
      internal.push(internalRow);
    }
    const tsv = toTsv(labels);
    lastCopy.current = { tsv, json: toWishesInternal(internal) };
    await navigator.clipboard.writeText(tsv);
  }

  async function pasteSelection() {
    if (readOnly) {
      return;
    }
    const text = await navigator.clipboard.readText();
    const payload = lastCopy.current && text === lastCopy.current.tsv ? lastCopy.current.json : text;
    const parsed = parseWishesPaste(payload);
    if (!parsed) {
      return;
    }
    const range = rangeOf(selection);
    const single = parsed.length === 1 && parsed[0]?.length === 1;
    const wide = range.rowEnd > range.rowStart || range.colEnd > range.colStart;
    const height = single && wide ? range.rowEnd - range.rowStart + 1 : parsed.length;
    const width = single && wide ? range.colEnd - range.colStart + 1 : (parsed[0]?.length ?? 0);
    const before: WishesCellState[] = [];
    const writes: WishesCellWrite[] = [];
    const unresolved = new Set<string>();
    for (let rowOffset = 0; rowOffset < height; rowOffset += 1) {
      for (let colOffset = 0; colOffset < width; colOffset += 1) {
        const state = stateAt(range.rowStart + rowOffset, range.colStart + colOffset);
        const source = single && wide ? parsed[0]?.[0] : parsed[rowOffset]?.[colOffset];
        if (!state || !source) {
          continue;
        }
        const resolved = source.raw
          ? resolveStatusToken(source.status ?? "", definitions)
          : source.status
            ? { status: source.status }
            : { clear: true as const };
        if ("unresolved" in resolved) {
          unresolved.add(resolved.unresolved);
          continue;
        }
        before.push(state);
        writes.push({
          teamMemberId: state.teamMemberId,
          date: state.date,
          status: "clear" in resolved ? null : resolved.status,
          comment: "clear" in resolved ? null : source.raw ? state.comment : source.comment,
          expectedUpdatedAt: state.updatedAt
        });
      }
    }
    await applyStates(before, writes, [...unresolved]);
  }

  function fill(direction: "down" | "right") {
    if (!matrix || readOnly) {
      return;
    }
    const range = rangeOf(selection);
    const before: WishesCellState[] = [];
    const writes: WishesCellWrite[] = [];
    if (direction === "down") {
      for (let row = range.rowStart + 1; row <= range.rowEnd; row += 1) {
        for (let col = range.colStart; col <= range.colEnd; col += 1) {
          const source = stateAt(range.rowStart, col);
          const target = stateAt(row, col);
          if (source && target) {
            before.push(target);
            writes.push(copied(target, source));
          }
        }
      }
    } else {
      for (let row = range.rowStart; row <= range.rowEnd; row += 1) {
        for (let col = range.colStart + 1; col <= range.colEnd; col += 1) {
          const source = stateAt(row, range.colStart);
          const target = stateAt(row, col);
          if (source && target) {
            before.push(target);
            writes.push(copied(target, source));
          }
        }
      }
    }
    void applyStates(before, writes);
  }

  if (!matrix) {
    return null;
  }

  return (
    <div className="grid gap-2">
      {readOnlyReason ? (
        <p className="text-sm font-medium text-amber-900" role="status">
          {readOnlyReason}
        </p>
      ) : null}
      {history.notice ? (
        <p className="text-sm text-muted" role="status">
          {history.notice}
        </p>
      ) : null}
      <Grid
        columns={columns}
        cornerLabel={t(locale, "date")}
        editable={!readOnly}
        editing={editorFilter !== null}
        label={t(locale, "wishesGridLabel")}
        renderCell={(row, col) => {
          const state = stateAt(row, col);
          const definition = state?.status ? statusByCode.get(state.status) : undefined;
          const intents = state ? intentIndex.get(cellKey(state.teamMemberId, state.date)) : undefined;
          return (
            <WishesCellView
              colorPreset={definition?.color_preset ?? null}
              comment={state?.comment ?? ""}
              label={definition ? planningDayStatusLabel(definition, locale) : ""}
              locale={locale}
              noGoCount={intents?.noGo ?? 0}
              wishCount={intents?.wish ?? 0}
            />
          );
        }}
        renderRowHeader={(row) => <DayHeader date={days[row]?.date ?? ""} locale={locale} />}
        rowCount={days.length}
        selection={selection}
        onCommand={(command) => {
          if (command.type === "edit") {
            if (readOnly || !stateAt(selection.active.row, selection.active.col)) {
              return;
            }
            setEditorFilter(command.filter);
            return;
          }
          if (command.type === "cancel") {
            setEditorFilter(null);
            return;
          }
          if (readOnly) {
            return;
          }
          if (command.type === "clear") {
            void applyStatus(null);
            return;
          }
          if (command.type === "copy") {
            void copySelection();
            return;
          }
          if (command.type === "paste") {
            void pasteSelection();
            return;
          }
          if (command.type === "fill-down") {
            fill("down");
            return;
          }
          if (command.type === "fill-right") {
            fill("right");
            return;
          }
          if (command.type === "undo") {
            void history.undo();
            return;
          }
          if (command.type === "redo") {
            void history.redo();
          }
        }}
        onSelectionChange={(next) => {
          setEditorFilter(null);
          setSelection(next);
          const member = members[next.active.col];
          const date = days[next.active.row]?.date;
          if (member && date) {
            onSelectCell?.(date, member.id);
          }
        }}
      />
      {editorFilter !== null ? (
        <WishesStatusEditor
          definitions={definitions}
          filter={editorFilter}
          locale={locale}
          onOpenChange={(open) => {
            if (!open) {
              setEditorFilter(null);
              refocus();
            }
          }}
          onSelect={(status) => void applyStatus(status)}
        />
      ) : null}
    </div>
  );
}

function copied(target: WishesCellState, source: WishesCellState): WishesCellWrite {
  return {
    teamMemberId: target.teamMemberId,
    date: target.date,
    status: source.status,
    comment: source.status == null ? null : source.comment,
    expectedUpdatedAt: target.updatedAt
  };
}

function DayHeader({ date, locale }: { date: string; locale: Locale }) {
  if (!date) {
    return null;
  }
  const formatted = new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-GB", {
    weekday: "short",
    day: "2-digit",
    month: "2-digit"
  }).format(new Date(`${date}T12:00:00`));
  return <span className="truncate font-medium text-ink">{formatted}</span>;
}

function columnHeader(
  member: Member,
  matrix: Matrix,
  notes: WishesBundle["notes"],
  locale: Locale
): string {
  const filled = matrix.cells.filter((cell) => cell.team_member_id === member.id && cell.status).length;
  const note = notes.find((row) => row.team_member_id === member.id);
  const marked = Boolean(note?.summary?.trim() || note?.wishes_response_received);
  const progress = t(locale, "wishesFilledLabel", { filled: String(filled), total: String(matrix.days.length) });
  const percent = Number.isInteger(member.employment_percentage)
    ? String(member.employment_percentage)
    : member.employment_percentage.toFixed(1);
  return marked ? `${percent}% · ${progress} · ${t(locale, "wishesNoteMark")}` : `${percent}% · ${progress}`;
}

function uniqueNames(members: Member[]): Map<number, string> {
  const counts = new Map<string, number>();
  for (const member of members) {
    const name = teamMemberPlanningDisplayName(member);
    counts.set(name, (counts.get(name) ?? 0) + 1);
  }
  const seen = new Map<string, number>();
  const labels = new Map<number, string>();
  for (const member of members) {
    const name = teamMemberPlanningDisplayName(member);
    if ((counts.get(name) ?? 0) > 1) {
      const next = (seen.get(name) ?? 0) + 1;
      seen.set(name, next);
      labels.set(member.id, `${name} ${next}`);
    } else {
      labels.set(member.id, name);
    }
  }
  return labels;
}
