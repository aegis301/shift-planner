import { describe, expect, it } from "vitest";
import { pushCreatedSet, pushRedoResult, pushUndoResult, rebuildUndoStacks, type HistoryChangeSet } from "@/lib/grid/undoStack";

const user = { id: 7, email: "planner@example.com" };

function set(partial: Partial<HistoryChangeSet> & Pick<HistoryChangeSet, "id" | "status">): HistoryChangeSet {
  return {
    created_by_user_id: user.id,
    actor: user.email,
    reverts_change_set_id: null,
    ...partial
  };
}

describe("undo stacks", () => {
  it("pushes a created set and records undo and redo", () => {
    const created = pushCreatedSet({ undo: [], redo: [] }, 4);
    const undone = pushUndoResult(created, 4, 9);
    expect(undone).toEqual({ undo: [], redo: [9] });
    expect(pushRedoResult(undone, 9, 12)).toEqual({ undo: [12], redo: [] });
  });

  it("rebuilds the stack from history after a reload", () => {
    const history = [
      set({ id: 4, status: "reverted" }),
      set({ id: 5, status: "applied" }),
      set({ id: 9, status: "applied", reverts_change_set_id: 4 }),
      set({ id: 3, status: "applied", created_by_user_id: 99, actor: "other@example.com" })
    ];
    expect(rebuildUndoStacks(history, user)).toEqual({ undo: [5], redo: [9] });
  });

  it("treats reverting a revert as redo", () => {
    const history = [
      set({ id: 4, status: "reverted" }),
      set({ id: 9, status: "reverted", reverts_change_set_id: 4 }),
      set({ id: 12, status: "applied", reverts_change_set_id: 9 })
    ];
    expect(rebuildUndoStacks(history, user)).toEqual({ undo: [12], redo: [] });
  });
});
