import { Ban } from "lucide-react";
import type { PlanningDayStatusColorPreset } from "@/lib/planningDayStatus";
import { planningDayStatusFillClass } from "@/lib/planningDayStatus";
import { intentChipClass } from "@/lib/wishesMonth";
import { t, type Locale } from "@/lib/i18n";

export function WishesCellView({
  label,
  colorPreset,
  blocking,
  comment,
  wishCount,
  noGoCount,
  locale,
  memberId,
  date
}: {
  label: string;
  colorPreset: PlanningDayStatusColorPreset | null;
  blocking: boolean;
  comment: string;
  wishCount: number;
  noGoCount: number;
  locale: Locale;
  memberId: number;
  date: string;
}) {
  return (
    <span
      className={`absolute inset-0 flex min-w-0 items-center gap-1 px-[var(--space-cell-x)] ${colorPreset ? planningDayStatusFillClass(colorPreset) : ""}`}
      data-wishes-date={date}
      data-wishes-member={memberId}
    >
      {blocking ? (
        <span className="inline-flex shrink-0 items-center gap-0.5 rounded-token-sm bg-ink px-1 text-[0.65rem] font-semibold text-white">
          <Ban aria-hidden className="h-3 w-3" />
          {t(locale, "wishesBlockMark")}
        </span>
      ) : null}
      <span className={`truncate font-medium ${colorPreset ? "" : "text-ink"}`}>{label || t(locale, "emptyValue")}</span>
      {wishCount > 0 ? <IntentChip count={wishCount} kind="wish" locale={locale} /> : null}
      {noGoCount > 0 ? <IntentChip count={noGoCount} kind="no_go" locale={locale} /> : null}
      {comment.trim() ? <span className="shrink-0 text-info">{t(locale, "dayCommentMarker")}</span> : null}
    </span>
  );
}

export function IntentChip({ kind, locale, count = 1 }: { kind: "wish" | "no_go"; locale: Locale; count?: number }) {
  const label = t(locale, kind === "wish" ? "wishShort" : "noGoShort");
  return (
    <span className={`shrink-0 rounded-token-sm px-1 font-semibold ${intentChipClass(kind)}`}>
      {label}
      {count > 1 ? ` ${count}` : ""}
    </span>
  );
}
