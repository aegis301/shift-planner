"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Grid } from "@/components/grid/Grid";
import {
  Combobox,
  ComboboxAnchor,
  ComboboxContent,
  ComboboxInput,
  ComboboxItem,
  ComboboxList
} from "@/components/ui/combobox";
import { useLocale, useSession } from "@/components/LocaleProvider";
import { ApiError } from "@/lib/api";
import type { RosterMatrix } from "@/lib/api/types";
import { parseClipboard, resolvePasteCell, toInternalClipboard, toTsv, type ClipboardMember } from "@/lib/grid/clipboard";
import { rangeOf, selectionAt, type GridSelection } from "@/lib/grid/selection";
import { emptyUndoStacks, pushCreatedSet, pushRedoResult, pushUndoResult, rebuildUndoStacks, type UndoStacks } from "@/lib/grid/undoStack";
import { t, type Locale } from "@/lib/i18n";
import {
  fairnessDeviationChipClass,
  fairnessDimensionLabel,
  fairnessValueForMember,
  formatFairnessDeviation,
  formatFairnessWindowRange,
  indexFairnessMembers,
  relevantFairnessDimension,
  type FairnessAccountsRead
} from "@/lib/fairness";
import { sessionTimeZone } from "@/lib/orgTime";
import {
  planningDayStatusBadgeClass,
  planningDayStatusByCode,
  planningDayStatusLabel,
  planningDayStatusSolidClass,
  rosterBlocksForPlanningDayStatusCode
} from "@/lib/planningDayStatus";
import { usePlanningOrganizationId, useRosterMatrix } from "@/lib/queries/planning";
import { invalidateQueryKeys, rosterAssignmentKeys } from "@/lib/queries/invalidation";
import {
  revertRosterChangeSet,
  useRosterAssignmentMutation,
  useRosterChangeSetMutation,
  useRosterChangeSets,
  type RosterChangeSetRead,
  type RosterChangeWrite
} from "@/lib/queries/rosterEdit";
import { useUnresolvedShiftSwaps } from "@/lib/queries/activity";
import {
  columnHeader,
  isNightRosterSlot,
  maxStackSize,
  rosterGridColumns,
  rowHeightForStack,
  slotsForColumn,
  stackIndexAfterMove,
  type RosterColumnSlot,
  type RosterGridColumn,
  type RosterView
} from "@/lib/rosterColumns";
import { IntentChip } from "@/components/planning/WishesCell";
import { intentBandCoversSlot } from "@/lib/wishesDay";
import { formatShiftTimeRange } from "@/lib/shiftDisplay";
import { teamMemberPlanningDisplayName } from "@/lib/teamMemberDisplay";

type WarningHint = {
  severity: "info" | "warning" | "error";
  team_member_id: number | null;
  date: string | null;
  details: Record<string, unknown>;
};

export type RosterChangeNotice = {
  changeSet: RosterChangeSetRead | null;
  unresolvedNames: string[];
  applyLegal: (() => void) | null;
};

