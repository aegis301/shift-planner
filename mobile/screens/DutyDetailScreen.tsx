import type { TranslationKey } from "@shift-planner/i18n";
import { sessionTimeZone } from "@shift-planner/domain";
import { Body, Card, Heading, Screen, Title } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { dutyTitle, formatDutyDate, formatDutyTimes } from "@/lib/duties";
import { useLocale } from "@/lib/locale";
import { useMemberDuties } from "@/lib/queries";
import { useDutyWindow } from "@/screens/DutiesScreen";

const PLAN_STATUS_LABELS: Record<string, TranslationKey> = {
  draft: "periodStatusDraft",
  preliminary: "periodStatusPreliminary",
  published: "periodStatusPublished"
};

export function DutyDetailScreen({ rosterSlotId, slotDate }: { rosterSlotId: number; slotDate?: string }) {
  const { session } = useAuth();
  const { locale, t } = useLocale();
  const listWindow = useDutyWindow();
  const duties = useMemberDuties(slotDate ? { from: slotDate, to: slotDate } : listWindow);
  const duty = duties.data?.find((row) => row.roster_slot_id === rosterSlotId);
  const timeZone = sessionTimeZone(session);

  if (!duty) {
    return (
      <Screen>
        <Title>{t("mobileDutyTitle")}</Title>
        {duties.isSuccess ? <Body muted>{t("mobileDutyNotFound")}</Body> : null}
      </Screen>
    );
  }
  const statusKey = duty.plan_status ? PLAN_STATUS_LABELS[duty.plan_status] : undefined;
  return (
    <Screen>
      <Title>{dutyTitle(duty)}</Title>
      <Card>
        <Heading>{t("mobileDutyDate")}</Heading>
        <Body>{formatDutyDate(duty.slot_date, locale)}</Body>
        <Heading>{t("mobileDutyTime")}</Heading>
        <Body>{formatDutyTimes(duty, timeZone, locale)}</Body>
        <Body muted>{t("mobileDutyTimeZone", { zone: timeZone })}</Body>
        <Heading>{t("mobileDutyTemplate")}</Heading>
        <Body>{duty.template_name || duty.template_code || t("emptyValue")}</Body>
        <Heading>{t("mobileDutyGroup")}</Heading>
        <Body>{duty.shift_group_name || t("emptyValue")}</Body>
        <Heading>{t("mobileDutyStatus")}</Heading>
        <Body>{statusKey ? t(statusKey) : t("emptyValue")}</Body>
      </Card>
    </Screen>
  );
}
