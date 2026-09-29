import { describe, expect, it } from "vitest";
import {
  emptyWishesUndo,
  parseStatusTsv,
  parseWishesPaste,
  popWishesRedo,
  popWishesUndo,
  recordWishesEdit,
  resolveStatusToken,
  skipConflicts,
  stampCounterpart,
  toWishesInternal,
  writesRestoring
} from "@/lib/wishesUndo";

const definitions = [
  { code: "urlaub", label: "Urlaub" },
  { code: "frei", label: "Frei" }
];

describe("wishes undo", () => {
  it("restores the previous status and skips cells the server marks as conflicts", () => {
    const before = [
      { teamMemberId: 1, date: "2026-10-01", status: null, comment: null, updatedAt: null },
      { teamMemberId: 1, date: "2026-10-02", status: "frei", comment: "note", updatedAt: "t0" }
    ];
    const writes = writesRestoring(
      before,
      new Map([
        ["1:2026-10-01", "t1"],
        ["1:2026-10-02", "t2"]
      ])
    );
    expect(writes[0]).toMatchObject({ status: null, expectedUpdatedAt: "t1" });
    expect(writes[1]).toMatchObject({ status: "frei", comment: "note", expectedUpdatedAt: "t2" });
    const split = skipConflicts(writes, [{ teamMemberId: 1, date: "2026-10-02" }]);
    expect(split.skipped.map((row) => row.date)).toEqual(["2026-10-02"]);
    expect(split.kept.map((row) => row.date)).toEqual(["2026-10-01"]);
  });

  it("keeps two undos redoable", () => {
    const first = recordWishesEdit(emptyWishesUndo(), {
      undo: [{ teamMemberId: 1, date: "2026-10-01", status: null, comment: null, expectedUpdatedAt: "a" }],
      redo: [{ teamMemberId: 1, date: "2026-10-01", status: "urlaub", comment: null, expectedUpdatedAt: null }]
    });
    const second = recordWishesEdit(first, {
      undo: [{ teamMemberId: 1, date: "2026-10-02", status: "frei", comment: null, expectedUpdatedAt: "b" }],
      redo: [{ teamMemberId: 1, date: "2026-10-02", status: "lehre", comment: null, expectedUpdatedAt: "c" }]
    });
    const undone = popWishesUndo(second);
    expect(undone?.stacks.undo).toHaveLength(1);
    expect(undone?.stacks.redo).toHaveLength(1);
    const undoneAgain = popWishesUndo(undone!.stacks);
    expect(undoneAgain?.stacks.redo).toHaveLength(2);
    const redone = popWishesRedo(undoneAgain!.stacks);
    expect(redone?.entry.redo[0]?.status).toBe("urlaub");
    expect(redone?.stacks.redo).toHaveLength(1);
  });

  it("parses status codes and labels without shifting a blank first cell", () => {
    expect(parseStatusTsv("\turlaub\nfrei\t")).toEqual([
      ["", "urlaub"],
      ["frei", ""]
    ]);
    expect(resolveStatusToken("Urlaub", definitions)).toEqual({ status: "urlaub" });
    expect(resolveStatusToken("frei", definitions)).toEqual({ status: "frei" });
    expect(resolveStatusToken("", definitions)).toEqual({ clear: true });
    expect(resolveStatusToken("nope", definitions)).toEqual({ unresolved: "nope" });
  });

  it("stamps the inverse with the timestamp from the write that just landed", () => {
    const updatedAt = new Map<string, string | null>([
      ["1:2026-10-01", "t2"],
      ["1:2026-10-02", null]
    ]);
    const stamped = stampCounterpart(
      [
        { teamMemberId: 1, date: "2026-10-01", status: "urlaub", comment: null, expectedUpdatedAt: "t0" },
        { teamMemberId: 1, date: "2026-10-02", status: null, comment: null, expectedUpdatedAt: "t1" },
        { teamMemberId: 1, date: "2026-10-03", status: "frei", comment: null, expectedUpdatedAt: "t9" }
      ],
      updatedAt,
      [{ teamMemberId: 1, date: "2026-10-03" }]
    );
    expect(stamped).toEqual([
      { teamMemberId: 1, date: "2026-10-01", status: "urlaub", comment: null, expectedUpdatedAt: "t2" },
      { teamMemberId: 1, date: "2026-10-02", status: null, comment: null, expectedUpdatedAt: null }
    ]);
    const internal = toWishesInternal([[{ status: "frei", comment: "x" }]]);
    expect(parseWishesPaste(internal)).toEqual([[{ status: "frei", comment: "x", raw: false }]]);
  });
});
