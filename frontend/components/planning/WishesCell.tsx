import type { PlanningDayStatusColorPreset } from "@/lib/planningDayStatus";
import { planningDayStatusBadgeClass, planningDayStatusSolidClass } from "@/lib/planningDayStatus";
import { t, type Locale } from "@/lib/i18n";

export function WishesCellView({
  label,
  colorPreset,
  comment,
  wishCount,
  noGoCount,
  locale
}: {
  label: string;
  colorPreset: PlanningDayStatusColorPreset | null;
  comment: string;
  wishCount: number;
  noGoCount: number;
  locale: Locale;
}) {
  return (
    <span className="flex min-w-0 items-center gap-1">
      <span className={`h-2 w-2 shrink-0 rounded-full ${colorPreset ? planningDayStatusSolidClass(colorPreset) : "bg-slate-300"}`} />
      <span className={`truncate font-medium ${colorPreset ? "" : "text-ink"}`}>
        {colorPreset ? (
          <span className={`rounded-token-sm px-1 ring-1 ${planningDayStatusBadgeClass(colorPreset)}`}>{label}</span>
        ) : (
          label || t(locale, "emptyValue")
        )}
      </span>
      {wishCount > 0 ? (
        <span className="text-info">
          {t(locale, "wishShort")}
          {wishCount > 1 ? ` ${wishCount}` : ""}
        </span>
      ) : null}
      {noGoCount > 0 ? (
        <span className="text-danger">
          {t(locale, "noGoShort")}
          {noGoCount > 1 ? ` ${noGoCount}` : ""}
        </span>
      ) : null}
      {comment.trim() ? <span className="text-info">{t(locale, "dayCommentMarker")}</span> : null}
    </span>
  );
}
