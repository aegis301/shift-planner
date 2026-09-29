import { describe, expect, it } from "vitest";
import { commandFromKey, selectionAfterCommand } from "@/lib/grid/keyboard";
import { selectionAt } from "@/lib/grid/selection";

const bounds = { rows: 31, cols: 8 };
const idle = { shiftKey: false, ctrlKey: false, metaKey: false, altKey: false };

describe("grid keyboard", () => {
  it("maps arrows, week paging, home and end", () => {
    const start = selectionAt({ row: 10, col: 3 }, bounds);
    expect(selectionAfterCommand(start, commandFromKey({ ...idle, key: "ArrowLeft" })!, bounds).active).toEqual({ row: 10, col: 2 });
    expect(selectionAfterCommand(start, commandFromKey({ ...idle, key: "PageDown" })!, bounds).active.row).toBe(17);
    expect(selectionAfterCommand(start, commandFromKey({ ...idle, key: "Home" })!, bounds).active).toEqual({ row: 10, col: 0 });
    expect(selectionAfterCommand(start, commandFromKey({ ...idle, key: "End" })!, bounds).active.col).toBe(7);
    expect(selectionAfterCommand(start, commandFromKey({ ...idle, key: "Home", ctrlKey: true })!, bounds).active).toEqual({ row: 0, col: 0 });
    expect(selectionAfterCommand(start, commandFromKey({ ...idle, key: "End", metaKey: true })!, bounds).active).toEqual({ row: 30, col: 7 });
  });

  it("extends with shift and selects structural ranges", () => {
    expect(commandFromKey({ ...idle, key: "ArrowDown", shiftKey: true })).toMatchObject({ type: "move", extend: true, rowDelta: 1 });
    expect(commandFromKey({ ...idle, key: " ", shiftKey: true })?.type).toBe("select-row");
    expect(commandFromKey({ ...idle, key: " ", ctrlKey: true })?.type).toBe("select-column");
    expect(commandFromKey({ ...idle, key: "a", ctrlKey: true })?.type).toBe("select-all");
  });

  it("opens the editor, clears, fills, and undoes", () => {
    expect(commandFromKey({ ...idle, key: "Enter" })).toEqual({ type: "edit", filter: "" });
    expect(commandFromKey({ ...idle, key: "F2" })).toEqual({ type: "edit", filter: "" });
    expect(commandFromKey({ ...idle, key: "n" })).toEqual({ type: "edit", filter: "n" });
    expect(commandFromKey({ ...idle, key: "Escape" })?.type).toBe("cancel");
    expect(commandFromKey({ ...idle, key: "Delete" })?.type).toBe("clear");
    expect(commandFromKey({ ...idle, key: "Backspace" })?.type).toBe("clear");
    expect(commandFromKey({ ...idle, key: "d", ctrlKey: true })?.type).toBe("fill-down");
    expect(commandFromKey({ ...idle, key: "r", metaKey: true })?.type).toBe("fill-right");
    expect(commandFromKey({ ...idle, key: "z", ctrlKey: true })?.type).toBe("undo");
    expect(commandFromKey({ ...idle, key: "y", ctrlKey: true })?.type).toBe("redo");
    expect(commandFromKey({ ...idle, key: "z", ctrlKey: true, shiftKey: true })?.type).toBe("redo");
    expect(commandFromKey({ ...idle, key: "c", ctrlKey: true })?.type).toBe("copy");
    expect(commandFromKey({ ...idle, key: "v", ctrlKey: true })?.type).toBe("paste");
  });
});
