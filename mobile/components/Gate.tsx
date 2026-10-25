import type { ReactNode } from "react";
import { Redirect } from "expo-router";
import { Loading } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { useLocale } from "@/lib/locale";
import { routeFor, type AppRoute } from "@/lib/routes";

export function Gate({ route, children }: { route: AppRoute; children: ReactNode }) {
  const { status, session } = useAuth();
  const { t } = useLocale();
  const target = routeFor(status, session);
  if (target == null) {
    return <Loading label={t("mobileLoading")} />;
  }
  if (target !== route) {
    return <Redirect href={target} />;
  }
  return <>{children}</>;
}
