import { forwardRef, type ComponentPropsWithoutRef } from "react";
import * as AlertDialogPrimitive from "@radix-ui/react-alert-dialog";
import { cn } from "@/components/ui/cn";
import { Button, type ButtonProps } from "@/components/ui/button";

export const AlertDialog = AlertDialogPrimitive.Root;
export const AlertDialogTrigger = AlertDialogPrimitive.Trigger;

export const AlertDialogContent = forwardRef<
  HTMLDivElement,
  ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Content>
>(function AlertDialogContent({ className, ...props }, ref) {
  return (
    <AlertDialogPrimitive.Portal>
      <AlertDialogPrimitive.Overlay className="fixed inset-0 z-50 bg-ink/30 backdrop-blur-sm" />
      <AlertDialogPrimitive.Content
        ref={ref}
        className={cn(
          "fixed left-1/2 top-1/2 z-50 w-[min(100%-1.5rem,28rem)] -translate-x-1/2 -translate-y-1/2 rounded-token-lg bg-surface p-5 text-text shadow-soft ring-1 ring-severity-error focus:outline-none",
          className
        )}
        {...props}
      />
    </AlertDialogPrimitive.Portal>
  );
});

export const AlertDialogTitle = forwardRef<
  HTMLHeadingElement,
  ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Title>
>(function AlertDialogTitle({ className, ...props }, ref) {
  return (
    <AlertDialogPrimitive.Title ref={ref} className={cn("text-lg font-semibold text-text", className)} {...props} />
  );
});

export const AlertDialogDescription = forwardRef<
  HTMLParagraphElement,
  ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Description>
>(function AlertDialogDescription({ className, ...props }, ref) {
  return (
    <AlertDialogPrimitive.Description ref={ref} className={cn("mt-2 text-sm text-muted", className)} {...props} />
  );
});

export const AlertDialogCancel = forwardRef<HTMLButtonElement, ButtonProps>(function AlertDialogCancel(
  { className, ...props },
  ref
) {
  return (
    <AlertDialogPrimitive.Cancel asChild>
      <Button ref={ref} variant="secondary" className={className} {...props} />
    </AlertDialogPrimitive.Cancel>
  );
});

export const AlertDialogAction = forwardRef<HTMLButtonElement, ButtonProps>(function AlertDialogAction(
  { className, variant = "danger", ...props },
  ref
) {
  return (
    <AlertDialogPrimitive.Action asChild>
      <Button ref={ref} variant={variant} className={className} {...props} />
    </AlertDialogPrimitive.Action>
  );
});
