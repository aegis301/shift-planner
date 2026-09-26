"use client";

import { Check, ChevronDown } from "lucide-react";
import { t, type Locale, type TranslationKey } from "@/lib/i18n";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger
} from "@/components/ui/dropdown-menu";

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
  const effectiveDisabled = disabled || status == null;
  const transitions = status ? transitionActions(status) : [];
  const triggerLabel = status
    ? t(locale, statusLabelKey(status))
    : t(locale, "planningPeriodStatusSelectGroup");

  return (
    <DropdownMenu key={status ?? "none"}>
      <DropdownMenuTrigger asChild disabled={effectiveDisabled}>
        <button
          aria-label={t(locale, "planningPeriodStatusMenu")}
          className={`group inline-flex h-10 min-w-44 items-center justify-between gap-2 rounded-lg border px-3 text-sm font-semibold shadow-sm disabled:cursor-not-allowed disabled:opacity-40 ${
            status ? statusBadgeClass(status) : "border-slate-200 bg-white text-slate-600"
          }`}
          disabled={effectiveDisabled}
          title={disabledReason ? t(locale, disabledReason) : undefined}
          type="button"
        >
          <span className="truncate">{triggerLabel}</span>
          <ChevronDown className="h-4 w-4 shrink-0 transition group-data-[state=open]:rotate-180" />
        </button>
      </DropdownMenuTrigger>
      {status ? (
        <DropdownMenuContent align="end" className="min-w-44">
          <DropdownMenuLabel className="flex items-center gap-2 normal-case tracking-normal text-sm font-semibold">
            <Check className="h-4 w-4 shrink-0 text-slate-400" aria-hidden />
            <span>{t(locale, statusLabelKey(status))}</span>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          {transitions.map((action) => (
            <DropdownMenuItem key={action} className="font-medium text-slate-800" onSelect={() => onSelectAction(action)}>
              {t(locale, actionLabelKey(action))}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      ) : null}
    </DropdownMenu>
  );
}