export function RosterGrid({
  periodId,
  shiftGroupId,
  versionId = null,
  readOnly = false,
  validationWarnings = [],
  duplicateMemberDayKeys,
  fairnessAccounts = null,
  onSelectSlot,
  onNotice,
  view = "template"
}: {
  periodId: string;
  shiftGroupId?: string;
  versionId?: number | null;
  readOnly?: boolean;
  validationWarnings?: WarningHint[];
  duplicateMemberDayKeys?: ReadonlySet<string>;
  fairnessAccounts?: FairnessAccountsRead | null;
  onSelectSlot?: (slotId: number) => void;
  onNotice?: (notice: RosterChangeNotice | null) => void;
  view?: RosterView;
}) {
  const { locale } = useLocale();
  const { me } = useSession();
  const queryClient = useQueryClient();
  const organizationId = usePlanningOrganizationId();
  const timeZone = sessionTimeZone(me);
  const rosterQuery = useRosterMatrix({
    periodId,
    shiftGroupId: shiftGroupId ?? "",
    teamMemberPortal: false,
    versionId,
    enabled: periodId !== ""
  });
  const matrix = rosterQuery.data?.matrix ?? null;
  const scope =
    organizationId != null && periodId !== "" && shiftGroupId
      ? { organizationId, periodId, shiftGroupId, teamMemberPortal: false }
      : null;
  const assignOne = useRosterAssignmentMutation(scope);
  const applySet = useRosterChangeSetMutation(scope);
  const history = useRosterChangeSets(scope);
  const swaps = useUnresolvedShiftSwaps({ periodId, shiftGroupId: shiftGroupId ?? "", enabled: Boolean(shiftGroupId) });
  const [selection, setSelection] = useState<GridSelection>(selectionAt({ row: 0, col: 0 }, { rows: 1, cols: 1 }));
  const [stacks, setStacks] = useState<UndoStacks | null>(null);
  const [editor, setEditor] = useState<{ filter: string; manualOverride: boolean } | null>(null);
  const [message, setMessage] = useState("");
  const [stackIndex, setStackIndex] = useState(0);
  const stackIndexRef = useRef(0);
  const stackEntryRef = useRef<number | null>(null);
  const lastCopy = useRef<{ tsv: string; json: string } | null>(null);
  const headerLabels = { day: t(locale, "rosterViewDay"), night: t(locale, "rosterViewNight") };
  const columns = useMemo(
    () => (matrix ? rosterGridColumns(matrix.slots, matrix.shift_templates ?? [], view, timeZone) : []),
    [matrix, timeZone, view]
  );
  const days = useMemo(() => matrix?.days ?? [], [matrix?.days]);
  const stackRowHeight = useCallback(
    (row: number) => rowHeightForStack(maxStackSize(matrix?.slots ?? [], columns, days[row]?.date ?? "", timeZone)),
    [columns, days, matrix?.slots, timeZone]
  );
  const userId = me && "id" in me ? me.id : null;
  const userEmail = me && "email" in me ? me.email : null;

  useEffect(() => {
    setStacks(null);
  }, [periodId, shiftGroupId]);

  useEffect(() => {
    if (stacks !== null || !history.data || userId == null || userEmail == null) {
      return;
    }
    setStacks(rebuildUndoStacks(history.data, { id: userId, email: userEmail }));
  }, [history.data, stacks, userEmail, userId]);

  const swapSlotIds = useMemo(() => {
    const ids = new Set<number>();
    for (const row of swaps.data ?? []) {
      if ("offered_slot_id" in row && typeof row.offered_slot_id === "number") {
        ids.add(row.offered_slot_id);
      }
    }
    return ids;
  }, [swaps.data]);

  async function remember(changeSet: { id: number; status: string; items?: { outcome: string }[] } | null | undefined) {
    if (!changeSet || changeSet.status === "refused") {
      return;
    }
    if (changeSet.items && !changeSet.items.some((item) => item.outcome === "applied")) {
      return;
    }
    setStacks((current) => pushCreatedSet(current ?? emptyUndoStacks(), changeSet.id));
  }

  async function applyItems(items: RosterChangeWrite[], mode: "all_or_nothing" | "best_effort", label: string, unresolvedNames: string[] = []) {
    if (!scope || items.length === 0) {
      if (unresolvedNames.length > 0) {
        onNotice?.({ changeSet: null, unresolvedNames, applyLegal: null });
      }
      return;
    }
    const result = await applySet.mutateAsync({ mode, label, items });
    if (result.applied && result.changeSet) {
      await remember(result.changeSet);
      onNotice?.(unresolvedNames.length > 0 ? { changeSet: null, unresolvedNames, applyLegal: null } : null);
      setMessage(t(locale, "autosaved"));
      return;
    }
    if (result.changeSet) {
      onNotice?.({
        changeSet: result.changeSet,
        unresolvedNames,
        applyLegal: mode === "all_or_nothing" ? () => void applyItems(items, "best_effort", label) : null
      });
    }
  }

  async function saveOne(memberId: number | "", manualOverride: boolean) {
    const slot = slotAt(matrix, columns, days, selection.active.row, selection.active.col, timeZone, stackIndexRef.current);
    if (!slot || readOnly) {
      return;
    }
    setEditor(null);
    window.setTimeout(() => document.querySelector<HTMLElement>("[data-grid-active='true']")?.focus(), 0);
    try {
      const saved = await assignOne.mutateAsync({
        rosterSlotId: slot.id,
        teamMemberId: memberId,
        manualOverride: memberId === "" ? false : manualOverride
      });
      const changeSetId = saved && "change_set_id" in saved ? saved.change_set_id : null;
      if (changeSetId != null) {
        await remember({ id: changeSetId, status: "applied", items: [{ outcome: "applied" }] });
      }
      setMessage(t(locale, "autosaved"));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t(locale, "warnings"));
    }
  }

  function selectedItems(readMember: (row: number, col: number) => number | null): RosterChangeWrite[] {
    if (!matrix) {
      return [];
    }
    const range = rangeOf(selection);
    const items: RosterChangeWrite[] = [];
    for (let row = range.rowStart; row <= range.rowEnd; row += 1) {
      for (let col = range.colStart; col <= range.colEnd; col += 1) {
        const slot = slotAt(matrix, columns, days, row, col, timeZone, stackIndexRef.current);
        if (!slot) {
          continue;
        }
        items.push({ rosterSlotId: slot.id, teamMemberId: readMember(row, col) });
      }
    }
    return items;
  }

  async function copySelection() {
    if (!matrix) {
      return;
    }
    const range = rangeOf(selection);
    const labels: (string | null)[][] = [];
    const internal: { memberId: number | null }[][] = [];
    for (let row = range.rowStart; row <= range.rowEnd; row += 1) {
      const labelRow: (string | null)[] = [];
      const idRow: { memberId: number | null }[] = [];
      for (let col = range.colStart; col <= range.colEnd; col += 1) {
        const slot = slotAt(matrix, columns, days, row, col, timeZone, stackIndexRef.current);
        const assignment = slot ? matrix.assignments.find((rowItem) => rowItem.roster_slot_id === slot.id) : undefined;
        const member = assignment ? matrix.team_members.find((item) => item.id === assignment.team_member_id) : undefined;
        labelRow.push(member ? teamMemberPlanningDisplayName(member) : "");
        idRow.push({ memberId: assignment?.team_member_id ?? null });
      }
      labels.push(labelRow);
      internal.push(idRow);
    }
    const tsv = toTsv(labels);
    lastCopy.current = { tsv, json: toInternalClipboard(internal) };
    await navigator.clipboard.writeText(tsv);
  }

  async function pasteSelection() {
    if (!matrix || readOnly) {
      return;
    }
    const text = await navigator.clipboard.readText();
    const payload = lastCopy.current && text === lastCopy.current.tsv ? lastCopy.current.json : text;
    const parsed = parseClipboard(payload);
    if (!parsed) {
      return;
    }
    const range = rangeOf(selection);
    const single = parsed.rows.length === 1 && parsed.rows[0]?.length === 1;
    const wide = range.rowEnd > range.rowStart || range.colEnd > range.colStart;
    const height = single && wide ? range.rowEnd - range.rowStart + 1 : parsed.rows.length;
    const width = single && wide ? range.colEnd - range.colStart + 1 : (parsed.rows[0]?.length ?? 0);
    const unresolved = new Set<string>();
    const items: RosterChangeWrite[] = [];
    for (let rowOffset = 0; rowOffset < height; rowOffset += 1) {
      for (let colOffset = 0; colOffset < width; colOffset += 1) {
        const row = range.rowStart + rowOffset;
        const col = range.colStart + colOffset;
        const slot = slotAt(matrix, columns, days, row, col, timeZone, stackIndexRef.current);
        if (!slot) {
          continue;
        }
        const source = single && wide ? parsed.rows[0][0] : parsed.rows[rowOffset]?.[colOffset];
        if (source === undefined) {
          continue;
        }
        const resolved = resolvePasteCell(source, matrix.team_members as ClipboardMember[]);
        if (resolved.kind === "unresolved") {
          unresolved.add(resolved.name);
          continue;
        }
        items.push({ rosterSlotId: slot.id, teamMemberId: resolved.kind === "member" ? resolved.memberId : null });
      }
    }
    await applyItems(items, "all_or_nothing", "Paste", [...unresolved]);
  }

  async function undo() {
    const id = stacks?.undo.at(-1);
    if (id == null || !scope) {
      return;
    }
    const result = await revertRosterChangeSet(id);
    await invalidateQueryKeys(queryClient, rosterAssignmentKeys(scope));
    if (!result.applied || !result.changeSet) {
      onNotice?.({ changeSet: result.changeSet, unresolvedNames: [], applyLegal: null });
      return;
    }
    setStacks((current) => pushUndoResult(current ?? emptyUndoStacks(), id, result.changeSet.id));
    onNotice?.(
      result.changeSet.items.some((item) => item.refusal_code === "changed_since")
        ? { changeSet: result.changeSet, unresolvedNames: [], applyLegal: null }
        : null
    );
  }

  async function redo() {
    const id = stacks?.redo.at(-1);
    if (id == null || !scope) {
      return;
    }
    const result = await revertRosterChangeSet(id);
    await invalidateQueryKeys(queryClient, rosterAssignmentKeys(scope));
    if (!result.applied || !result.changeSet) {
      onNotice?.({ changeSet: result.changeSet, unresolvedNames: [], applyLegal: null });
      return;
    }
    setStacks((current) => pushRedoResult(current ?? emptyUndoStacks(), id, result.changeSet.id));
  }

  if (!matrix) {
    return null;
  }

  const activeSlot = slotAt(matrix, columns, days, selection.active.row, selection.active.col, timeZone, stackIndexRef.current);

  return (
    <div className="grid gap-2">
      {message ? <p className="text-sm text-muted">{message}</p> : null}
      <Grid
        columns={columns.map((column) => ({ id: column.key, header: columnHeader(column, headerLabels), group: column.name }))}
        cornerLabel={t(locale, "date")}
        editable={!readOnly}
        editing={editor !== null}
        getRowSize={view === "variant" ? undefined : stackRowHeight}
        label={t(locale, "rosterGridLabel")}
        renderCell={(row, col) => (
          <RosterGridCell
            active={selection.active.row === row && selection.active.col === col}
            activeSlotId={slotAt(matrix, columns, days, row, col, timeZone, stackIndex)?.id ?? null}
            column={columns[col]}
            locale={locale}
            matrix={matrix}
            slotDate={days[row]?.date ?? ""}
            duplicateMemberDayKeys={duplicateMemberDayKeys}
            swapSlotIds={swapSlotIds}
            timeZone={timeZone}
            warnings={validationWarnings}
            onActivate={(slotId) => {
              const slots = slotsAt(matrix, columns, days, row, col, timeZone);
              const index = Math.max(0, slots.findIndex((slot) => slot.id === slotId));
              stackIndexRef.current = index;
              setStackIndex(index);
              setSelection(selectionAt({ row, col }, { rows: days.length, cols: columns.length }));
              if (!readOnly) {
                const assignment = matrix.assignments.find((item) => item.roster_slot_id === slotId);
                setEditor({ filter: "", manualOverride: assignment?.manual_override === true });
              }
              onSelectSlot?.(slotId);
            }}
          />
        )}
        renderRowHeader={(row) => <DayHeader date={days[row]?.date ?? ""} locale={locale} slots={matrix.slots} />}
        rowCount={days.length}
        selection={selection}
        onBeforeVerticalMove={(rowDelta) => {
          const fromSlots = slotsAt(matrix, columns, days, selection.active.row, selection.active.col, timeZone);
          const toSlots = slotsAt(matrix, columns, days, selection.active.row + rowDelta, selection.active.col, timeZone);
          const step = stackIndexAfterMove({
            fromIndex: stackIndexRef.current,
            rowDelta,
            fromCount: fromSlots.length,
            toCount: toSlots.length
          });
          if (step.stay) {
            stackEntryRef.current = null;
            stackIndexRef.current = step.index;
            setStackIndex(step.index);
            const slot = fromSlots[step.index];
            if (slot) {
              onSelectSlot?.(slot.id);
            }
            return true;
          }
          stackEntryRef.current = step.index;
          return false;
        }}
        onCommand={(command) => {
          if (command.type === "edit") {
            const row = command.row ?? selection.active.row;
            const col = command.col ?? selection.active.col;
            if (readOnly || !slotAt(matrix, columns, days, row, col, timeZone, stackIndexRef.current)) {
              return;
            }
            const assignment = assignmentFor(matrix, { active: { row, col }, anchor: { row, col } }, columns, days, timeZone, stackIndexRef.current);
            setEditor({ filter: command.filter, manualOverride: assignment?.manual_override === true });
            return;
          }
          if (command.type === "cancel") {
            setEditor(null);
            return;
          }
          if (readOnly) {
            return;
          }
          if (command.type === "clear") {
            void applyItems(
              selectedItems(() => null),
              "all_or_nothing",
              "Clear"
            );
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
            const range = rangeOf(selection);
            const items: RosterChangeWrite[] = [];
            for (let row = range.rowStart + 1; row <= range.rowEnd; row += 1) {
              for (let col = range.colStart; col <= range.colEnd; col += 1) {
                const slot = slotAt(matrix, columns, days, row, col, timeZone, stackIndexRef.current);
                if (slot) {
                  items.push({ rosterSlotId: slot.id, teamMemberId: memberAt(matrix, columns, days, range.rowStart, col, timeZone, stackIndexRef.current) });
                }
              }
            }
            void applyItems(items, "all_or_nothing", "Fill down");
            return;
          }
          if (command.type === "fill-right") {
            const range = rangeOf(selection);
            const items: RosterChangeWrite[] = [];
            for (let row = range.rowStart; row <= range.rowEnd; row += 1) {
              for (let col = range.colStart + 1; col <= range.colEnd; col += 1) {
                const slot = slotAt(matrix, columns, days, row, col, timeZone, stackIndexRef.current);
                if (slot) {
                  items.push({ rosterSlotId: slot.id, teamMemberId: memberAt(matrix, columns, days, row, range.colStart, timeZone, stackIndexRef.current) });
                }
              }
            }
            void applyItems(items, "all_or_nothing", "Fill right");
            return;
          }
          if (command.type === "undo") {
            void undo();
            return;
          }
          if (command.type === "redo") {
            void redo();
          }
        }}
        onSelectionChange={(next) => {
          const moved = next.active.row !== selection.active.row || next.active.col !== selection.active.col;
          const entered = stackEntryRef.current;
          stackEntryRef.current = null;
          const index = moved ? (entered ?? 0) : stackIndexRef.current;
          if (moved) {
            stackIndexRef.current = index;
            setStackIndex(index);
          }
          setEditor(null);
          setSelection(next);
          const slot = slotAt(matrix, columns, days, next.active.row, next.active.col, timeZone, index);
          if (slot) {
            onSelectSlot?.(slot.id);
          }
        }}
      />
      {editor && activeSlot ? (
        <MemberPicker
          fairnessAccounts={fairnessAccounts}
          filter={editor.filter}
          locale={locale}
          manualOverride={editor.manualOverride}
          matrix={matrix}
          slotId={activeSlot.id}
          timeZone={timeZone}
          onManualOverride={(manualOverride) => setEditor((current) => (current ? { ...current, manualOverride } : current))}
          onOpenChange={(open) => {
            if (!open) {
              setEditor(null);
              window.setTimeout(() => document.querySelector<HTMLElement>("[data-grid-active='true']")?.focus(), 0);
            }
          }}
          onSelect={(memberId) => void saveOne(memberId, editor.manualOverride)}
        />
      ) : null}
    </div>
  );
}

