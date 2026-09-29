export type HistoryChangeSet = {
  id: number;
  status: "applied" | "refused" | "partially_applied" | "reverted";
  created_by_user_id?: number | null;
  actor: string;
  reverts_change_set_id?: number | null;
};

export type UndoStacks = {
  undo: number[];
  redo: number[];
};

export function emptyUndoStacks(): UndoStacks {
  return { undo: [], redo: [] };
}

export function pushCreatedSet(stacks: UndoStacks, changeSetId: number): UndoStacks {
  return { undo: [...stacks.undo, changeSetId], redo: [] };
}

export function pushUndoResult(stacks: UndoStacks, revertedId: number, revertSetId: number): UndoStacks {
  return {
    undo: stacks.undo.filter((id) => id !== revertedId),
    redo: [...stacks.redo, revertSetId]
  };
}

export function pushRedoResult(stacks: UndoStacks, redoSourceId: number, restoredSetId: number): UndoStacks {
  return {
    undo: [...stacks.undo.filter((id) => id !== redoSourceId), restoredSetId],
    redo: stacks.redo.filter((id) => id !== redoSourceId)
  };
}

function ownedBy(set: HistoryChangeSet, user: { id: number; email: string }): boolean {
  return set.created_by_user_id === user.id || set.actor === user.email;
}

function isLive(status: HistoryChangeSet["status"]): boolean {
  return status === "applied" || status === "partially_applied";
}

export function rebuildUndoStacks(sets: HistoryChangeSet[], user: { id: number; email: string }): UndoStacks {
  const ordered = sets.filter((set) => ownedBy(set, user) && set.status !== "refused").slice().sort((left, right) => left.id - right.id);
  let undo: number[] = [];
  let redo: number[] = [];
  for (const set of ordered) {
    if (set.reverts_change_set_id == null) {
      if (isLive(set.status)) {
        undo = [...undo, set.id];
        redo = [];
      } else if (set.status === "reverted") {
        undo = undo.filter((id) => id !== set.id);
      }
      continue;
    }
    if (!isLive(set.status)) {
      if (set.status === "reverted") {
        redo = redo.filter((id) => id !== set.id);
        undo = undo.filter((id) => id !== set.id);
      }
      continue;
    }
    const target = ordered.find((row) => row.id === set.reverts_change_set_id);
    if (target?.reverts_change_set_id != null) {
      redo = redo.filter((id) => id !== set.reverts_change_set_id);
      undo = [...undo, set.id];
      continue;
    }
    undo = undo.filter((id) => id !== set.reverts_change_set_id);
    redo = [...redo, set.id];
  }
  return { undo, redo };
}
