import { createContext, forwardRef, useContext, useRef, type ComponentPropsWithoutRef, type ReactNode, type Ref } from "react";
import { Command } from "cmdk";
import { cn } from "@/components/ui/cn";
import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/popover";

const ComboboxAnchorRefContext = createContext<Ref<HTMLElement> | null>(null);

function assignRef<T>(ref: Ref<T> | null | undefined, value: T | null) {
  if (typeof ref === "function") {
    ref(value as T);
  } else if (ref) {
    (ref as { current: T | null }).current = value;
  }
}

export function Combobox({
  open,
  onOpenChange,
  children
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: ReactNode;
}) {
  const anchorRef = useRef<HTMLElement>(null);
  return (
    <ComboboxAnchorRefContext.Provider value={anchorRef}>
      <Popover open={open} onOpenChange={onOpenChange}>
        {children}
      </Popover>
    </ComboboxAnchorRefContext.Provider>
  );
}

export const ComboboxAnchor = forwardRef<HTMLElement, ComponentPropsWithoutRef<typeof PopoverAnchor>>(
  function ComboboxAnchor(props, ref) {
    const anchorRef = useContext(ComboboxAnchorRefContext);
    return (
      <PopoverAnchor
        ref={(node) => {
          assignRef(anchorRef, node);
          assignRef(ref, node);
        }}
        {...props}
      />
    );
  }
);

export const ComboboxContent = forwardRef<
  HTMLDivElement,
  ComponentPropsWithoutRef<typeof PopoverContent> & { shouldFilter?: boolean }
>(function ComboboxContent({ className, children, shouldFilter = true, onCloseAutoFocus, onInteractOutside, ...props }, ref) {
  const anchorRef = useContext(ComboboxAnchorRefContext);
  const anchor = () => (anchorRef && typeof anchorRef !== "function" ? anchorRef.current : null);
  return (
    <PopoverContent
      ref={ref}
      align="start"
      className={cn("w-[var(--radix-popover-trigger-width)] min-w-[12.5rem] p-0", className)}
      onOpenAutoFocus={(event) => event.preventDefault()}
      onCloseAutoFocus={(event) => {
        onCloseAutoFocus?.(event);
        const node = anchor();
        if (!event.defaultPrevented && node) {
          event.preventDefault();
          node.focus();
        }
      }}
      onInteractOutside={(event) => {
        onInteractOutside?.(event);
        const node = anchor();
        const target = event.target;
        if (!event.defaultPrevented && node && target instanceof Node && node.contains(target)) {
          event.preventDefault();
        }
      }}
      {...props}
    >
      <Command className="flex max-h-[min(50vh,17.5rem)] flex-col overflow-hidden" loop shouldFilter={shouldFilter}>
        {children}
      </Command>
    </PopoverContent>
  );
});

export const ComboboxInput = forwardRef<HTMLInputElement, ComponentPropsWithoutRef<typeof Command.Input>>(
  function ComboboxInput({ className, ...props }, ref) {
    return (
      <div className="border-b border-default p-2">
        <Command.Input
          ref={ref}
          className={cn(
            "h-9 w-full rounded-token-md border border-default bg-surface px-2 text-xs text-text outline-none placeholder:text-muted",
            className
          )}
          {...props}
        />
      </div>
    );
  }
);

export const ComboboxList = forwardRef<HTMLDivElement, ComponentPropsWithoutRef<typeof Command.List>>(
  function ComboboxList({ className, ...props }, ref) {
    return (
      <Command.List ref={ref} className={cn("min-h-0 flex-1 overflow-y-auto py-1", className)} {...props} />
    );
  }
);

export const ComboboxItem = forwardRef<HTMLDivElement, ComponentPropsWithoutRef<typeof Command.Item>>(
  function ComboboxItem({ className, ...props }, ref) {
    return (
      <Command.Item
        ref={ref}
        className={cn(
          "flex cursor-pointer items-center gap-2 px-3 py-2 text-left text-xs text-text outline-none data-[selected=true]:bg-surface-muted",
          className
        )}
        {...props}
      />
    );
  }
);

export const ComboboxEmpty = Command.Empty;
