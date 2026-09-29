export type CellCoord = {
  row: number;
  col: number;
};

export type GridSelection = {
  active: CellCoord;
  anchor: CellCoord;
};

export type GridBounds = {
  rows: number;
  cols: number;
};

export function clampCell(cell: CellCoord, bounds: GridBounds): CellCoord {
  return {
    row: Math.min(Math.max(cell.row, 0), Math.max(bounds.rows - 1, 0)),
    col: Math.min(Math.max(cell.col, 0), Math.max(bounds.cols - 1, 0))
  };
}

export function selectionAt(cell: CellCoord, bounds: GridBounds): GridSelection {
  const next = clampCell(cell, bounds);
  return { active: next, anchor: next };
}

export function moveActive(
  selection: GridSelection,
  rowDelta: number,
  colDelta: number,
  bounds: GridBounds,
  extend: boolean,
  wrap: boolean
): GridSelection {
  let row = selection.active.row + rowDelta;
  let col = selection.active.col + colDelta;
  if (wrap && bounds.cols > 0) {
    while (col >= bounds.cols) {
      col -= bounds.cols;
      row += 1;
    }
    while (col < 0) {
      col += bounds.cols;
      row -= 1;
    }
  }
  const active = clampCell({ row, col }, bounds);
  return { active, anchor: extend ? selection.anchor : active };
}

export function rangeOf(selection: GridSelection): {
  rowStart: number;
  rowEnd: number;
  colStart: number;
  colEnd: number;
} {
  return {
    rowStart: Math.min(selection.anchor.row, selection.active.row),
    rowEnd: Math.max(selection.anchor.row, selection.active.row),
    colStart: Math.min(selection.anchor.col, selection.active.col),
    colEnd: Math.max(selection.anchor.col, selection.active.col)
  };
}

export function cellsInSelection(selection: GridSelection): CellCoord[] {
  const range = rangeOf(selection);
  const cells: CellCoord[] = [];
  for (let row = range.rowStart; row <= range.rowEnd; row += 1) {
    for (let col = range.colStart; col <= range.colEnd; col += 1) {
      cells.push({ row, col });
    }
  }
  return cells;
}

export function cellSelected(selection: GridSelection, cell: CellCoord): boolean {
  const range = rangeOf(selection);
  return cell.row >= range.rowStart && cell.row <= range.rowEnd && cell.col >= range.colStart && cell.col <= range.colEnd;
}

export function selectRow(selection: GridSelection, bounds: GridBounds): GridSelection {
  return {
    anchor: { row: selection.active.row, col: 0 },
    active: { row: selection.active.row, col: Math.max(bounds.cols - 1, 0) }
  };
}

export function selectColumn(selection: GridSelection, bounds: GridBounds): GridSelection {
  return {
    anchor: { row: 0, col: selection.active.col },
    active: { row: Math.max(bounds.rows - 1, 0), col: selection.active.col }
  };
}

export function selectAll(bounds: GridBounds): GridSelection {
  return {
    anchor: { row: 0, col: 0 },
    active: { row: Math.max(bounds.rows - 1, 0), col: Math.max(bounds.cols - 1, 0) }
  };
}

export function jumpToEdge(selection: GridSelection, edge: "start" | "end" | "origin" | "limit", bounds: GridBounds, extend: boolean): GridSelection {
  const active =
    edge === "start"
      ? { row: selection.active.row, col: 0 }
      : edge === "end"
        ? { row: selection.active.row, col: Math.max(bounds.cols - 1, 0) }
        : edge === "origin"
          ? { row: 0, col: 0 }
          : { row: Math.max(bounds.rows - 1, 0), col: Math.max(bounds.cols - 1, 0) };
  const next = clampCell(active, bounds);
  return { active: next, anchor: extend && edge !== "origin" && edge !== "limit" ? selection.anchor : next };
}
