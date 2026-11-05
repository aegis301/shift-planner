export type SplitOrientation = "horizontal" | "vertical";

export type SplitPaneSpec = {
  id: string;
  minSize: number;
  maxSize?: number;
  defaultSize?: number;
  collapsible?: boolean;
  flex?: boolean;
  collapsedBelow?: number;
};

export type SplitLayout = {
  sizes: Record<string, number>;
  collapsed: Record<string, boolean>;
};

export type SplitKeyAction =
  | { kind: "move"; delta: number }
  | { kind: "min" }
  | { kind: "max" }
  | { kind: "toggle" };

export const SPLIT_STEP = 16;
export const SPLIT_LARGE_STEP = 64;
export const SPLIT_DIVIDER_SIZE = 6;
export const SPLIT_STORAGE_PREFIX = "shift-planner-split:";

export function splitStorageKey(layoutKey: string): string {
  return `${SPLIT_STORAGE_PREFIX}${layoutKey}`;
}

function fixedPanes(panes: SplitPaneSpec[]): SplitPaneSpec[] {
  return panes.filter((pane) => !pane.flex);
}

function flexPane(panes: SplitPaneSpec[]): SplitPaneSpec | undefined {
  return panes.find((pane) => pane.flex);
}

function paneById(panes: SplitPaneSpec[], id: string): SplitPaneSpec | undefined {
  return panes.find((pane) => pane.id === id);
}

export function paneMaxSize(pane: SplitPaneSpec): number {
  return pane.maxSize ?? Number.POSITIVE_INFINITY;
}

export function clampPaneSize(pane: SplitPaneSpec, size: number): number {
  return Math.min(paneMaxSize(pane), Math.max(pane.minSize, size));
}

export function dividersSize(panes: SplitPaneSpec[]): number {
  return Math.max(0, panes.length - 1) * SPLIT_DIVIDER_SIZE;
}

function visibleSize(layout: SplitLayout, pane: SplitPaneSpec): number {
  return layout.collapsed[pane.id] ? 0 : layout.sizes[pane.id] ?? pane.minSize;
}

export function defaultSplitLayout(panes: SplitPaneSpec[], viewportWidth: number): SplitLayout {
  const sizes: Record<string, number> = {};
  const collapsed: Record<string, boolean> = {};
  for (const pane of fixedPanes(panes)) {
    sizes[pane.id] = clampPaneSize(pane, pane.defaultSize ?? pane.minSize);
    collapsed[pane.id] = Boolean(pane.collapsible && pane.collapsedBelow != null && viewportWidth < pane.collapsedBelow);
  }
  return { sizes, collapsed };
}

export function parseStoredSplitLayout(raw: string | null, panes: SplitPaneSpec[], fallback: SplitLayout): SplitLayout {
  if (!raw) {
    return fallback;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return fallback;
  }
  if (!parsed || typeof parsed !== "object") {
    return fallback;
  }
  const stored = parsed as { sizes?: Record<string, unknown>; collapsed?: Record<string, unknown> };
  const sizes: Record<string, number> = { ...fallback.sizes };
  const collapsed: Record<string, boolean> = { ...fallback.collapsed };
  for (const pane of fixedPanes(panes)) {
    const size = stored.sizes?.[pane.id];
    if (typeof size === "number" && Number.isFinite(size)) {
      sizes[pane.id] = clampPaneSize(pane, size);
    }
    const isCollapsed = stored.collapsed?.[pane.id];
    if (typeof isCollapsed === "boolean" && pane.collapsible) {
      collapsed[pane.id] = isCollapsed;
    }
  }
  return { sizes, collapsed };
}

export function serializeSplitLayout(layout: SplitLayout): string {
  return JSON.stringify(layout);
}

export function dividerTargetIndex(panes: SplitPaneSpec[], dividerIndex: number): number {
  const flexIndex = panes.findIndex((pane) => pane.flex);
  return flexIndex !== -1 && flexIndex <= dividerIndex ? dividerIndex + 1 : dividerIndex;
}

function growthSign(panes: SplitPaneSpec[], dividerIndex: number): number {
  return dividerTargetIndex(panes, dividerIndex) > dividerIndex ? -1 : 1;
}

function freeSpace(panes: SplitPaneSpec[], layout: SplitLayout, containerSize: number): number {
  const used = fixedPanes(panes).reduce((sum, pane) => sum + visibleSize(layout, pane), 0);
  return containerSize - dividersSize(panes) - (flexPane(panes)?.minSize ?? 0) - used;
}

export function paneSizeLimit(panes: SplitPaneSpec[], layout: SplitLayout, paneId: string, containerSize: number): number {
  const pane = paneById(panes, paneId);
  if (!pane) {
    return 0;
  }
  if (containerSize <= 0) {
    return Number.isFinite(paneMaxSize(pane)) ? paneMaxSize(pane) : Math.max(pane.minSize, visibleSize(layout, pane));
  }
  const borrowable = fixedPanes(panes)
    .filter((other) => other.id !== paneId && !layout.collapsed[other.id])
    .reduce((sum, other) => sum + Math.max(0, visibleSize(layout, other) - other.minSize), 0);
  const limit = visibleSize(layout, pane) + Math.max(0, freeSpace(panes, layout, containerSize)) + borrowable;
  return Math.max(pane.minSize, Math.min(paneMaxSize(pane), limit));
}

