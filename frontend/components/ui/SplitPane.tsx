"use client";

import {
  forwardRef,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode
} from "react";
import { cn } from "@/components/ui/cn";
import {
  SPLIT_DIVIDER_SIZE,
  applySplitKeyAction,
  defaultSplitLayout,
  dividerTargetIndex,
  fitSplitLayout,
  moveDivider,
  paneSizeLimit,
  parseStoredSplitLayout,
  serializeSplitLayout,
  splitKeyAction,
  splitStorageKey,
  togglePaneCollapsed,
  type SplitLayout,
  type SplitOrientation,
  type SplitPaneSpec
} from "@/lib/splitPane";

const SERVER_VIEWPORT_WIDTH = 1440;

export type SplitPaneItem = SplitPaneSpec & {
  content: ReactNode;
  label?: string;
  resizeLabel?: string;
  collapsed?: boolean;
  onCollapsedChange?: (collapsed: boolean) => void;
  className?: string;
};

export type SplitPaneProps = {
  layoutKey: string;
  panes: SplitPaneItem[];
  orientation?: SplitOrientation;
  className?: string;
};

type DragState = {
  dividerIndex: number;
  start: number;
  base: SplitLayout;
};

function specOf(pane: SplitPaneItem): SplitPaneSpec {
  return {
    id: pane.id,
    minSize: pane.minSize,
    maxSize: pane.maxSize,
    defaultSize: pane.defaultSize,
    collapsible: pane.collapsible,
    flex: pane.flex,
    collapsedBelow: pane.collapsedBelow
  };
}

function withControlledCollapse(panes: SplitPaneItem[], layout: SplitLayout): SplitLayout {
  const collapsed: Record<string, boolean> = { ...layout.collapsed };
  for (const pane of panes) {
    if (pane.collapsed !== undefined) {
      collapsed[pane.id] = pane.collapsed;
    }
  }
  return { sizes: layout.sizes, collapsed };
}