function DayHeader({ date, locale, slots }: { date: string; locale: Locale; slots: RosterMatrix["slots"] }) {
  const dayClass = slots.find((slot) => slot.slot_date === date)?.day_class;
  const formatted = new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-GB", {
    weekday: "short",
    day: "2-digit",
    month: "2-digit"
  }).format(new Date(`${date}T12:00:00`));
  return (
    <span className="truncate font-medium text-ink">
      {formatted}
      {dayClass ? ` · ${dayClass}` : ""}
    </span>
  );
}

function RosterGridCell({
  matrix,
  slotDate,
  column,
  warnings,
  swapSlotIds,
  duplicateMemberDayKeys,
  locale,
  timeZone,
  active,
  activeSlotId,
  onActivate
}: {
  matrix: RosterMatrix;
  slotDate: string;
  column: RosterGridColumn | undefined;
  warnings: WarningHint[];
  swapSlotIds: Set<number>;
  duplicateMemberDayKeys?: ReadonlySet<string>;
  locale: Locale;
  timeZone: string;
  active: boolean;
  activeSlotId: number | null;
  onActivate: (slotId: number) => void;
}) {
  if (!column) {
    return null;
  }
  const slots = slotsForColumn(matrix.slots, slotDate, column, timeZone);
  if (slots.length === 0) {
    return <span className="text-muted">{t(locale, "emptyValue")}</span>;
  }
  return (
    <span className="flex min-w-0 flex-col gap-1">
      {slots.map((slot) => (
        <SlotChip
          key={slot.id}
          active={active && slot.id === activeSlotId}
          duplicateMemberDayKeys={duplicateMemberDayKeys}
          locale={locale}
          matrix={matrix}
          slot={slot}
          swapSlotIds={swapSlotIds}
          timeZone={timeZone}
          warnings={warnings}
          onActivate={onActivate}
        />
      ))}
    </span>
  );
}

