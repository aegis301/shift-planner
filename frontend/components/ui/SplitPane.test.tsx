import { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { SplitPane } from "@/components/ui/SplitPane";
import { splitStorageKey } from "@/lib/splitPane";

beforeAll(() => {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  window.ResizeObserver = ResizeObserverStub;
});

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

function Harness() {
  const [open, setOpen] = useState(true);
  return (
    <SplitPane
      layoutKey="test"
      panes={[
        { id: "grid", minSize: 200, flex: true, content: <p>Grid</p> },
        { id: "side", minSize: 100, maxSize: 300, defaultSize: 150, collapsible: true, resizeLabel: "Resize side", content: <p>Side</p> },
        {
          id: "inspector",
          minSize: 100,
          maxSize: 300,
          defaultSize: 200,
          collapsible: true,
          collapsed: !open,
          onCollapsedChange: (collapsed) => setOpen(!collapsed),
          resizeLabel: "Resize inspector",
          content: <p>Inspector</p>
        }
      ]}
    />
  );
}

describe("SplitPane", () => {
  it("renders separators with value attributes", () => {
    render(<Harness />);
    const separator = screen.getByRole("separator", { name: "Resize side" });
    expect(separator.getAttribute("aria-orientation")).toBe("vertical");
    expect(separator.getAttribute("aria-valuenow")).toBe("150");
    expect(separator.getAttribute("aria-valuemin")).toBe("0");
    expect(separator.getAttribute("tabindex")).toBe("0");
  });

  it("moves a divider from the keyboard and persists the size", () => {
    render(<Harness />);
    const separator = screen.getByRole("separator", { name: "Resize side" });
    fireEvent.keyDown(separator, { key: "ArrowLeft" });
    expect(separator.getAttribute("aria-valuenow")).toBe("166");
    fireEvent.keyDown(separator, { key: "Home" });
    expect(separator.getAttribute("aria-valuenow")).toBe("100");
    const stored = JSON.parse(window.localStorage.getItem(splitStorageKey("test")) ?? "{}") as { sizes: Record<string, number> };
    expect(stored.sizes.side).toBe(100);
  });

  it("collapses a controlled pane with Enter and restores it on double-click", () => {
    render(<Harness />);
    const separator = screen.getByRole("separator", { name: "Resize inspector" });
    fireEvent.keyDown(separator, { key: "Enter" });
    expect(screen.getByText("Inspector").closest("[data-split-pane]")?.hasAttribute("hidden")).toBe(true);
    expect(separator.getAttribute("aria-valuenow")).toBe("0");
    fireEvent.doubleClick(separator);
    expect(screen.getByText("Inspector").closest("[data-split-pane]")?.hasAttribute("hidden")).toBe(false);
  });

  it("reapplies a stored size after remount", () => {
    window.localStorage.setItem(splitStorageKey("test"), JSON.stringify({ sizes: { side: 260 }, collapsed: {} }));
    render(<Harness />);
    expect(screen.getByRole("separator", { name: "Resize side" }).getAttribute("aria-valuenow")).toBe("260");
  });
});
