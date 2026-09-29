import type { ReactNode } from "react";
import { PlanningPeriodStatusMenu, type PlanningPeriodStatusAction } from "@/components/PlanningPeriodStatusMenu";
import { inputClass } from "@/components/Card";
import { t, type Locale } from "@/lib/i18n";

type Option = { id: string; label: string };

export function ContextBar({
  locale,
  periods,
  periodId,
  onPeriod,
  groups,
  shiftGroupId,
  onShiftGroup,
  allowAllGroups,
  status = null,
  statusDisabled = false,
  onStatus,
  versionLabel = null,
  statusReason = null,
  actions
}: {
  locale: Locale;
  periods: Option[];
  periodId: string;
  onPeriod: (id: string) => void;
  groups: Option[];
  shiftGroupId: string;
  onShiftGroup: (id: string) => void;
  allowAllGroups: boolean;
  status?: "draft" | "preliminary" | "published" | null;
  statusDisabled?: boolean;
  onStatus?: (action: PlanningPeriodStatusAction) => void;
  versionLabel?: string | null;
  statusReason?: string | null;
  actions?: ReactNode;
}) {
  return (
    <div data-slot="workbench-context-bar" className="flex flex-wrap items-end gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2">
      <label className="grid gap-1 text-xs font-medium text-slate-600">
        {t(locale, "planningPeriod")}
        <select className={`${inputClass} h-10 min-w-36`} value={periodId} onChange={(event) => onPeriod(event.target.value)}>
          <option value="">{t(locale, "emptyValue")}</option>
          {periods.map((period) => (
            <option key={period.id} value={period.id}>
              {period.label}
            </option>
          ))}
        </select>
      </label>
      <label className="grid gap-1 text-xs font-medium text-slate-600">
        {t(locale, "selectPlanningShiftGroup")}
        <select className={`${inputClass} h-10 min-w-40`} value={shiftGroupId} onChange={(event) => onShiftGroup(event.target.value)}>
          {allowAllGroups ? <option value="">{t(locale, "allShiftGroupsLabel")}</option> : null}
          {groups.map((group) => (
            <option key={group.id} value={group.id}>
              {group.label}
            </option>
          ))}
        </select>
      </label>
      {onStatus ? (
        <div className="grid gap-1">
          <span className="text-xs font-medium text-slate-600">{t(locale, "planningPeriodStatus")}</span>
          <PlanningPeriodStatusMenu
            disabled={statusDisabled}
            disabledReason="planningPeriodStatusSelectGroup"
            locale={locale}
            onSelectAction={onStatus}
            status={status}
          />
        </div>
      ) : null}
      {versionLabel ? <p className="mb-2 text-sm font-medium text-slate-700">{versionLabel}</p> : null}
      {statusReason ? <p className="mb-2 text-sm font-medium text-amber-900">{statusReason}</p> : null}
      <div className="ml-auto flex flex-wrap items-center gap-2">{actions}</div>
    </div>
  );
}