function SlotChip({
  matrix,
  slot,
  warnings,
  swapSlotIds,
  duplicateMemberDayKeys,
  locale,
  timeZone,
  active,
  onActivate
}: {
  matrix: RosterMatrix;
  slot: RosterColumnSlot;
  warnings: WarningHint[];
  swapSlotIds: Set<number>;
  duplicateMemberDayKeys?: ReadonlySet<string>;
  locale: Locale;
  timeZone: string;
  active: boolean;
  onActivate: (slotId: number) => void;
}) {
  const assignment = matrix.assignments.find((row) => row.roster_slot_id === slot.id);
  const member = assignment ? matrix.team_members.find((row) => row.id === assignment.team_member_id) : undefined;
  const definitions = matrix.day_status_definitions ?? [];
  const cell = assignment
    ? matrix.planning_cells.find((row) => row.cell_date === slot.slot_date && row.team_member_id === assignment.team_member_id)
    : undefined;
  const statusRow = cell?.status ? planningDayStatusByCode(definitions).get(cell.status) : undefined;
  const blocking = Boolean(cell?.status && rosterBlocksForPlanningDayStatusCode(cell.status, definitions));
  const intent = assignment
    ? matrix.shift_intents?.find(
        (row) =>
          row.cell_date === slot.slot_date &&
          row.team_member_id === assignment.team_member_id &&
          row.shift_template_id === slot.shift_template_id &&
          intentBandCoversSlot(row.band, isNightRosterSlot(slot, timeZone))
      )
    : undefined;
  const severity = severityFor(slot.id, slot.slot_date, assignment?.team_member_id ?? null, warnings);
  const tone = blocking ? "error" : severity;
  return (
    <span
      className={`flex min-w-0 items-center gap-1 rounded-sm ${tone === "error" ? "bg-severity-error" : tone === "warning" ? "bg-severity-warning" : tone === "info" ? "bg-severity-info" : ""} ${active ? "ring-1 ring-ink" : ""}`}
      data-roster-slot={slot.id}
      title={formatShiftTimeRange(slot.starts_at ?? null, slot.ends_at ?? null, timeZone)}
      onClick={(event) => {
        event.stopPropagation();
        onActivate(slot.id);
      }}
    >
      <span className={`h-2 w-2 shrink-0 rounded-full ${statusRow ? planningDayStatusSolidClass(statusRow.color_preset) : "bg-slate-300"}`} />
      <span className="truncate font-medium text-ink">{member ? teamMemberPlanningDisplayName(member) : t(locale, "emptyValue")}</span>
      {intent?.kind === "wish" ? <IntentChip kind="wish" locale={locale} /> : null}
      {intent?.kind === "no_go" && !assignment?.manual_override ? <IntentChip kind="no_go" locale={locale} /> : null}
      {blocking ? <span className="text-danger">{t(locale, "conflict")}</span> : null}
      {assignment && duplicateMemberDayKeys?.has(`${assignment.team_member_id}:${slot.slot_date}`) ? (
        <span className="text-warning">{t(locale, "rosterDuplicateDayInline")}</span>
      ) : null}
      {statusRow && blocking ? (
        <span className={`rounded-token-sm px-1 ring-1 ${planningDayStatusBadgeClass(statusRow.color_preset)}`}>
          {planningDayStatusLabel(statusRow, locale)}
        </span>
      ) : null}
      {cell?.comment?.trim() ? <span className="text-info">{t(locale, "dayCommentMarker")}</span> : null}
      {assignment?.manual_override ? <span className="h-1.5 w-1.5 rounded-full bg-warning" title={t(locale, "manualOverride")} /> : null}
      {swapSlotIds.has(slot.id) ? <span className="rounded-token-sm bg-severity-warning px-1">{t(locale, "rosterSwapBadge")}</span> : null}
    </span>
  );
}

