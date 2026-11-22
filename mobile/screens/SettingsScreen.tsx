import { useState } from "react";
import { Body, Button, Card, Heading, Row, Screen, Title } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { appVersion } from "@/lib/config";
import { useLocale } from "@/lib/locale";
import { userSession } from "@/lib/session";

export function SettingsScreen() {
  const { session, signOut, switchOrganization } = useAuth();
  const { locale, setLocale, t } = useLocale();
  const [switching, setSwitching] = useState("");
  const [error, setError] = useState("");
  const user = userSession(session);
  const memberships = user?.memberships ?? [];

  async function choose(slug: string) {
    setSwitching(slug);
    setError("");
    try {
      await switchOrganization(slug);
    } catch {
      setError(t("mobileSwitchFailed"));
    } finally {
      setSwitching("");
    }
  }

  return (
    <Screen>
      <Title>{t("mobileTabSettings")}</Title>
      <Heading>{t("mobileSettingsLanguage")}</Heading>
      <Card>
        <Row accessibilityLabel={t("mobileLanguageGerman")} onPress={() => setLocale("de")} selected={locale === "de"} title={t("mobileLanguageGerman")} />
        <Row accessibilityLabel={t("mobileLanguageEnglish")} onPress={() => setLocale("en")} selected={locale === "en"} title={t("mobileLanguageEnglish")} />
      </Card>
      <Heading>{t("mobileSettingsOrganization")}</Heading>
      <Card>
        {memberships.length > 1 ? (
          memberships.map((membership) => {
            const current = membership.organization.id === user?.organization_id;
            return (
              <Row
                key={membership.membership_id}
                accessibilityLabel={t("mobileSwitchOrganization", { name: membership.organization.name })}
                detail={current ? t("mobileCurrentOrganization") : switching === membership.organization.slug ? t("mobileLoading") : undefined}
                onPress={current ? undefined : () => void choose(membership.organization.slug)}
                selected={current}
                title={membership.organization.name}
              />
            );
          })
        ) : (
          <Body>{user?.organization.name ?? t("emptyValue")}</Body>
        )}
        {error ? <Body tone="danger">{error}</Body> : null}
      </Card>
      <Heading>{t("mobileSettingsAccount")}</Heading>
      <Body>{session?.email ?? t("emptyValue")}</Body>
      <Heading>{t("mobileSettingsVersion")}</Heading>
      <Body muted>{appVersion()}</Body>
      <Button accessibilityLabel={t("mobileSignOut")} label={t("mobileSignOut")} onPress={() => void signOut()} variant="secondary" />
    </Screen>
  );
}
