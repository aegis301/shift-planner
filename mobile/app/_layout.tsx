import { useState } from "react";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { AuthProvider } from "@/lib/auth";
import { LocaleProvider, useLocale } from "@/lib/locale";

function Screens() {
  const { t } = useLocale();
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="duty/[id]" options={{ headerShown: true, title: t("mobileDutyTitle"), headerBackTitle: t("mobileBack") }} />
    </Stack>
  );
}

export default function RootLayout() {
  const [queryClient] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 30_000 } } }));
  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <LocaleProvider>
          <AuthProvider>
            <StatusBar style="auto" />
            <Screens />
          </AuthProvider>
        </LocaleProvider>
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