function MemberPicker({
  matrix,
  slotId,
  locale,
  filter,
  manualOverride,
  fairnessAccounts,
  timeZone,
  onManualOverride,
  onSelect,
  onOpenChange
}: {
  matrix: RosterMatrix;
  slotId: number;
  locale: Locale;
  filter: string;
  manualOverride: boolean;
  fairnessAccounts: FairnessAccountsRead | null;
  timeZone: string;
  onManualOverride: (value: boolean) => void;
  onSelect: (memberId: number | "") => void;
  onOpenChange: (open: boolean) => void;
}) {
  const [query, setQuery] = useState(filter);
  const anchorRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const node = document.querySelector<HTMLElement>("[data-grid-active='true']");
    const anchor = anchorRef.current;
    if (!node || !anchor) {
      return;
    }
    const box = node.getBoundingClientRect();
    anchor.style.position = "fixed";
    anchor.style.top = `${box.top}px`;
    anchor.style.left = `${box.left}px`;
    anchor.style.width = `${box.width}px`;
    anchor.style.height = `${box.height}px`;
  }, []);
  const needle = query.trim().toLowerCase();
  const slot = matrix.slots.find((row) => row.id === slotId);
  const fairnessIndex = indexFairnessMembers(fairnessAccounts);
  const dimension =
    slot && fairnessAccounts
      ? relevantFairnessDimension(
          {
            slot_date: slot.slot_date,
            starts_at: slot.starts_at,
            ends_at: slot.ends_at,
            day_class: slot.day_class,
            category: slot.category
          },
          fairnessAccounts.dimensions ?? [],
          timeZone
        )
      : undefined;
  const windowLabel = fairnessAccounts ? formatFairnessWindowRange(fairnessAccounts.window) : "";
  const matched = matrix.team_members.filter((member) => {
    if (!needle) {
      return true;
    }
    return (
      teamMemberPlanningDisplayName(member).toLowerCase().includes(needle) ||
      member.email.toLowerCase().includes(needle) ||
      member.first_name.toLowerCase().includes(needle) ||
      member.last_name.toLowerCase().includes(needle)
    );
  });
  const members = dimension
    ? [...matched].sort((left, right) => {
        const leftDeviation = fairnessValueForMember(fairnessIndex, left.id, dimension.id)?.deviation_absolute ?? 0;
        const rightDeviation = fairnessValueForMember(fairnessIndex, right.id, dimension.id)?.deviation_absolute ?? 0;
        if (leftDeviation !== rightDeviation) {
          return leftDeviation - rightDeviation;
        }
        return teamMemberPlanningDisplayName(left).localeCompare(teamMemberPlanningDisplayName(right), undefined, { sensitivity: "base" });
      })
    : matched;
  return (
    <Combobox open onOpenChange={onOpenChange}>
      <ComboboxAnchor ref={anchorRef} className="pointer-events-none" />
      <ComboboxContent
        className="w-80"
        shouldFilter={false}
        onKeyDown={(event) => event.stopPropagation()}
      >
        <ComboboxInput
          aria-label={t(locale, "searchTeamMembersPlaceholder")}
          autoFocus
          placeholder={t(locale, "searchTeamMembersPlaceholder")}
          value={query}
          onValueChange={setQuery}
        />
        <ComboboxList>
          <button className="w-full px-3 py-2 text-left text-xs text-muted" type="button" onClick={() => onSelect("")}>
            {t(locale, "emptyValue")}
          </button>
          {members.map((member) => {
            const value = dimension ? fairnessValueForMember(fairnessIndex, member.id, dimension.id) : undefined;
            const deviation = value && dimension ? formatFairnessDeviation(value.deviation_absolute, dimension.metric, locale) : null;
            return (
              <ComboboxItem key={member.id} value={String(member.id)} onSelect={() => onSelect(member.id)}>
                <span className="min-w-0 flex-1 truncate font-medium text-ink">{teamMemberPlanningDisplayName(member)}</span>
                {value && dimension && deviation ? (
                  <span
                    className={`shrink-0 rounded-md px-1.5 py-0.5 font-mono text-[0.65rem] font-semibold tabular-nums ring-1 ${fairnessDeviationChipClass(value.deviation_absolute)}`}
                    title={t(locale, "fairnessPickerDeviationTitle", {
                      dimension: fairnessDimensionLabel(locale, dimension),
                      window: windowLabel,
                      value: deviation
                    })}
                  >
                    {`Δ ${deviation}`}
                  </span>
                ) : null}
              </ComboboxItem>
            );
          })}
        </ComboboxList>
        <label className="flex items-center gap-2 border-t border-default px-3 py-2 text-xs text-muted">
          <input checked={manualOverride} type="checkbox" onChange={(event) => onManualOverride(event.target.checked)} />
          {t(locale, "manualOverrideAbbr")}
        </label>
        <span className="sr-only">{slotId}</span>
      </ComboboxContent>
    </Combobox>
  );
}

