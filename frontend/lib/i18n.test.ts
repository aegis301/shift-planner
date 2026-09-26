import { describe, expect, it } from "vitest";
import { dictionaries, t } from "@/lib/i18n";

function sortedKeys(record: object): string[] {
  return Object.keys(record).sort();
}

describe("t", () => {
  it("replaces every named placeholder", () => {
    expect(t("de", "apiRequestFailed", { status: "404" })).toBe(
      "Die Anfrage ist fehlgeschlagen (HTTP 404)."
    );
    expect(t("en", "matrixProgressDays", { filled: "3", total: "31" })).toBe(
      "3 / 31 days with status"
    );
    expect(t("de", "matrixProgressIntents", { wish: "2", noGo: "1" })).toBe(
      "2 Wünsche · 1 No-Go"
    );
  });

  it("leaves placeholders that were not given", () => {
    expect(t("en", "apiRequestFailed", { other: "x" })).toBe("The request failed (HTTP {{status}}).");
    expect(t("de", "matrixProgressDays")).toBe("{{filled}} / {{total}} Tage mit Status");
  });
});

describe("dictionaries", () => {
  it("gives German and English the same keys", () => {
    expect(sortedKeys(dictionaries.de)).toEqual(sortedKeys(dictionaries.en));
    expect(sortedKeys(dictionaries.de).length).toBeGreaterThan(0);
  });
});
