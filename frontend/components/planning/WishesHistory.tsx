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
  emptyWishesUndo,
  popWishesRedo,
  popWishesUndo,
  recordWishesEdit,
  skipConflicts,
  stampCounterpart,
  writesRestoring,
  cellKey,
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
  const [stacks, setStacks] = useState<WishesUndoStacks>(emptyWishesUndo);
  const [notice, setNotice] = useState("");
  const stacksRef = useRef(stacks);
  const busy = useRef(false);
  stacksRef.current = stacks;

  useEffect(() => {
    setStacks(emptyWishesUndo());
    setNotice("");
  }, [periodId, shiftGroupId]);

  async function refresh() {
    if (organizationId == null || periodId === "" || shiftGroupId === "") {
      return;
    }
    await invalidateQueryKeys(queryClient, wishesEditKeys({
      organizationId,
      periodId,
      shiftGroupId,
      teamMemberPortal: false
    }));
  }

  function describe(resultConflicts: { teamMemberId: number; date: string }[], unresolved: string[] = []) {
    const parts: string[] = [];
    if (unresolved.length > 0) {
      parts.push(t(locale, "wishesPasteUnresolved", { names: unresolved.join(", ") }));
    }
    if (resultConflicts.length > 0) {
      parts.push(t(locale, "wishesConflictSkipped", { count: String(resultConflicts.length) }));
    }
    setNotice(parts.length > 0 ? parts.join(" ") : t(locale, "autosaved"));
  }

  async function applyEdit(before: WishesCellState[], writes: WishesCellWrite[], unresolved: string[] = []) {
    if (readOnly || writes.length === 0 || periodId === "" || shiftGroupId === "" || busy.current) {
      if (unresolved.length > 0) {
        setNotice(t(locale, "wishesPasteUnresolved", { names: unresolved.join(", ") }));
      }
      return;
    }
    busy.current = true;
    try {
      const result = await applyWishesWrites({ periodId, shiftGroupId, writes, precondition: false });
      const applied = skipConflicts(writes, result.conflicts).kept;
      const appliedKeys = new Set(applied.map((row) => cellKey(row.teamMemberId, row.date)));
      const appliedBefore = before.filter((row) => appliedKeys.has(cellKey(row.teamMemberId, row.date)));
      if (applied.length > 0) {
        setStacks((current) =>
          recordWishesEdit(current, {
            undo: writesRestoring(appliedBefore, result.updatedAt),
            redo: applied.map((row) => ({
              ...row,
              expectedUpdatedAt: result.updatedAt.get(cellKey(row.teamMemberId, row.date)) ?? null
            }))
          })
        );
      }
      describe(result.conflicts, unresolved);
      await refresh();
    } catch (error) {
      setNotice(error instanceof ApiError || error instanceof Error ? error.message : t(locale, "warnings"));
    } finally {
      busy.current = false;
    }
  }

  async function runHistory(direction: "undo" | "redo") {
    if (readOnly || periodId === "" || shiftGroupId === "" || busy.current) {
      return;
    }
    const popped = direction === "undo" ? popWishesUndo(stacksRef.current) : popWishesRedo(stacksRef.current);
    if (!popped) {
      return;
    }
    busy.current = true;
    try {
      const writes = direction === "undo" ? popped.entry.undo : popped.entry.redo;
      const result = await applyWishesWrites({ periodId, shiftGroupId, writes, precondition: true });
      const counterpart = direction === "undo" ? popped.entry.redo : popped.entry.undo;
      const nextCounterpart = stampCounterpart(counterpart, result.updatedAt, result.conflicts);
      const nextApplied = skipConflicts(writes, result.conflicts).kept;
      const nextEntry: WishesUndoEntry =
        direction === "undo"
          ? { undo: nextApplied, redo: nextCounterpart }
          : { undo: nextCounterpart, redo: nextApplied };
      if (nextEntry.undo.length === 0 && nextEntry.redo.length === 0) {
        setStacks(
          direction === "undo"
            ? { undo: popped.stacks.undo, redo: popped.stacks.redo.slice(0, -1) }
            : { undo: popped.stacks.undo.slice(0, -1), redo: popped.stacks.redo }
        );
      } else {
        setStacks(
          direction === "undo"
            ? { undo: popped.stacks.undo, redo: [...popped.stacks.redo.slice(0, -1), nextEntry] }
            : { undo: [...popped.stacks.undo.slice(0, -1), nextEntry], redo: popped.stacks.redo }
        );
      }
      describe(result.conflicts);
      await refresh();
    } catch (error) {
      setNotice(error instanceof ApiError || error instanceof Error ? error.message : t(locale, "warnings"));
    } finally {
      busy.current = false;
    }
  }

  const value: WishesHistory = {
    notice,
    applyEdit: (before, writes, unresolved) => applyEdit(before, writes, unresolved ?? []),
    undo: () => runHistory("undo"),
    redo: () => runHistory("redo"),
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
