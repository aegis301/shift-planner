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

  it("keeps the earlier revert when two sets are undone", () => {
    const first = pushCreatedSet({ undo: [], redo: [] }, 1);
    const second = pushCreatedSet(first, 2);
    const undoneLatest = pushUndoResult(second, 2, 3);
    const undoneBoth = pushUndoResult(undoneLatest, 1, 4);
    expect(undoneBoth).toEqual({ undo: [], redo: [3, 4] });
    expect(pushRedoResult(undoneBoth, 4, 5)).toEqual({ undo: [5], redo: [3] });
    expect(
      rebuildUndoStacks(
        [
          set({ id: 1, status: "reverted" }),
          set({ id: 2, status: "reverted" }),
          set({ id: 3, status: "applied", reverts_change_set_id: 2 }),
          set({ id: 4, status: "applied", reverts_change_set_id: 1 })
        ],
        user
      )
    ).toEqual({ undo: [], redo: [3, 4] });
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

  it("ignores a set that did not apply any assignment", () => {
    expect(
      rebuildUndoStacks(
        [
          set({
            id: 2,
            status: "applied",
            items: [{ outcome: "unchanged" }, { outcome: "unchanged" }]
          })
        ],
        user
      )
    ).toEqual({ undo: [], redo: [] });
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
