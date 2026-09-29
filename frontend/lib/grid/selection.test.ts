import { describe, expect, it } from "vitest";
import {
  cellSelected,
  cellsInSelection,
  moveActive,
  rangeOf,
  selectAll,
  selectColumn,
  selectRow,
  selectionAt
} from "@/lib/grid/selection";

const bounds = { rows: 10, cols: 4 };

describe("grid selection", () => {
  it("moves the active cell and collapses the range", () => {
    const next = moveActive(selectionAt({ row: 1, col: 1 }, bounds), 1, 0, bounds, false, false);
    expect(next.active).toEqual({ row: 2, col: 1 });
    expect(next.anchor).toEqual(next.active);
  });

  it("extends a rectangle with shift movement", () => {
    const start = selectionAt({ row: 2, col: 1 }, bounds);
    const next = moveActive(start, 2, 1, bounds, true, false);
    expect(rangeOf(next)).toEqual({ rowStart: 2, rowEnd: 4, colStart: 1, colEnd: 2 });
    expect(cellsInSelection(next)).toHaveLength(6);
    expect(cellSelected(next, { row: 3, col: 2 })).toBe(true);
    expect(cellSelected(next, { row: 1, col: 1 })).toBe(false);
  });

  it("selects a row, a column, and the whole grid", () => {
    const start = selectionAt({ row: 3, col: 2 }, bounds);
    expect(rangeOf(selectRow(start, bounds))).toEqual({ rowStart: 3, rowEnd: 3, colStart: 0, colEnd: 3 });
    expect(rangeOf(selectColumn(start, bounds))).toEqual({ rowStart: 0, rowEnd: 9, colStart: 2, colEnd: 2 });
    expect(cellsInSelection(selectAll(bounds))).toHaveLength(40);
  });

  it("clamps movement at the edges and wraps tab", () => {
    const edge = moveActive(selectionAt({ row: 0, col: 0 }, bounds), -1, -1, bounds, false, false);
    expect(edge.active).toEqual({ row: 0, col: 0 });
    const wrapped = moveActive(selectionAt({ row: 0, col: 3 }, bounds), 0, 1, bounds, false, true);
    expect(wrapped.active).toEqual({ row: 1, col: 0 });
  });
});
