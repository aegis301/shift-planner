import { forwardRef, type ComponentPropsWithoutRef } from "react";
import * as ScrollAreaPrimitive from "@radix-ui/react-scroll-area";
import { cn } from "@/components/ui/cn";

export const ScrollArea = forwardRef<HTMLDivElement, ComponentPropsWithoutRef<typeof ScrollAreaPrimitive.Root>>(
  function ScrollArea({ className, children, ...props }, ref) {
    return (
      <ScrollAreaPrimitive.Root ref={ref} className={cn("overflow-hidden", className)} {...props}>
        <ScrollAreaPrimitive.Viewport className="h-full w-full">{children}</ScrollAreaPrimitive.Viewport>
        <ScrollAreaPrimitive.Scrollbar
          orientation="vertical"
          className="flex w-2 touch-none p-0.5"
        >
          <ScrollAreaPrimitive.Thumb className="relative flex-1 rounded-full bg-border" />
        </ScrollAreaPrimitive.Scrollbar>
      </ScrollAreaPrimitive.Root>
    );
  }
);