export const SplitPane = forwardRef<HTMLDivElement, SplitPaneProps>(function SplitPane(
  { layoutKey, panes, orientation = "horizontal", className },
  ref
) {
  const specs: SplitPaneSpec[] = panes.map(specOf);
  const specsRef = useRef(specs);
  specsRef.current = specs;
  const idPrefix = useId();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<DragState | null>(null);
  const [containerSize, setContainerSize] = useState(0);
  const [stored, setStored] = useState<SplitLayout>(() => defaultSplitLayout(specs, SERVER_VIEWPORT_WIDTH));
  const [loaded, setLoaded] = useState(false);
  const [dragging, setDragging] = useState(false);
  const horizontal = orientation === "horizontal";

  const setRootRef = useCallback(
    (node: HTMLDivElement | null) => {
      rootRef.current = node;
      if (typeof ref === "function") {
        ref(node);
      } else if (ref) {
        ref.current = node;
      }
    },
    [ref]
  );

  useEffect(() => {
    const fallback = defaultSplitLayout(specsRef.current, window.innerWidth);
    let raw: string | null = null;
    try {
      raw = window.localStorage.getItem(splitStorageKey(layoutKey));
    } catch {
      raw = null;
    }
    setStored(parseStoredSplitLayout(raw, specsRef.current, fallback));
    setLoaded(true);
  }, [layoutKey]);

  useEffect(() => {
    if (!loaded) {
      return;
    }
    try {
      window.localStorage.setItem(splitStorageKey(layoutKey), serializeSplitLayout(stored));
    } catch {
      return;
    }
  }, [layoutKey, loaded, stored]);

  useEffect(() => {
    const node = rootRef.current;
    if (!node) {
      return;
    }
    const measure = () => {
      const borders = horizontal ? node.offsetWidth - node.clientWidth : node.offsetHeight - node.clientHeight;
      const outer = horizontal ? node.getBoundingClientRect().width : node.getBoundingClientRect().height;
      setContainerSize(Math.max(0, outer - borders));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [horizontal]);

  const effective = fitSplitLayout(specs, withControlledCollapse(panes, stored), containerSize);

  function commit(next: SplitLayout) {
    for (const pane of panes) {
      if (pane.collapsed !== undefined && next.collapsed[pane.id] !== effective.collapsed[pane.id]) {
        pane.onCollapsedChange?.(Boolean(next.collapsed[pane.id]));
      }
    }
    setStored(next);
  }

  function axis(event: PointerEvent<HTMLDivElement>): number {
    return horizontal ? event.clientX : event.clientY;
  }

  function onPointerDown(event: PointerEvent<HTMLDivElement>, dividerIndex: number) {
    if (event.button !== 0) {
      return;
    }
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { dividerIndex, start: axis(event), base: effective };
    setDragging(true);
  }

  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag) {
      return;
    }
    commit(moveDivider(specs, drag.base, drag.dividerIndex, axis(event) - drag.start, containerSize));
  }

  function onPointerEnd(event: PointerEvent<HTMLDivElement>) {
    dragRef.current = null;
    setDragging(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>, dividerIndex: number) {
    const action = splitKeyAction(event.key, event.shiftKey, orientation);
    if (!action) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    commit(applySplitKeyAction(specs, effective, dividerIndex, action, containerSize));
  }

  function onDoubleClick(dividerIndex: number) {
    const target = specs[dividerTargetIndex(specs, dividerIndex)];
    if (target) {
      commit(togglePaneCollapsed(specs, effective, target.id));
    }
  }

  return (
    <div
      ref={setRootRef}
      className={cn(
        "flex min-h-0 min-w-0 overflow-hidden rounded-token-lg border border-default bg-surface",
        horizontal ? "flex-row" : "flex-col",
        dragging && "select-none",
        className
      )}
      data-split-layout={layoutKey}
    >
      {panes.map((pane, index) => {
        const isCollapsed = !pane.flex && Boolean(effective.collapsed[pane.id]);
        const size = effective.sizes[pane.id] ?? pane.minSize;
        const target = index < panes.length - 1 ? panes[dividerTargetIndex(specs, index)] : undefined;
        const targetCollapsed = target ? Boolean(effective.collapsed[target.id]) : false;
        const targetSize = target ? effective.sizes[target.id] ?? target.minSize : 0;
        return [
          <div
            key={pane.id}
            aria-label={pane.label}
            className={cn("min-h-0 min-w-0 overflow-auto", pane.className)}
            data-split-pane={pane.id}
            hidden={isCollapsed}
            id={`${idPrefix}-${pane.id}`}
            role={pane.label ? "region" : undefined}
            style={pane.flex ? { flex: "1 1 0%" } : { flex: `0 0 ${isCollapsed ? 0 : size}px` }}
          >
            {pane.content}
          </div>,
          target ? (
            <div
              key={`divider-${pane.id}`}
              aria-controls={`${idPrefix}-${target.id}`}
              aria-label={target.resizeLabel}
              aria-orientation={horizontal ? "vertical" : "horizontal"}
              aria-valuemax={Math.round(paneSizeLimit(specs, effective, target.id, containerSize))}
              aria-valuemin={target.collapsible ? 0 : target.minSize}
              aria-valuenow={targetCollapsed ? 0 : Math.round(targetSize)}
              className={cn(
                "relative shrink-0 touch-none select-none outline-none",
                "before:absolute before:bg-border hover:before:bg-accent focus-visible:before:bg-accent",
                horizontal
                  ? "cursor-col-resize before:inset-y-0 before:left-1/2 before:w-px before:-translate-x-1/2 focus-visible:before:w-0.5"
                  : "cursor-row-resize before:inset-x-0 before:top-1/2 before:h-px before:-translate-y-1/2 focus-visible:before:h-0.5"
              )}
              data-split-divider={target.id}
              role="separator"
              style={horizontal ? { width: SPLIT_DIVIDER_SIZE } : { height: SPLIT_DIVIDER_SIZE }}
              tabIndex={0}
              onDoubleClick={() => onDoubleClick(index)}
              onKeyDown={(event) => onKeyDown(event, index)}
              onLostPointerCapture={() => {
                dragRef.current = null;
                setDragging(false);
              }}
              onPointerCancel={onPointerEnd}
              onPointerDown={(event) => onPointerDown(event, index)}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerEnd}
            />
          ) : null
        ];
      })}
    </div>
  );
});
