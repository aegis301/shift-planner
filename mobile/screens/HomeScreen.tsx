import { RefreshControl } from "react-native";
import { shiftSwapKindLabel, shiftSwapStatusLabel, sessionTimeZone } from "@shift-planner/domain";
import { Body, Button, Card, Heading, Row, Screen, Title } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { dutyTitle, formatDutyDate, formatDutyTimes } from "@/lib/duties";
import { useLocale } from "@/lib/locale";
import { useMemberHome } from "@/lib/queries";

export function HomeScreen({ onOpenDuty }: { onOpenDuty: (rosterSlotId: number) => void }) {
  const { session } = useAuth();
  const { locale, t } = useLocale();
  const home = useMemberHome();
  const timeZone = sessionTimeZone(session);
  const data = home.data;
  const wishes = data?.draft_wishes ?? null;
  const month = wishes ? `${String(wishes.month).padStart(2, "0")}/${wishes.year}` : "";

  return (
    <Screen refreshControl={<RefreshControl accessibilityLabel={t("mobileRefresh")} onRefresh={() => void home.refetch()} refreshing={home.isRefetching} />}>
      <Title>{t("mobileTabHome")}</Title>
      {home.isError ? (
        <Card>
          <Body tone="danger">{t("mobileLoadFailed")}</Body>
          <Button accessibilityLabel={t("mobileRetry")} label={t("mobileRetry")} onPress={() => void home.refetch()} variant="secondary" />
        </Card>
      ) : null}
      <Heading>{t("mobileHomeNextDuties")}</Heading>
      {data && data.duties.length === 0 ? <Body muted>{t("mobileHomeNoDuties")}</Body> : null}
      {data?.duties.map((duty) => {
        const detail = `${formatDutyDate(duty.slot_date, locale)} · ${formatDutyTimes(duty, timeZone, locale)}`;
        return (
          <Row
            key={duty.roster_slot_id}
            accessibilityLabel={`${dutyTitle(duty)}, ${detail}`}
            detail={detail}
            onPress={() => onOpenDuty(duty.roster_slot_id)}
            title={dutyTitle(duty)}
          />
        );
      })}
      <Heading>{t("mobileHomeSwapActions")}</Heading>
      {data && data.swap_actions.length === 0 ? <Body muted>{t("mobileHomeNoSwapActions")}</Body> : null}
      {data?.swap_actions.map((action) => {
        const title = shiftSwapKindLabel(locale, action.kind);
        const detail = shiftSwapStatusLabel(locale, action.status);
        return <Row key={action.id} accessibilityLabel={`${title}, ${detail}`} detail={detail} title={title} />;
      })}
      <Heading>{t("mobileHomeWishesTitle")}</Heading>
      {data && !wishes ? <Body muted>{t("mobileHomeNoWishes")}</Body> : null}
      {wishes ? (
        <Body>
          {wishes.wishes_deadline
            ? t("mobileHomeWishesDeadline", { month, date: formatDutyDate(wishes.wishes_deadline, locale) })
            : t("mobileHomeWishesNoDeadline", { month })}
        </Body>
      ) : null}
    </Screen>
  );
}
