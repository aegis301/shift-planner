import { forwardRef, type HTMLAttributes } from "react";
import { cn } from "@/components/ui/cn";

type BadgeVariant = "neutral" | "info" | "warning" | "error";

const variantClass: Record<BadgeVariant, string> = {
  neutral: "bg-surface-muted text-muted ring-border",
  info: "bg-severity-info text-text ring-severity-info",
  warning: "bg-severity-warning text-text ring-severity-warning",
  error: "bg-severity-error text-text ring-severity-error"
};

export type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  variant?: BadgeVariant;
};

export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(function Badge(
  { className, variant = "neutral", ...props },
  ref
) {
  return (
    <span
      ref={ref}
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ring-1",
        variantClass[variant],
        className
      )}
      {...props}
    />
  );
});
