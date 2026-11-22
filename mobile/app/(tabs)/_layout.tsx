import { Tabs } from "expo-router";
import { Gate } from "@/components/Gate";
import { useLocale } from "@/lib/locale";
import { useTheme } from "@/theme";

export default function TabsLayout() {
  const { t } = useLocale();
  const theme = useTheme();
  return (
    <Gate route="/(tabs)">
      <Tabs
        screenOptions={{
          headerShown: false,
          tabBarActiveTintColor: theme.text,
          tabBarInactiveTintColor: theme.textMuted,
          tabBarStyle: { backgroundColor: theme.surface, borderTopColor: theme.border, minHeight: theme.touchTarget + 12 }
        }}
      >
        <Tabs.Screen name="index" options={{ title: t("mobileTabHome"), tabBarAccessibilityLabel: t("mobileTabHome"), tabBarIcon: () => null }} />
        <Tabs.Screen name="duties" options={{ title: t("mobileTabDuties"), tabBarAccessibilityLabel: t("mobileTabDuties"), tabBarIcon: () => null }} />
        <Tabs.Screen
          name="settings"
          options={{ title: t("mobileTabSettings"), tabBarAccessibilityLabel: t("mobileTabSettings"), tabBarIcon: () => null }}
        />
      </Tabs>
    </Gate>
  );
}
