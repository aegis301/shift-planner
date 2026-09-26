import { forwardRef, type HTMLAttributes } from "react";
import { cn } from "@/components/ui/cn";

export const Kbd = forwardRef<HTMLElement, HTMLAttributes<HTMLElement>>(function Kbd(
  { className, ...props },
  ref
) {
  return (
    <kbd
      ref={ref}
      className={cn(
        "inline-flex h-5 min-w-5 items-center justify-center rounded-token-sm border border-default bg-surface-muted px-1 font-mono text-[0.65rem] text-muted",
        className
      )}
      {...props}
    />
  );
});
