"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AdminSectionTabs } from "@/components/AdminSectionTabs";
import { useLocale, useSession } from "@/components/LocaleProvider";
import { isUserSession } from "@/lib/membershipRouting";

const TEAM_BASE = "/organization/team";

export default function TeamManagementLayout({ children }: { children: React.ReactNode }) {
  const { locale } = useLocale();
  const { me, loading } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!isUserSession(me) || !me.capabilities.admin) {
      router.replace("/");
    }
  }, [loading, me, router]);

  if (loading || !me || !isUserSession(me) || !me.capabilities.admin) {
    return null;
  }

  return (
    <div className="min-w-0">
      <AdminSectionTabs
        locale={locale}
        tabs={[
          {
            href: TEAM_BASE,
            labelKey: "teamMembers",
            isActive: (p) =>
              (p === TEAM_BASE || p === `${TEAM_BASE}/` || p.startsWith(`${TEAM_BASE}/members`)) &&
              !p.startsWith(`${TEAM_BASE}/requests`) &&
              !p.startsWith(`${TEAM_BASE}/organization`) &&
              !p.startsWith(`${TEAM_BASE}/properties`),
          },
          {
            href: `${TEAM_BASE}/properties`,
            labelKey: "teamMemberPropertiesNav",
            isActive: (p) => p.startsWith(`${TEAM_BASE}/properties`),
          },
          {
            href: `${TEAM_BASE}/requests`,
            labelKey: "joinRequestsNav",
            isActive: (p) => p.startsWith(`${TEAM_BASE}/requests`),
          },
          {
            href: `${TEAM_BASE}/organization`,
            labelKey: "orgManagementNav",
            isActive: (p) => p.startsWith(`${TEAM_BASE}/organization`),
          },
        ]}
      />
      {children}
    </div>
  );
}
