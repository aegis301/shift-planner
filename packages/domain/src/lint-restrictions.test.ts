import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function lint(source: string): number {
  const dir = mkdtempSync(path.join(packageRoot, "src", "lint-probe-"));
  const file = path.join(dir, "probe.ts");
  writeFileSync(file, source);
  try {
    execFileSync("npx", ["eslint", file], { cwd: packageRoot, stdio: "pipe" });
    return 0;
  } catch (error) {
    const status = (error as { status?: number }).status;
    return status ?? 1;
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

describe("domain lint", () => {
  it("rejects react, next, react-native, and window", () => {
    expect(lint('import "react";\n')).toBe(1);
    expect(lint('import "next";\n')).toBe(1);
    expect(lint('import "react-native";\n')).toBe(1);
    expect(lint("export const origin = window.location;\n")).toBe(1);
  });
});
