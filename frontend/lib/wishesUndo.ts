export type WishesCellState = {
  teamMemberId: number;
  date: string;
  status: string | null;
  comment: string | null;
  updatedAt: string | null;
};

export type WishesCellWrite = {
  teamMemberId: number;
  date: string;
  status: string | null;
  comment: string | null;
  expectedUpdatedAt: string | null;
};

export type WishesUndoEntry = {
  undo: WishesCellWrite[];
  redo: WishesCellWrite[];
};

export type WishesUndoStacks = {
  undo: WishesUndoEntry[];
  redo: WishesUndoEntry[];
};

export function emptyWishesUndo(): WishesUndoStacks {
  return { undo: [], redo: [] };
}

export function recordWishesEdit(stacks: WishesUndoStacks, entry: WishesUndoEntry): WishesUndoStacks {
  return { undo: [...stacks.undo, entry], redo: [] };
}

export function popWishesUndo(stacks: WishesUndoStacks): { stacks: WishesUndoStacks; entry: WishesUndoEntry } | null {
  const entry = stacks.undo.at(-1);
  if (!entry) {
    return null;
  }
  return { entry, stacks: { undo: stacks.undo.slice(0, -1), redo: [...stacks.redo, entry] } };
}

export function popWishesRedo(stacks: WishesUndoStacks): { stacks: WishesUndoStacks; entry: WishesUndoEntry } | null {
  const entry = stacks.redo.at(-1);
  if (!entry) {
    return null;
  }
  return { entry, stacks: { undo: [...stacks.undo, entry], redo: stacks.redo.slice(0, -1) } };
}

export function writesRestoring(before: WishesCellState[], currentUpdatedAt: Map<string, string | null>): WishesCellWrite[] {
  return before.map((cell) => ({
    teamMemberId: cell.teamMemberId,
    date: cell.date,
    status: cell.status,
    comment: cell.comment,
    expectedUpdatedAt: currentUpdatedAt.get(cellKey(cell.teamMemberId, cell.date)) ?? null
  }));
}

export function cellKey(teamMemberId: number, date: string): string {
  return `${teamMemberId}:${date}`;
}

export function skipConflicts<T extends { teamMemberId: number; date: string }>(
  writes: T[],
  conflicts: { teamMemberId: number; date: string }[]
): { kept: T[]; skipped: T[] } {
  const blocked = new Set(conflicts.map((row) => cellKey(row.teamMemberId, row.date)));
  const kept: T[] = [];
  const skipped: T[] = [];
  for (const write of writes) {
    if (blocked.has(cellKey(write.teamMemberId, write.date))) {
      skipped.push(write);
    } else {
      kept.push(write);
    }
  }
  return { kept, skipped };
}

export function parseStatusTsv(text: string): string[][] {
  let body = text.replace(/^\uFEFF/, "");
  if (body.endsWith("\r\n")) {
    body = body.slice(0, -2);
  } else if (body.endsWith("\n")) {
    body = body.slice(0, -1);
  }
  if (body === "") {
    return [[""]];
  }
  return body.split(/\r?\n/).map((line) => line.split("\t"));
}

export function stampCounterpart(
  counterpart: WishesCellWrite[],
  updatedAt: Map<string, string | null>,
  conflicts: { teamMemberId: number; date: string }[]
): WishesCellWrite[] {
  const blocked = new Set(conflicts.map((row) => cellKey(row.teamMemberId, row.date)));
  return counterpart
    .filter((row) => !blocked.has(cellKey(row.teamMemberId, row.date)))
    .map((row) => ({
      ...row,
      expectedUpdatedAt: updatedAt.get(cellKey(row.teamMemberId, row.date)) ?? null
    }));
}

export type WishesPasteCell = {
  status: string | null;
  comment: string | null;
  raw: boolean;
};

export function toWishesInternal(rows: { status: string | null; comment: string | null }[][]): string {
  return JSON.stringify({ kind: "wishes-cells", rows });
}

export function parseWishesPaste(text: string): WishesPasteCell[][] | null {
  const trimmed = text.trim();
  if (trimmed.startsWith("{")) {
    try {
      const parsed = JSON.parse(trimmed) as {
        kind?: string;
        rows?: { status?: string | null; comment?: string | null }[][];
      };
      if (parsed.kind !== "wishes-cells" || !Array.isArray(parsed.rows)) {
        return null;
      }
      return parsed.rows.map((row) =>
        (Array.isArray(row) ? row : []).map((cell) => ({
          status: cell?.status ?? null,
          comment: cell?.comment ?? null,
          raw: false
        }))
      );
    } catch {
      return null;
    }
  }
  return parseStatusTsv(text).map((row) => row.map((token) => ({ status: token, comment: null, raw: true })));
}

export function resolveStatusToken(
  token: string,
  definitions: { code: string; label: string }[]
): { status: string } | { unresolved: string } | { clear: true } {
  const name = token.trim();
  if (!name) {
    return { clear: true };
  }
  const needle = name.toLowerCase();
  const byCode = definitions.filter((row) => row.code.toLowerCase() === needle);
  if (byCode.length === 1) {
    return { status: byCode[0].code };
  }
  const byLabel = definitions.filter((row) => row.label.toLowerCase() === needle);
  if (byLabel.length === 1) {
    return { status: byLabel[0].code };
  }
  return { unresolved: name };
}
