import { describe, expect, it } from "vitest";
import {
  SPLIT_DIVIDER_SIZE,
  SPLIT_LARGE_STEP,
  SPLIT_STEP,
  applySplitKeyAction,
  clampPaneSize,
  defaultSplitLayout,
  dividerTargetIndex,
  fitSplitLayout,
  moveDivider,
  paneSizeLimit,
  parseStoredSplitLayout,
  serializeSplitLayout,
  setPaneSize,
  splitKeyAction,
  splitStorageKey,
  togglePaneCollapsed,
  type SplitLayout,
  type SplitPaneSpec
} from "@/lib/splitPane";

const panes: SplitPaneSpec[] = [
  { id: "grid", minSize: 480, flex: true },
  { id: "workload", minSize: 260, maxSize: 600, defaultSize: 340, collapsible: true, collapsedBelow: 1280 },
  { id: "inspector", minSize: 320, maxSize: 640, defaultSize: 400, collapsible: true }
];

const dividers = 2 * SPLIT_DIVIDER_SIZE;
const roomy = 2000;

function flexWidth(layout: SplitLayout, container: number): number {
  const fixed = panes
    .filter((pane) => !pane.flex)
    .reduce((sum, pane) => sum + (layout.collapsed[pane.id] ? 0 : layout.sizes[pane.id] ?? 0), 0);
  return container - dividers - fixed;
}

