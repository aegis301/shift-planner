import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const source = readFileSync(path.join(process.cwd(), "app/globals.css"), "utf8");
const comfortable = source.match(/:root,\s*\[data-density="comfortable"\]\s*\{[^}]+\}/)?.[0];
const compact = source.match(/\[data-density="compact"\]\s*\{[^}]+\}/)?.[0];

function applyDensity(density: "comfortable" | "compact") {
  document.head.querySelectorAll("style[data-density-test]").forEach((node) => node.remove());
  const style = document.createElement("style");
  style.dataset.densityTest = "true";
  style.textContent = `${comfortable ?? ""}\n${compact ?? ""}`;
  document.head.appendChild(style);
  document.documentElement.dataset.density = density;
}

describe("data-density", () => {
  it("switches cell spacing tokens", () => {
    expect(comfortable).toBeTruthy();
    expect(compact).toBeTruthy();
    applyDensity("compact");
    const compactStyle = getComputedStyle(document.documentElement);
    expect(compactStyle.getPropertyValue("--space-cell-x").trim()).toBe("0.25rem");
    expect(compactStyle.getPropertyValue("--space-cell-y").trim()).toBe("0.125rem");
    expect(compactStyle.getPropertyValue("--font-size-cell").trim()).toBe("0.6875rem");
    applyDensity("comfortable");
    const comfortableStyle = getComputedStyle(document.documentElement);
    expect(comfortableStyle.getPropertyValue("--space-cell-x").trim()).toBe("0.5rem");
    expect(comfortableStyle.getPropertyValue("--space-cell-y").trim()).toBe("0.375rem");
    expect(comfortableStyle.getPropertyValue("--font-size-cell").trim()).toBe("0.75rem");
  });
});
