import { forwardRef, type ComponentPropsWithoutRef } from "react";
import * as ToggleGroupPrimitive from "@radix-ui/react-toggle-group";
import { cn } from "@/components/ui/cn";

export const ToggleGroup = forwardRef<HTMLDivElement, ComponentPropsWithoutRef<typeof ToggleGroupPrimitive.Root>>(
  function ToggleGroup({ className, ...props }, ref) {
    return (
      <ToggleGroupPrimitive.Root
        ref={ref}
        className={cn("inline-flex gap-1 rounded-token-lg border border-default bg-surface p-1", className)}
        {...props}
      />
    );
  }
);

export const ToggleGroupItem = forwardRef<
  HTMLButtonElement,
  ComponentPropsWithoutRef<typeof ToggleGroupPrimitive.Item>
>(function ToggleGroupItem({ className, ...props }, ref) {
  return (
    <ToggleGroupPrimitive.Item
      ref={ref}
      className={cn(
        "inline-flex h-8 items-center justify-center rounded-token-md px-3 text-sm font-semibold text-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent data-[state=on]:bg-text data-[state=on]:text-surface",
        className
      )}
      {...props}
    />
  );
});