describe("split pane size math", () => {
  it("uses default sizes and collapses panes below their viewport threshold", () => {
    expect(defaultSplitLayout(panes, 1440)).toEqual({
      sizes: { workload: 340, inspector: 400 },
      collapsed: { workload: false, inspector: false }
    });
    expect(defaultSplitLayout(panes, 1200).collapsed).toEqual({ workload: true, inspector: false });
  });

  it("clamps sizes to the pane minimum and maximum", () => {
    expect(clampPaneSize(panes[1], 100)).toBe(260);
    expect(clampPaneSize(panes[1], 900)).toBe(600);
    expect(clampPaneSize(panes[1], 420)).toBe(420);
    const layout = defaultSplitLayout(panes, 1440);
    expect(setPaneSize(panes, layout, "workload", 50, roomy).sizes.workload).toBe(260);
    expect(setPaneSize(panes, layout, "workload", 5000, roomy).sizes.workload).toBe(600);
  });

  it("targets the fixed pane on the side away from the flex pane", () => {
    expect(dividerTargetIndex(panes, 0)).toBe(1);
    expect(dividerTargetIndex(panes, 1)).toBe(2);
    const leftFixed: SplitPaneSpec[] = [{ id: "side", minSize: 100, maxSize: 400, defaultSize: 200 }, { id: "main", minSize: 200, flex: true }];
    expect(dividerTargetIndex(leftFixed, 0)).toBe(0);
    const layout = defaultSplitLayout(leftFixed, 1440);
    expect(moveDivider(leftFixed, layout, 0, 40, roomy).sizes.side).toBe(240);
  });

  it("grows the pane right of a divider when the divider moves left", () => {
    const layout = defaultSplitLayout(panes, 1440);
    expect(moveDivider(panes, layout, 0, -100, roomy).sizes.workload).toBe(440);
    expect(moveDivider(panes, layout, 1, 100, roomy).sizes.inspector).toBe(320);
  });

  it("never lets the flex pane drop below its minimum", () => {
    const container = 480 + dividers + 340 + 400 + 30;
    const layout = defaultSplitLayout(panes, 1440);
    const grown = moveDivider(panes, layout, 0, -500, container);
    expect(flexWidth(grown, container)).toBeGreaterThanOrEqual(480);
    expect(grown.sizes.workload).toBe(340 + 30 + 80);
    expect(grown.sizes.inspector).toBe(320);
    expect(paneSizeLimit(panes, layout, "workload", container)).toBe(450);
  });

  it("maps keys to steps, edges, and collapse", () => {
    expect(splitKeyAction("ArrowLeft", false, "horizontal")).toEqual({ kind: "move", delta: -SPLIT_STEP });
    expect(splitKeyAction("ArrowRight", true, "horizontal")).toEqual({ kind: "move", delta: SPLIT_LARGE_STEP });
    expect(splitKeyAction("ArrowDown", false, "vertical")).toEqual({ kind: "move", delta: SPLIT_STEP });
    expect(splitKeyAction("ArrowDown", false, "horizontal")).toBeNull();
    expect(splitKeyAction("Home", false, "horizontal")).toEqual({ kind: "min" });
    expect(splitKeyAction("End", false, "horizontal")).toEqual({ kind: "max" });
    expect(splitKeyAction("Enter", false, "horizontal")).toEqual({ kind: "toggle" });
  });

  it("applies keyboard steps and edge jumps to the divider's pane", () => {
    const layout = defaultSplitLayout(panes, 1440);
    expect(applySplitKeyAction(panes, layout, 0, { kind: "move", delta: -SPLIT_STEP }, roomy).sizes.workload).toBe(356);
    expect(applySplitKeyAction(panes, layout, 0, { kind: "move", delta: SPLIT_LARGE_STEP }, roomy).sizes.workload).toBe(276);
    expect(applySplitKeyAction(panes, layout, 0, { kind: "min" }, roomy).sizes.workload).toBe(260);
    expect(applySplitKeyAction(panes, layout, 0, { kind: "max" }, roomy).sizes.workload).toBe(600);
    expect(applySplitKeyAction(panes, layout, 1, { kind: "toggle" }, roomy).collapsed.inspector).toBe(true);
  });

  it("collapses and restores a pane with its previous size", () => {
    const layout = setPaneSize(panes, defaultSplitLayout(panes, 1440), "inspector", 500, roomy);
    const collapsed = togglePaneCollapsed(panes, layout, "inspector");
    expect(collapsed.collapsed.inspector).toBe(true);
    const restored = togglePaneCollapsed(panes, collapsed, "inspector");
    expect(restored).toEqual(layout);
    expect(togglePaneCollapsed(panes, layout, "grid")).toBe(layout);
  });

  it("opens a collapsed pane when its divider is dragged outward", () => {
    const collapsed = togglePaneCollapsed(panes, defaultSplitLayout(panes, 1440), "workload");
    expect(moveDivider(panes, collapsed, 0, 20, roomy)).toBe(collapsed);
    const opened = moveDivider(panes, collapsed, 0, -40, roomy);
    expect(opened.collapsed.workload).toBe(false);
    expect(opened.sizes.workload).toBe(300);
  });

  it("reapplies persisted sizes and clamps them", () => {
    const fallback = defaultSplitLayout(panes, 1440);
    const stored = serializeSplitLayout({ sizes: { workload: 9000, inspector: 10, grid: 50 }, collapsed: { workload: true, grid: true } });
    expect(parseStoredSplitLayout(stored, panes, fallback)).toEqual({
      sizes: { workload: 600, inspector: 320 },
      collapsed: { workload: true, inspector: false }
    });
    expect(parseStoredSplitLayout("not json", panes, fallback)).toBe(fallback);
    expect(parseStoredSplitLayout(null, panes, fallback)).toBe(fallback);
    expect(splitStorageKey("planning-roster")).toBe("shift-planner-split:planning-roster");
  });

  it("shrinks and then collapses panes when the container gets smaller", () => {
    const layout = defaultSplitLayout(panes, 1440);
    const narrow = 480 + dividers + 340 + 400 - 50;
    const fitted = fitSplitLayout(panes, layout, narrow);
    expect(fitted.sizes).toEqual({ workload: 340, inspector: 350 });
    expect(flexWidth(fitted, narrow)).toBe(480);
    const tiny = fitSplitLayout(panes, layout, 480 + dividers + 320);
    expect(tiny.collapsed).toEqual({ workload: true, inspector: false });
    expect(flexWidth(tiny, 480 + dividers + 320)).toBeGreaterThanOrEqual(480);
    expect(fitSplitLayout(panes, layout, 0)).toBe(layout);
  });

  it("only clamps to the pane bounds before the container is measured", () => {
    const layout = defaultSplitLayout(panes, 1440);
    const grown = setPaneSize(panes, layout, "workload", 500, 0);
    expect(grown.sizes).toEqual({ workload: 500, inspector: 400 });
    expect(paneSizeLimit(panes, layout, "workload", 0)).toBe(600);
  });
});
