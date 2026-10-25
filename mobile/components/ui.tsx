import type { ReactNode } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View, type RefreshControlProps } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useTheme } from "@/theme";

export function Screen({ children, refreshControl }: { children: ReactNode; refreshControl?: React.ReactElement<RefreshControlProps> }) {
  const theme = useTheme();
  return (
    <SafeAreaView edges={["top", "left", "right"]} style={[styles.fill, { backgroundColor: theme.background }]}>
      <ScrollView contentContainerStyle={{ padding: theme.space * 1.5, gap: theme.space }} refreshControl={refreshControl}>
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}

export function Title({ children }: { children: ReactNode }) {
  const theme = useTheme();
  return (
    <Text accessibilityRole="header" style={[styles.title, { color: theme.text }]}>
      {children}
    </Text>
  );
}

export function Heading({ children }: { children: ReactNode }) {
  const theme = useTheme();
  return (
    <Text accessibilityRole="header" style={[styles.heading, { color: theme.text }]}>
      {children}
    </Text>
  );
}

export function Body({ children, muted = false, tone }: { children: ReactNode; muted?: boolean; tone?: "danger" }) {
  const theme = useTheme();
  const color = tone === "danger" ? theme.danger : muted ? theme.textMuted : theme.text;
  return <Text style={[styles.body, { color }]}>{children}</Text>;
}

export function Card({ children }: { children: ReactNode }) {
  const theme = useTheme();
  return (
    <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border, borderRadius: theme.radius, padding: theme.space }]}>
      {children}
    </View>
  );
}

export function Button({
  label,
  accessibilityLabel,
  onPress,
  variant = "primary",
  disabled = false,
  busy = false
}: {
  label: string;
  accessibilityLabel: string;
  onPress: () => void;
  variant?: "primary" | "secondary";
  disabled?: boolean;
  busy?: boolean;
}) {
  const theme = useTheme();
  const primary = variant === "primary";
  return (
    <Pressable
      accessibilityLabel={accessibilityLabel}
      accessibilityRole="button"
      accessibilityState={{ disabled: disabled || busy, busy }}
      disabled={disabled || busy}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        {
          minHeight: theme.touchTarget,
          borderRadius: theme.radius,
          backgroundColor: primary ? theme.accent : theme.surface,
          borderColor: primary ? theme.accent : theme.border,
          opacity: disabled ? 0.5 : pressed ? 0.8 : 1
        }
      ]}
    >
      {busy ? <ActivityIndicator color={primary ? theme.accentText : theme.text} /> : null}
      <Text style={[styles.buttonText, { color: primary ? theme.accentText : theme.text }]}>{label}</Text>
    </Pressable>
  );
}

export function Row({
  title,
  detail,
  accessibilityLabel,
  onPress,
  selected = false
}: {
  title: string;
  detail?: string;
  accessibilityLabel: string;
  onPress?: () => void;
  selected?: boolean;
}) {
  const theme = useTheme();
  const content = (
    <View style={styles.rowText}>
      <Text style={[styles.body, { color: theme.text, fontWeight: selected ? "700" : "500" }]}>{title}</Text>
      {detail ? <Text style={[styles.detail, { color: theme.textMuted }]}>{detail}</Text> : null}
    </View>
  );
  if (!onPress) {
    return (
      <View accessibilityLabel={accessibilityLabel} accessible style={[styles.row, { minHeight: theme.touchTarget, borderColor: theme.border }]}>
        {content}
      </View>
    );
  }
  return (
    <Pressable
      accessibilityLabel={accessibilityLabel}
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[styles.row, { minHeight: theme.touchTarget, borderColor: theme.border }]}
    >
      {content}
    </Pressable>
  );
}

export function Loading({ label }: { label: string }) {
  const theme = useTheme();
  return (
    <View accessibilityLabel={label} style={[styles.center, { backgroundColor: theme.background }]}>
      <ActivityIndicator color={theme.text} />
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 28, fontWeight: "700" },
  heading: { fontSize: 18, fontWeight: "600", marginTop: 8 },
  body: { fontSize: 16 },
  detail: { fontSize: 14, marginTop: 2 },
  card: { borderWidth: StyleSheet.hairlineWidth, gap: 8 },
  button: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, paddingHorizontal: 16, borderWidth: 1 },
  buttonText: { fontSize: 16, fontWeight: "600" },
  row: { flexDirection: "row", alignItems: "center", paddingVertical: 8, borderBottomWidth: StyleSheet.hairlineWidth },
  rowText: { flex: 1 }
});
