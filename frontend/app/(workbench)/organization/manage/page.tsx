"use client";

import { useLocale } from "@/components/LocaleProvider";
import { t } from "@/lib/i18n";

export default function OrganizationManagementPage() {
  const { locale } = useLocale();

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-semibold text-ink">{t(locale, "navOrganizationManagement")}</h1>
      <p className="mt-3 text-sm text-slate-600">{t(locale, "organizationManagementPlaceholder")}</p>
    </div>
  );
}