function slotsAt(
  matrix: RosterMatrix | null,
  columns: RosterGridColumn[],
  days: { date: string }[],
  row: number,
  col: number,
  timeZone: string
) {
  const column = columns[col];
  const date = days[row]?.date;
  if (!matrix || !column || !date) {
    return [];
  }
  return slotsForColumn(matrix.slots, date, column, timeZone);
}

function slotAt(
  matrix: RosterMatrix | null,
  columns: RosterGridColumn[],
  days: { date: string }[],
  row: number,
  col: number,
  timeZone: string,
  stackIndex: number
) {
  const slots = slotsAt(matrix, columns, days, row, col, timeZone);
  if (slots.length === 0) {
    return null;
  }
  return slots[Math.min(Math.max(stackIndex, 0), slots.length - 1)] ?? null;
}

function memberAt(
  matrix: RosterMatrix,
  columns: RosterGridColumn[],
  days: { date: string }[],
  row: number,
  col: number,
  timeZone: string,
  stackIndex: number
): number | null {
  const slot = slotAt(matrix, columns, days, row, col, timeZone, stackIndex);
  if (!slot) {
    return null;
  }
  return matrix.assignments.find((item) => item.roster_slot_id === slot.id)?.team_member_id ?? null;
}

function assignmentFor(
  matrix: RosterMatrix,
  selection: GridSelection,
  columns: RosterGridColumn[],
  days: { date: string }[],
  timeZone: string,
  stackIndex: number
) {
  const slot = slotAt(matrix, columns, days, selection.active.row, selection.active.col, timeZone, stackIndex);
  return slot ? matrix.assignments.find((item) => item.roster_slot_id === slot.id) : undefined;
}

function severityFor(slotId: number, date: string, memberId: number | null, warnings: WarningHint[]): WarningHint["severity"] | null {
  let best: WarningHint["severity"] | null = null;
  const rank = { info: 1, warning: 2, error: 3 };
  for (const warning of warnings) {
    const ids = listedSlotIds(warning.details);
    const matchesSlot = ids.includes(slotId);
    const matchesMember = memberId != null && warning.team_member_id === memberId && warning.date === date;
    if (!matchesSlot && !matchesMember) {
      continue;
    }
    if (!best || rank[warning.severity] > rank[best]) {
      best = warning.severity;
    }
  }
  return best;
}

function listedSlotIds(details: Record<string, unknown>): number[] {
  const ids: number[] = [];
  for (const key of ["roster_slot_id", "related_roster_slot_id"]) {
    const value = details[key];
    if (typeof value === "number") {
      ids.push(value);
    }
  }
  for (const key of ["conflicting_roster_slot_ids", "violating_roster_slot_ids", "source_roster_slot_ids", "roster_slot_ids"]) {
    const value = details[key];
    if (Array.isArray(value)) {
      for (const item of value) {
        if (typeof item === "number") {
          ids.push(item);
        }
      }
    }
  }
  return ids;
}
