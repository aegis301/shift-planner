import { useState } from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";
import { ApiError } from "@shift-planner/api-client";
import { Body, Button, Screen, Title } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { apiBaseUrl } from "@/lib/config";
import { useLocale } from "@/lib/locale";
import { useTheme } from "@/theme";

export function SignInScreen() {
  const { signIn } = useAuth();
  const { t } = useLocale();
  const theme = useTheme();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const configured = apiBaseUrl() !== "";

  async function submit() {
    if (!email.trim() || !password) {
      setError(t("mobileSignInMissing"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      await signIn(email.trim(), password);
    } catch (caught) {
      setError(caught instanceof ApiError && caught.status === 401 ? t("mobileSignInInvalid") : t("mobileSignInFailed"));
    } finally {
      setBusy(false);
    }
  }

  const inputStyle = [
    styles.input,
    { minHeight: theme.touchTarget, borderColor: theme.border, borderRadius: theme.radius, color: theme.text, backgroundColor: theme.surface }
  ];

  return (
    <Screen>
      <Title>{t("mobileSignInTitle")}</Title>
      {!configured ? <Body tone="danger">{t("mobileApiNotConfigured")}</Body> : null}
      <View style={styles.field}>
        <Text style={{ color: theme.text }}>{t("email")}</Text>
        <TextInput
          accessibilityLabel={t("email")}
          autoCapitalize="none"
          autoComplete="email"
          inputMode="email"
          onChangeText={setEmail}
          style={inputStyle}
          textContentType="username"
          value={email}
        />
      </View>
      <View style={styles.field}>
        <Text style={{ color: theme.text }}>{t("password")}</Text>
        <TextInput
          accessibilityLabel={t("password")}
          autoComplete="current-password"
          onChangeText={setPassword}
          onSubmitEditing={() => void submit()}
          secureTextEntry
          style={inputStyle}
          textContentType="password"
          value={password}
        />
      </View>
      {error ? (
        <Text accessibilityLiveRegion="polite" accessibilityRole="alert" style={{ color: theme.danger, fontSize: 16 }}>
          {error}
        </Text>
      ) : null}
      <Button
        accessibilityLabel={t("mobileSignInSubmit")}
        busy={busy}
        disabled={!configured}
        label={t("mobileSignInSubmit")}
        onPress={() => void submit()}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  field: { gap: 4 },
  input: { borderWidth: 1, paddingHorizontal: 12, fontSize: 16 }
});
