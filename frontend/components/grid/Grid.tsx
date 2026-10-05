"use client";

import { useEffect, useRef, useSyncExternalStore, type ReactNode } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { createColumnHelper, getCoreRowModel, useReactTable } from "@tanstack/react-table";
import { cn } from "@/components/ui/cn";
import { commandFromKey, selectionAfterCommand, type GridCommand } from "@/lib/grid/keyboard";
import {
  cellSelected,
  selectAll,
  selectColumn,
  selectRow,
  selectionAt,
  type GridSelection
} from "@/lib/grid/selection";

export type GridColumnModel = {
  id: string;
  header: string;
  group: string;
};

const DAY_WIDTH = 168;
const COLUMN_WIDTH = 152;

function useDensity(): "compact" | "comfortable" {
  return useSyncExternalStore(
    (onStoreChange) => {
      const observer = new MutationObserver(onStoreChange);
      observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-density"] });
      return () => observer.disconnect();
    },
    () => (document.documentElement.dataset.density === "compact" ? "compact" : "comfortable"),
    () => "comfortable"
  );
}

type HeaderRow = { id: string };

const columnHelper = createColumnHelper<HeaderRow>();

export function Grid({
  label,
  rowCount,
  columns,
  cornerLabel,
  renderRowHeader,
  renderCell,
  selection,
  onSelectionChange,
  onCommand,
  onBeforeVerticalMove,
  editable = true,
  editing = false,
  rowHeight,
  getRowSize
}: {
  label: string;
  rowCount: number;
  columns: GridColumnModel[];
  cornerLabel: string;
  renderRowHeader: (row: number) => ReactNode;
  renderCell: (row: number, col: number) => ReactNode;
  selection: GridSelection;
  onSelectionChange: (selection: GridSelection) => void;
  onCommand: (command: GridCommand) => void;
  onBeforeVerticalMove?: (rowDelta: number) => boolean;
  editable?: boolean;
  editing?: boolean;
  rowHeight?: number;
  getRowSize?: (row: number) => number;
}) {
  const density = useDensity();
  const resolvedRowHeight = rowHeight ?? (density === "compact" ? 36 : 52);
  const parentRef = useRef<HTMLDivElement>(null);
  const focusAfterKey = useRef(false);
  const bounds = { rows: rowCount, cols: columns.length };
  const table = useReactTable({
    data: [] as HeaderRow[],
    columns: [
      columnHelper.display({ id: "day", header: cornerLabel, size: DAY_WIDTH }),
      ...groupColumns(columns).map((group) =>
        columnHelper.group({
          id: `group-${group.columns[0]?.id ?? group.header}`,
          header: group.header,
          columns: group.columns.map((column) =>
            columnHelper.display({
              id: column.id,
              header: column.header,
              size: COLUMN_WIDTH
            })
          )
        })
      )
    ],
    state: { columnPinning: { left: ["day"] } },
    getCoreRowModel: getCoreRowModel()
  });
  const rowVirtualizer = useVirtualizer({
    count: rowCount,
    getScrollElement: () => parentRef.current,
    estimateSize: (index) => getRowSize?.(index) ?? resolvedRowHeight,
    overscan: 8
  });
  const columnVirtualizer = useVirtualizer({
    horizontal: true,
    count: columns.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => COLUMN_WIDTH,
    overscan: 4
  });

  const rowVirtualizerRef = useRef(rowVirtualizer);
  rowVirtualizerRef.current = rowVirtualizer;
  useEffect(() => {
    rowVirtualizerRef.current.measure();
  }, [getRowSize, resolvedRowHeight, rowCount]);

  useEffect(() => {
    rowVirtualizer.scrollToIndex(selection.active.row, { align: "auto" });
    columnVirtualizer.scrollToIndex(selection.active.col, { align: "auto" });
  }, [columnVirtualizer, rowVirtualizer, selection.active.col, selection.active.row]);

  useEffect(() => {
    if (!focusAfterKey.current || editing) {
      return;
    }
    focusAfterKey.current = false;
    parentRef.current?.querySelector<HTMLElement>("[data-grid-active='true']")?.focus();
  });

  function applySelection(next: GridSelection) {
    focusAfterKey.current = true;
    onSelectionChange(next);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (editing) {
      return;
    }
    const command = commandFromKey({
      key: event.key,
      shiftKey: event.shiftKey,
      ctrlKey: event.ctrlKey,
      metaKey: event.metaKey,
      altKey: event.altKey
    });
    if (!command || bounds.cols === 0 || bounds.rows === 0) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    if (
      command.type === "move" &&
      command.colDelta === 0 &&
      (command.rowDelta === 1 || command.rowDelta === -1) &&
      !command.extend &&
      onBeforeVerticalMove?.(command.rowDelta)
    ) {
      return;
    }
    if (command.type === "move" || command.type === "edge") {
      applySelection(selectionAfterCommand(selection, command, bounds));
      return;
    }
    if (command.type === "select-row") {
      applySelection(selectRow(selection, bounds));
      return;
    }
    if (command.type === "select-column") {
      applySelection(selectColumn(selection, bounds));
      return;
    }
    if (command.type === "select-all") {
      applySelection(selectAll(bounds));
      return;
    }
    onCommand(command);
  }

  const headerGroups = table.getHeaderGroups();
  const width = DAY_WIDTH + columnVirtualizer.getTotalSize();

  return (
    <div
      ref={parentRef}
      aria-colcount={columns.length + 1}
      aria-label={label}
      aria-rowcount={rowCount + headerGroups.length}
      className="max-h-[70vh] overflow-auto rounded-token-lg border border-default bg-surface"
      onKeyDown={onKeyDown}
      role="grid"
    >
      <div style={{ width }}>
        <div className="sticky top-0 z-20 bg-surface">
          {headerGroups.map((group, groupIndex) => (
            <div key={group.id} className="relative flex border-b border-default" role="row" style={{ height: density === "compact" ? 28 : 36 }}>
              {groupIndex === 0 ? (
                <div
                  className="sticky left-0 z-30 flex items-end border-r border-default bg-surface px-[var(--space-cell-x)] text-xs font-semibold text-muted"
                  role="columnheader"
                  style={{ width: DAY_WIDTH, height: headerGroups.length * (density === "compact" ? 28 : 36) }}
                >
                  {cornerLabel}
                </div>
              ) : (
                <div className="sticky left-0 z-30 border-r border-default bg-surface" style={{ width: DAY_WIDTH }} />
              )}
              {group.headers
                .filter((header) => header.column.id !== "day")
                .map((header) => {
                  const size = header.column.getSize();
                  return (
                    <div
                      key={header.id}
                      className="absolute flex items-end truncate px-[var(--space-cell-x)] text-xs font-semibold text-ink"
                      role="columnheader"
                      style={{ left: header.getStart(), width: size, height: "100%" }}
                    >
                      {header.isPlaceholder ? null : String(header.column.columnDef.header)}
                    </div>
                  );
                })}
            </div>
          ))}
        </div>
        <div className="relative" style={{ height: rowVirtualizer.getTotalSize() }}>
          {rowVirtualizer.getVirtualItems().map((virtualRow) => (
            <div
              key={virtualRow.key}
              aria-rowindex={virtualRow.index + headerGroups.length + 1}
              className="absolute left-0 top-0"
              role="row"
              style={{ height: virtualRow.size, transform: `translateY(${virtualRow.start}px)`, width }}
            >
              <div
                className="sticky left-0 z-10 flex h-full items-center border-b border-r border-default bg-surface px-[var(--space-cell-x)] text-[length:var(--font-size-cell)]"
                role="rowheader"
                style={{ width: DAY_WIDTH }}
              >
                {renderRowHeader(virtualRow.index)}
              </div>
              {columnVirtualizer.getVirtualItems().map((virtualColumn) => {
                const coord = { row: virtualRow.index, col: virtualColumn.index };
                const active = selection.active.row === coord.row && selection.active.col === coord.col;
                const selected = cellSelected(selection, coord);
                return (
                  <button
                    key={virtualColumn.key}
                    aria-colindex={virtualColumn.index + 2}
                    aria-haspopup={editable ? "listbox" : undefined}
                    aria-selected={selected}
                    className={cn(
                      "absolute top-0 flex h-full items-start overflow-visible border-b border-r border-default px-[var(--space-cell-x)] text-left text-[length:var(--font-size-cell)]",
                      selected && "bg-severity-info",
                      active && "outline outline-2 outline-offset-[-2px] outline-[var(--color-accent)]"
                    )}
                    data-grid-active={active ? "true" : undefined}
                    role="gridcell"
                    style={{ left: DAY_WIDTH + virtualColumn.start, width: virtualColumn.size }}
                    tabIndex={active ? 0 : -1}
                    type="button"
                    onClick={(event) => {
                      if (event.shiftKey) {
                        onSelectionChange({ active: coord, anchor: selection.anchor });
                        return;
                      }
                      onSelectionChange(selectionAt(coord, bounds));
                      if (editable) {
                        onCommand({ type: "edit", filter: "", row: coord.row, col: coord.col });
                      }
                    }}
                  >
                    {renderCell(virtualRow.index, virtualColumn.index)}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function groupColumns(columns: GridColumnModel[]): { header: string; columns: GridColumnModel[] }[] {
  const groups: { header: string; columns: GridColumnModel[] }[] = [];
  for (const column of columns) {
    const last = groups[groups.length - 1];
    if (last && last.header === column.group) {
      last.columns.push(column);
    } else {
      groups.push({ header: column.group, columns: [column] });
    }
  }
  return groups;
}
