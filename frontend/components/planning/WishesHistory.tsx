"use client";

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useLocale } from "@/components/LocaleProvider";
import { ApiError } from "@/lib/api";
import { t } from "@/lib/i18n";
import { applyWishesWrites } from "@/lib/wishesEdit";
import { invalidateQueryKeys, wishesEditKeys } from "@/lib/queries/invalidation";
import { usePlanningOrganizationId } from "@/lib/queries/planning";
import {
  cellKey,
  emptyWishesUndo,
  overlayBefore,
  popWishesRedo,
  popWishesUndo,
  recordWishesEdit,
  retargetExpected,
  stampCounterpart,
  undoEntryForLanded,
  type WishesCellState,
  type WishesCellWrite,
  type WishesUndoEntry,
  type WishesUndoStacks
} from "@/lib/wishesUndo";

type WishesHistory = {
  notice: string;
  applyEdit: (before: WishesCellState[], writes: WishesCellWrite[], unresolved?: string[]) => Promise<void>;
  undo: () => Promise<void>;
  redo: () => Promise<void>;
  refresh: () => Promise<void>;
};

type PendingEdit = {
  kind: "edit";
  before: WishesCellState[];
  writes: WishesCellWrite[];
  unresolved: string[];
};

type PendingHistory = {
  kind: "undo" | "redo";
};

type Pending = PendingEdit | PendingHistory;

const WishesHistoryContext = createContext<WishesHistory | null>(null);

