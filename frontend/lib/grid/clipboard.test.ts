import { describe, expect, it } from "vitest";
import { parseClipboard, resolvePasteCell, toInternalClipboard, toTsv } from "@/lib/grid/clipboard";

const members = [
  { id: 1, first_name: "Ada", last_name: "Lovelace", email: "ada@example.com", nickname: "Addy" },
  { id: 2, first_name: "Bea", last_name: "Lovelace", email: "bea@example.com", nickname: null }
];

describe("grid clipboard", () => {
  it("round-trips tsv labels and internal ids", () => {
    expect(toTsv([["Addy", null], ["", "Bea"]])).toBe("Addy\t\n\tBea");
    const encoded = toInternalClipboard([[{ memberId: 1 }], [{ memberId: null }]]);
    expect(parseClipboard(encoded)).toEqual({ format: "json", rows: [[{ memberId: 1 }], [{ memberId: null }]] });
  });

  it("resolves a display name or email and refuses an unknown name", () => {
    expect(resolvePasteCell("Addy", members)).toEqual({ kind: "member", memberId: 1 });
    expect(resolvePasteCell("bea@example.com", members)).toEqual({ kind: "member", memberId: 2 });
    expect(resolvePasteCell("", members)).toEqual({ kind: "clear" });
    expect(resolvePasteCell("Not A Person", members)).toEqual({ kind: "unresolved", name: "Not A Person" });
  });

  it("does not guess when two people share a display name", () => {
    const twins = [
      { id: 3, first_name: "Ann", last_name: "Ng", email: "a@example.com", nickname: null },
      { id: 4, first_name: "Amy", last_name: "Ng", email: "b@example.com", nickname: null }
    ];
    expect(resolvePasteCell("Ng", twins)).toEqual({ kind: "unresolved", name: "Ng" });
  });

  it("parses a tsv rectangle", () => {
    expect(parseClipboard("Addy\tBea\n\tNg")).toEqual({
      format: "tsv",
      rows: [
        ["Addy", "Bea"],
        ["", "Ng"]
      ]
    });
  });
});
