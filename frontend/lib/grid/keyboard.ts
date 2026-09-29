import { jumpToEdge, moveActive, type GridBounds, type GridSelection } from "@/lib/grid/selection";

export type KeyInput = {
  key: string;
  shiftKey: boolean;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
};

export type GridCommand =
  | { type: "move"; rowDelta: number; colDelta: number; extend: boolean; wrap: boolean }
  | { type: "edge"; edge: "start" | "end" | "origin" | "limit"; extend: boolean }
  | { type: "select-row" }
  | { type: "select-column" }
  | { type: "select-all" }
  | { type: "edit"; filter: string }
  | { type: "cancel" }
  | { type: "clear" }
  | { type: "fill-down" }
  | { type: "fill-right" }
  | { type: "copy" }
  | { type: "paste" }
  | { type: "undo" }
  | { type: "redo" };

const WEEK_ROWS = 7;

export function commandFromKey(input: KeyInput): GridCommand | null {
  if (input.altKey) {
    return null;
  }
  const mod = input.ctrlKey || input.metaKey;
  const key = input.key;
  const lower = key.toLowerCase();
  if (mod && lower === "a") {
    return { type: "select-all" };
  }
  if (mod && lower === "c") {
    return { type: "copy" };
  }
  if (mod && lower === "v") {
    return { type: "paste" };
  }
  if (mod && lower === "d") {
    return { type: "fill-down" };
  }
  if (mod && lower === "r") {
    return { type: "fill-right" };
  }
  if (mod && lower === "y") {
    return { type: "redo" };
  }
  if (mod && lower === "z") {
    return { type: input.shiftKey ? "redo" : "undo" };
  }
  if (mod && key === " ") {
    return { type: "select-column" };
  }
  if (mod && key === "Home") {
    return { type: "edge", edge: "origin", extend: false };
  }
  if (mod && key === "End") {
    return { type: "edge", edge: "limit", extend: false };
  }
  if (!mod && input.shiftKey && key === " ") {
    return { type: "select-row" };
  }
  if (key === "ArrowUp") {
    return { type: "move", rowDelta: -1, colDelta: 0, extend: input.shiftKey, wrap: false };
  }
  if (key === "ArrowDown") {
    return { type: "move", rowDelta: 1, colDelta: 0, extend: input.shiftKey, wrap: false };
  }
  if (key === "ArrowLeft") {
    return { type: "move", rowDelta: 0, colDelta: -1, extend: input.shiftKey, wrap: false };
  }
  if (key === "ArrowRight") {
    return { type: "move", rowDelta: 0, colDelta: 1, extend: input.shiftKey, wrap: false };
  }
  if (key === "PageUp") {
    return { type: "move", rowDelta: -WEEK_ROWS, colDelta: 0, extend: input.shiftKey, wrap: false };
  }
  if (key === "PageDown") {
    return { type: "move", rowDelta: WEEK_ROWS, colDelta: 0, extend: input.shiftKey, wrap: false };
  }
  if (key === "Home") {
    return { type: "edge", edge: "start", extend: input.shiftKey };
  }
  if (key === "End") {
    return { type: "edge", edge: "end", extend: input.shiftKey };
  }
  if (key === "Tab") {
    return { type: "move", rowDelta: 0, colDelta: input.shiftKey ? -1 : 1, extend: false, wrap: true };
  }
  if (key === "Enter" || key === "F2") {
    return { type: "edit", filter: "" };
  }
  if (key === "Escape") {
    return { type: "cancel" };
  }
  if (key === "Delete" || key === "Backspace") {
    return { type: "clear" };
  }
  if (!mod && key.length === 1 && key !== " ") {
    return { type: "edit", filter: key };
  }
  return null;
}

export function selectionAfterCommand(selection: GridSelection, command: GridCommand, bounds: GridBounds): GridSelection {
  if (command.type === "move") {
    return moveActive(selection, command.rowDelta, command.colDelta, bounds, command.extend, command.wrap);
  }
  if (command.type === "edge") {
    return jumpToEdge(selection, command.edge, bounds, command.extend);
  }
  return selection;
}
