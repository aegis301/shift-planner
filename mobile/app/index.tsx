import { Redirect } from "expo-router";
import { Loading } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { useLocale } from "@/lib/locale";
import { routeFor } from "@/lib/routes";

export default function Index() {
  const { status, session } = useAuth();
  const { t } = useLocale();
  const target = routeFor(status, session);
  if (target == null) {
    return <Loading label={t("mobileLoading")} />;
  }
  return <Redirect href={target} />;
}
