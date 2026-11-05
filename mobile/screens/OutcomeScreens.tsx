import { Linking } from "react-native";
import { Body, Button, Screen, Title } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { webBaseUrl } from "@/lib/config";
import { useLocale } from "@/lib/locale";

function OutcomeScreen({ title, body, linkLabel, path }: { title: string; body: string; linkLabel: string; path: string }) {
  const { signOut } = useAuth();
  const { t } = useLocale();
  const base = webBaseUrl();
  return (
    <Screen>
      <Title>{title}</Title>
      <Body>{body}</Body>
      {base ? (
        <Button accessibilityLabel={linkLabel} label={linkLabel} onPress={() => void Linking.openURL(`${base}${path}`)} />
      ) : null}
      <Button accessibilityLabel={t("mobileSignOut")} label={t("mobileSignOut")} onPress={() => void signOut()} variant="secondary" />
    </Screen>
  );
}

export function NoMemberScreen() {
  const { t } = useLocale();
  return <OutcomeScreen body={t("mobileNoMemberBody")} linkLabel={t("mobileOpenWorkbench")} path="/" title={t("mobileNoMemberTitle")} />;
}

export function OnboardingScreen() {
  const { t } = useLocale();
  return (
    <OutcomeScreen body={t("mobileOnboardingBody")} linkLabel={t("mobileOpenOnboarding")} path="/onboarding" title={t("mobileOnboardingTitle")} />
  );
}