export function setPaneSize(
  panes: SplitPaneSpec[],
  layout: SplitLayout,
  paneId: string,
  size: number,
  containerSize: number
): SplitLayout {
  const pane = paneById(panes, paneId);
  if (!pane || pane.flex) {
    return layout;
  }
  const opened: SplitLayout = {
    sizes: { ...layout.sizes, [paneId]: visibleSize(layout, pane) },
    collapsed: { ...layout.collapsed, [paneId]: false }
  };
  const target = Math.min(clampPaneSize(pane, size), paneSizeLimit(panes, opened, paneId, containerSize));
  const sizes: Record<string, number> = { ...opened.sizes, [paneId]: target };
  if (containerSize <= 0) {
    return { sizes, collapsed: opened.collapsed };
  }
  let overflow = -freeSpace(panes, { sizes, collapsed: opened.collapsed }, containerSize);
  const paneIndex = panes.indexOf(pane);
  const neighbours = fixedPanes(panes)
    .filter((other) => other.id !== paneId && !opened.collapsed[other.id])
    .sort((a, b) => Math.abs(panes.indexOf(a) - paneIndex) - Math.abs(panes.indexOf(b) - paneIndex));
  for (const other of neighbours) {
    if (overflow <= 0) {
      break;
    }
    const current = sizes[other.id] ?? other.minSize;
    const taken = Math.min(overflow, Math.max(0, current - other.minSize));
    sizes[other.id] = current - taken;
    overflow -= taken;
  }
  return { sizes, collapsed: opened.collapsed };
}

export function togglePaneCollapsed(panes: SplitPaneSpec[], layout: SplitLayout, paneId: string): SplitLayout {
  const pane = paneById(panes, paneId);
  if (!pane?.collapsible) {
    return layout;
  }
  return { sizes: layout.sizes, collapsed: { ...layout.collapsed, [paneId]: !layout.collapsed[paneId] } };
}

export function moveDivider(
  panes: SplitPaneSpec[],
  layout: SplitLayout,
  dividerIndex: number,
  delta: number,
  containerSize: number
): SplitLayout {
  const pane = panes[dividerTargetIndex(panes, dividerIndex)];
  if (!pane || pane.flex) {
    return layout;
  }
  const growth = growthSign(panes, dividerIndex) * delta;
  if (layout.collapsed[pane.id]) {
    return growth > 0 ? setPaneSize(panes, layout, pane.id, pane.minSize + growth, containerSize) : layout;
  }
  return setPaneSize(panes, layout, pane.id, visibleSize(layout, pane) + growth, containerSize);
}

export function splitKeyAction(key: string, shiftKey: boolean, orientation: SplitOrientation): SplitKeyAction | null {
  const step = shiftKey ? SPLIT_LARGE_STEP : SPLIT_STEP;
  const [backward, forward] = orientation === "horizontal" ? ["ArrowLeft", "ArrowRight"] : ["ArrowUp", "ArrowDown"];
  if (key === backward) {
    return { kind: "move", delta: -step };
  }
  if (key === forward) {
    return { kind: "move", delta: step };
  }
  if (key === "Home") {
    return { kind: "min" };
  }
  if (key === "End") {
    return { kind: "max" };
  }
  if (key === "Enter") {
    return { kind: "toggle" };
  }
  return null;
}

export function applySplitKeyAction(
  panes: SplitPaneSpec[],
  layout: SplitLayout,
  dividerIndex: number,
  action: SplitKeyAction,
  containerSize: number
): SplitLayout {
  const pane = panes[dividerTargetIndex(panes, dividerIndex)];
  if (!pane) {
    return layout;
  }
  if (action.kind === "move") {
    return moveDivider(panes, layout, dividerIndex, action.delta, containerSize);
  }
  if (action.kind === "toggle") {
    return togglePaneCollapsed(panes, layout, pane.id);
  }
  const size = action.kind === "min" ? pane.minSize : paneMaxSize(pane);
  return setPaneSize(panes, layout, pane.id, size, containerSize);
}

export function fitSplitLayout(panes: SplitPaneSpec[], layout: SplitLayout, containerSize: number): SplitLayout {
  if (containerSize <= 0) {
    return layout;
  }
  const sizes: Record<string, number> = { ...layout.sizes };
  const collapsed: Record<string, boolean> = { ...layout.collapsed };
  let overflow = -freeSpace(panes, { sizes, collapsed }, containerSize);
  for (const pane of [...fixedPanes(panes)].reverse()) {
    if (overflow <= 0) {
      break;
    }
    if (collapsed[pane.id]) {
      continue;
    }
    const current = sizes[pane.id] ?? pane.minSize;
    const taken = Math.min(overflow, Math.max(0, current - pane.minSize));
    sizes[pane.id] = current - taken;
    overflow -= taken;
  }
  for (const pane of fixedPanes(panes)) {
    if (overflow <= 0) {
      break;
    }
    if (pane.collapsible && !collapsed[pane.id]) {
      collapsed[pane.id] = true;
      overflow -= sizes[pane.id] ?? pane.minSize;
    }
  }
  return { sizes, collapsed };
}
