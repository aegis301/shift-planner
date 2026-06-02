"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import { t, type Locale, type TranslationKey } from "@/lib/i18n";

export type PlanningPeriodStatusAction = "status-draft" | "status-preliminary" | "status-published";

type PlanningPeriodStatus = "draft" | "preliminary" | "published";

type PlanningPeriodStatusMenuProps = {
  locale: Locale;
  status: PlanningPeriodStatus | null;
  disabled?: boolean;
  disabledReason?: TranslationKey;
  onSelectAction: (action: PlanningPeriodStatusAction) => void;
};

function statusLabelKey(status: PlanningPeriodStatus): TranslationKey {
  if (status === "published") {
    return "periodStatusPublished";
  }
  if (status === "preliminary") {
    return "periodStatusPreliminary";
  }
  return "periodStatusDraft";
}

function statusBadgeClass(status: PlanningPeriodStatus): string {
  if (status === "published") {
    return "border-emerald-200 bg-emerald-50 text-emerald-900";
  }
  if (status === "preliminary") {
    return "border-sky-200 bg-sky-50 text-sky-900";
  }
  return "border-amber-200 bg-amber-50 text-amber-900";
}

function transitionActions(status: PlanningPeriodStatus): PlanningPeriodStatusAction[] {
  if (status === "draft") {
    return ["status-preliminary"];
  }
  if (status === "preliminary") {
    return ["status-draft", "status-published"];
  }
  return ["status-preliminary"];
}

function actionLabelKey(action: PlanningPeriodStatusAction): TranslationKey {
  if (action === "status-published") {
    return "publishPlanningPeriod";
  }
  if (action === "status-preliminary") {
    return "setPlanningPeriodPreliminary";
  }
  return "setPlanningPeriodDraft";
}

export function PlanningPeriodStatusMenu({
  locale,
  status,
  disabled = false,
  disabledReason,
  onSelectAction
}: PlanningPeriodStatusMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  useEffect(() => {
    setOpen(false);
  }, [status, disabled]);

  const effectiveDisabled = disabled || status == null;
  const transitions = status ? transitionActions(status) : [];
  const triggerLabel = status
    ? t(locale, statusLabelKey(status))
    : t(locale, "planningPeriodStatusSelectGroup");

  return (
    <div ref={rootRef} className="relative min-w-44">
      <button
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={t(locale, "planningPeriodStatusMenu")}
        className={`inline-flex h-10 w-full items-center justify-between gap-2 rounded-lg border px-3 text-sm font-semibold shadow-sm disabled:cursor-not-allowed disabled:opacity-40 ${
          status ? statusBadgeClass(status) : "border-slate-200 bg-white text-slate-600"
        }`}
        disabled={effectiveDisabled}
        onClick={() => {
          if (!effectiveDisabled) {
            setOpen((value) => !value);
          }
        }}
        title={disabledReason ? t(locale, disabledReason) : undefined}
        type="button"
      >
        <span className="truncate">{triggerLabel}</span>
        <ChevronDown className={`h-4 w-4 shrink-0 transition ${open ? "rotate-180" : ""}`} />
      </button>
      {open && status ? (
        <div
          className="absolute right-0 z-20 mt-1 min-w-full rounded-lg border border-slate-200 bg-white py-1 shadow-lg ring-1 ring-slate-100"
          role="menu"
        >
          <div
            className="flex items-center gap-2 px-3 py-2 text-sm font-semibold text-slate-500"
            role="presentation"
          >
            <Check className="h-4 w-4 shrink-0 text-slate-400" aria-hidden />
            <span>{t(locale, statusLabelKey(status))}</span>
          </div>
          <div className="my-1 border-t border-slate-100" role="separator" />
          {transitions.map((action) => (
            <button
              key={action}
              className="block w-full px-3 py-2 text-left text-sm font-medium text-slate-800 hover:bg-slate-50"
              onClick={() => {
                setOpen(false);
                onSelectAction(action);
              }}
              role="menuitem"
              type="button"
            >
              {t(locale, actionLabelKey(action))}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
