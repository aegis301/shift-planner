import type { SlotCandidatesRead } from "@/lib/api/types";
import { t, type Locale, type TranslationKey } from "@/lib/i18n";

export type SlotCandidateRefusal = NonNullable<SlotCandidatesRead["candidates"][number]["refusal"]>;

const REFUSAL_LABEL_KEYS: Record<Exclude<SlotCandidateRefusal["code"], "blocking_rule">, TranslationKey> = {
  not_on_period_roster: "candidateRefusalNotOnPeriodRoster",
  not_in_covering_group: "candidateRefusalNotInCoveringGroup",
  no_go: "candidateRefusalNoGo",
  unavailable_day_status: "candidateRefusalUnavailableDayStatus"
};

export function slotCandidateRefusalLabel(locale: Locale, refusal: SlotCandidateRefusal | null | undefined): string | null {
  if (!refusal) {
    return null;
  }
  if (refusal.code !== "blocking_rule") {
    return t(locale, REFUSAL_LABEL_KEYS[refusal.code]);
  }
  if (!refusal.rule_code) {
    return t(locale, "candidateRefusalBlockingRuleUnknown");
  }
  return t(locale, "candidateRefusalBlockingRule", { rule: refusal.rule_code });
}
