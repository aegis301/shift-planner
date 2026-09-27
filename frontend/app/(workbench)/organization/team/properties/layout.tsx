"use client";

import { AdminSectionTabs } from "@/components/AdminSectionTabs";
import { useLocale } from "@/components/LocaleProvider";

const PROPERTIES_BASE = "/organization/team/properties";

export default function TeamPropertiesLayout({
  children
}: {
  children: React.ReactNode;
}) {
  const { locale } = useLocale();
  return (
    <div className="min-w-0">
      <AdminSectionTabs
        locale={locale}
        tabs={[
          {
            href: `${PROPERTIES_BASE}/values`,
            labelKey: "teamMemberPropertyMatrixNav",
            isActive: (pathname) =>
              pathname === PROPERTIES_BASE ||
              pathname === `${PROPERTIES_BASE}/` ||
              pathname.startsWith(`${PROPERTIES_BASE}/values`)
          },
          {
            href: `${PROPERTIES_BASE}/definitions`,
            labelKey: "teamMemberPropertyDefinitionsNav",
            isActive: (pathname) =>
              pathname.startsWith(`${PROPERTIES_BASE}/definitions`)
          }
        ]}
      />
      {children}
    </div>
  );
}
