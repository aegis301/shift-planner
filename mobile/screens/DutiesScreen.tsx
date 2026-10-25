import { useMemo } from "react";
import { RefreshControl, SectionList, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { localDateKey, sessionTimeZone } from "@shift-planner/domain";
import { Body, Button, Row, Title } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { dutyTitle, formatDutyDate, formatDutyTimes, groupDutiesByWeek, windowAround } from "@/lib/duties";
import { useLocale } from "@/lib/locale";
import { useMemberDuties } from "@/lib/queries";
import { useTheme } from "@/theme";

export function useDutyWindow(): { from: string; to: string } {
  const { session } = useAuth();
  const today = localDateKey(new Date().toISOString(), sessionTimeZone(session));
  return useMemo(() => windowAround(today), [today]);
}

export function DutiesScreen({ onOpenDuty }: { onOpenDuty: (rosterSlotId: number) => void }) {
  const { session } = useAuth();
  const { locale, t } = useLocale();
  const theme = useTheme();
  const timeZone = sessionTimeZone(session);
  const window = useDutyWindow();
  const duties = useMemberDuties(window);
  const sections = useMemo(() => groupDutiesByWeek(duties.data ?? []), [duties.data]);

  return (
    <SafeAreaView edges={["top", "left", "right"]} style={[styles.fill, { backgroundColor: theme.background }]}>
      <SectionList
        ListEmptyComponent={duties.isSuccess ? <Body muted>{t("mobileDutiesEmpty")}</Body> : null}
        ListHeaderComponent={
          <View style={{ gap: theme.space }}>
            <Title>{t("mobileTabDuties")}</Title>
            {duties.isError ? (
              <>
                <Body tone="danger">{t("mobileLoadFailed")}</Body>
                <Button accessibilityLabel={t("mobileRetry")} label={t("mobileRetry")} onPress={() => void duties.refetch()} variant="secondary" />
              </>
            ) : null}
          </View>
        }
        contentContainerStyle={{ padding: theme.space * 1.5, gap: 4 }}
        keyExtractor={(duty) => String(duty.roster_slot_id)}
        refreshControl={
          <RefreshControl accessibilityLabel={t("mobileRefresh")} onRefresh={() => void duties.refetch()} refreshing={duties.isRefetching} />
        }
        renderItem={({ item }) => {
          const detail = `${formatDutyDate(item.slot_date, locale)} · ${formatDutyTimes(item, timeZone, locale)}`;
          return (
            <Row
              accessibilityLabel={`${dutyTitle(item)}, ${detail}`}
              detail={detail}
              onPress={() => onOpenDuty(item.roster_slot_id)}
              title={dutyTitle(item)}
            />
          );
        }}
        renderSectionHeader={({ section }) => (
          <Text accessibilityRole="header" style={[styles.section, { color: theme.textMuted }]}>
            {t("mobileWeekOf", { date: formatDutyDate(section.weekStart, locale) })}
          </Text>
        )}
        sections={sections}
        stickySectionHeadersEnabled={false}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  section: { fontSize: 14, fontWeight: "600", marginTop: 16, textTransform: "uppercase" }
});
