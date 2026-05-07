"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AdminSectionTabs } from "@/components/AdminSectionTabs";
import { useLocale, useSession } from "@/components/LocaleProvider";
import { isUserSession } from "@/lib/membershipRouting";

const SHIFTS_BASE = "/organization/shifts";

export default function ShiftManagementLayout({ children }: { children: React.ReactNode }) {
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
    <div>
      <AdminSectionTabs
        locale={locale}
        tabs={[
          {
            href: `${SHIFTS_BASE}/groups`,
            labelKey: "shiftGroups",
            isActive: (p) => p === SHIFTS_BASE || p === `${SHIFTS_BASE}/` || p.startsWith(`${SHIFTS_BASE}/groups`),
          },
          {
            href: `${SHIFTS_BASE}/types`,
            labelKey: "shiftTypes",
            isActive: (p) => p.startsWith(`${SHIFTS_BASE}/types`),
          },
        ]}
      />
      {children}
    </div>
  );
}