export function WishesHistoryProvider({
  periodId,
  shiftGroupId,
  readOnly,
  children
}: {
  periodId: string;
  shiftGroupId: string;
  readOnly: boolean;
  children: ReactNode;
}) {
  const { locale } = useLocale();
  const queryClient = useQueryClient();
  const organizationId = usePlanningOrganizationId();
  const [notice, setNotice] = useState("");
  const stacksRef = useRef<WishesUndoStacks>(emptyWishesUndo());
  const latestRef = useRef(new Map<string, WishesCellState>());
  const queueRef = useRef<Pending[]>([]);
  const runningRef = useRef(false);
  const generationRef = useRef(0);
  const scopeRef = useRef({ periodId, shiftGroupId, readOnly, locale, organizationId });
  scopeRef.current = { periodId, shiftGroupId, readOnly, locale, organizationId };

  function commitStacks(next: WishesUndoStacks) {
    stacksRef.current = next;
  }

  useEffect(() => {
    generationRef.current += 1;
    queueRef.current = [];
    latestRef.current = new Map();
    commitStacks(emptyWishesUndo());
    setNotice("");
  }, [periodId, shiftGroupId]);

  async function refresh() {
    const scope = scopeRef.current;
    if (scope.organizationId == null || scope.periodId === "" || scope.shiftGroupId === "") {
      return;
    }
    await invalidateQueryKeys(queryClient, wishesEditKeys({
      organizationId: scope.organizationId,
      periodId: scope.periodId,
      shiftGroupId: scope.shiftGroupId,
      teamMemberPortal: false
    }));
  }

  function describe(resultConflicts: { teamMemberId: number; date: string }[], unresolved: string[] = [], failure: unknown | null = null) {
    const scope = scopeRef.current;
    const parts: string[] = [];
    if (unresolved.length > 0) {
      parts.push(t(scope.locale, "wishesPasteUnresolved", { names: unresolved.join(", ") }));
    }
    if (resultConflicts.length > 0) {
      parts.push(t(scope.locale, "wishesConflictSkipped", { count: String(resultConflicts.length) }));
    }
    if (failure) {
      parts.push(failure instanceof ApiError || failure instanceof Error ? failure.message : t(scope.locale, "warnings"));
    }
    setNotice(parts.length > 0 ? parts.join(" ") : t(scope.locale, "autosaved"));
  }

  function remember(writes: WishesCellWrite[], updatedAt: Map<string, string | null>) {
    for (const write of writes) {
      const key = cellKey(write.teamMemberId, write.date);
      if (!updatedAt.has(key)) {
        continue;
      }
      latestRef.current.set(key, {
        teamMemberId: write.teamMemberId,
        date: write.date,
        status: write.status,
        comment: write.comment,
        updatedAt: updatedAt.get(key) ?? null
      });
    }
  }

  async function runEdit(item: PendingEdit, generation: number) {
    const scope = scopeRef.current;
    if (scope.readOnly || scope.periodId === "" || scope.shiftGroupId === "") {
      return;
    }
    const before = overlayBefore(item.before, latestRef.current);
    const result = await applyWishesWrites({
      periodId: scope.periodId,
      shiftGroupId: scope.shiftGroupId,
      writes: item.writes,
      precondition: false
    });
    if (generationRef.current !== generation) {
      return;
    }
    const entry = undoEntryForLanded(before, item.writes, result.conflicts, result.updatedAt);
    if (entry) {
      commitStacks(recordWishesEdit(stacksRef.current, entry));
      remember(item.writes, result.updatedAt);
    }
    describe(result.conflicts, item.unresolved, result.error);
    await refresh();
  }

  async function runHistory(direction: "undo" | "redo", generation: number) {
    const scope = scopeRef.current;
    if (scope.readOnly || scope.periodId === "" || scope.shiftGroupId === "") {
      return;
    }
    const popped = direction === "undo" ? popWishesUndo(stacksRef.current) : popWishesRedo(stacksRef.current);
    if (!popped) {
      return;
    }
    const writes = direction === "undo" ? popped.entry.undo : popped.entry.redo;
    const result = await applyWishesWrites({
      periodId: scope.periodId,
      shiftGroupId: scope.shiftGroupId,
      writes,
      precondition: true
    });
    if (generationRef.current !== generation) {
      return;
    }
    const counterpart = direction === "undo" ? popped.entry.redo : popped.entry.undo;
    const landed = writes.filter((row) => result.updatedAt.has(cellKey(row.teamMemberId, row.date)));
    if (landed.length === 0) {
      if (!result.error) {
        commitStacks(
          direction === "undo"
            ? { undo: popped.stacks.undo, redo: popped.stacks.redo.slice(0, -1) }
            : { undo: popped.stacks.undo.slice(0, -1), redo: popped.stacks.redo }
        );
      }
      describe(result.conflicts, [], result.error);
      await refresh();
      return;
    }
    const landedKeys = new Set(landed.map((row) => cellKey(row.teamMemberId, row.date)));
    const blocked = new Set(result.conflicts.map((row) => cellKey(row.teamMemberId, row.date)));
    const pending = writes.filter((row) => {
      const key = cellKey(row.teamMemberId, row.date);
      return !landedKeys.has(key) && !blocked.has(key);
    });
    const pendingCounterpart = counterpart.filter((row) => {
      const key = cellKey(row.teamMemberId, row.date);
      return !landedKeys.has(key) && !blocked.has(key);
    });
    const retry: WishesUndoEntry | null =
      pending.length > 0
        ? direction === "undo"
          ? { undo: pending, redo: pendingCounterpart }
          : { undo: pendingCounterpart, redo: pending }
        : null;
    const landedEntry: WishesUndoEntry =
      direction === "undo"
        ? {
            undo: landed,
            redo: stampCounterpart(
              counterpart.filter((row) => landedKeys.has(cellKey(row.teamMemberId, row.date))),
              result.updatedAt,
              result.conflicts
            )
          }
        : {
            undo: stampCounterpart(
              counterpart.filter((row) => landedKeys.has(cellKey(row.teamMemberId, row.date))),
              result.updatedAt,
              result.conflicts
            ),
            redo: landed
          };
    if (direction === "undo") {
      const older = retargetExpected(retry ? [...popped.stacks.undo, retry] : popped.stacks.undo, result.updatedAt);
      commitStacks({ undo: older, redo: [...popped.stacks.redo.slice(0, -1), landedEntry] });
    } else {
      const older = retargetExpected(retry ? [...popped.stacks.redo, retry] : popped.stacks.redo, result.updatedAt);
      commitStacks({ undo: [...popped.stacks.undo.slice(0, -1), landedEntry], redo: older });
    }
    remember(landed, result.updatedAt);
    describe(result.conflicts, [], result.error);
    await refresh();
  }

  const processRef = useRef<(item: Pending, generation: number) => Promise<void>>(async () => {});
  processRef.current = async (item, generation) => {
    if (item.kind === "edit") {
      await runEdit(item, generation);
      return;
    }
    await runHistory(item.kind, generation);
  };

  function kick() {
    if (runningRef.current) {
      return;
    }
    runningRef.current = true;
    void (async () => {
      try {
        while (queueRef.current.length > 0) {
          const item = queueRef.current.shift();
          if (!item) {
            break;
          }
          const generation = generationRef.current;
          await processRef.current(item, generation);
        }
      } finally {
        runningRef.current = false;
        if (queueRef.current.length > 0) {
          kick();
        }
      }
    })();
  }

  function enqueue(item: Pending) {
    queueRef.current.push(item);
    kick();
  }

  const value: WishesHistory = {
    notice,
    applyEdit: (before, writes, unresolved = []) => {
      const scope = scopeRef.current;
      if (scope.readOnly || writes.length === 0 || scope.periodId === "" || scope.shiftGroupId === "") {
        if (unresolved.length > 0) {
          setNotice(t(scope.locale, "wishesPasteUnresolved", { names: unresolved.join(", ") }));
        }
        return Promise.resolve();
      }
      enqueue({ kind: "edit", before, writes, unresolved });
      return Promise.resolve();
    },
    undo: () => {
      enqueue({ kind: "undo" });
      return Promise.resolve();
    },
    redo: () => {
      enqueue({ kind: "redo" });
      return Promise.resolve();
    },
    refresh
  };

  return <WishesHistoryContext.Provider value={value}>{children}</WishesHistoryContext.Provider>;
}

export function useWishesHistory(): WishesHistory {
  const value = useContext(WishesHistoryContext);
  if (!value) {
    throw new Error("WishesHistoryProvider is missing");
  }
  return value;
}
