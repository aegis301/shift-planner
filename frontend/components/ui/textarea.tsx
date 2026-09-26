import { forwardRef, type TextareaHTMLAttributes } from "react";
import { cn } from "@/components/ui/cn";

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...props }, ref) {
    return (
      <textarea
        ref={ref}
        className={cn(
          "min-h-[6rem] w-full rounded-token-md border border-default bg-surface px-3 py-2 text-sm text-text placeholder:text-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
          className
        )}
        {...props}
      />
    );
  }
);
