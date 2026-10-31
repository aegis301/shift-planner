"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "@/components/LocaleProvider";
import { isUserSession } from "@/lib/membershipRouting";

export default function OrganizationManagementLayout({ children }: { children: React.ReactNode }) {
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

  return <div className="min-w-0">{children}</div>;
}
