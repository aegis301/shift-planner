"use client";

import Link from "next/link";
import { useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { CalendarCheck, CalendarDays, Heart, House, UserRound } from "lucide-react";
import { useLocale } from "@/components/LocaleProvider";
import { NotificationSlot } from "@/components/shell/NotificationSlot";
import { ShellHeaderMenus, useAreaGuard, useShellSession } from "@/components/shell/shellSession";
import { t } from "@/lib/i18n";
import { isUserSession, membershipDefaultPath } from "@/lib/membershipRouting";

const tabs = [
  { href: "/my", key: "memberTabHome" as const, icon: House },
  { href: "/my-planning", key: "memberTabWishes" as const, icon: Heart },
  { href: "/my-planning?tab=roster", key: "memberTabDuties" as const, icon: CalendarCheck },
  { href: "/my-planning?tab=shifts", key: "memberTabSwaps" as const, icon: CalendarDays },
  { href: "/profile", key: "memberTabProfile" as const, icon: UserRound }
];

function tabActive(key: (typeof tabs)[number]["key"], pathname: string, planningTab: string | null): boolean {
  if (key === "memberTabHome") {
    return pathname === "/my";
  }
  if (key === "memberTabWishes") {
    return pathname === "/my-planning" && !planningTab;
  }
  if (key === "memberTabDuties") {
    return pathname.startsWith("/my-planning") && planningTab === "roster";
  }
  if (key === "memberTabSwaps") {
    return pathname.startsWith("/my-planning") && planningTab === "shifts";
  }
  return pathname.startsWith("/profile");
}

export function MemberShell({ children }: { children: React.ReactNode }) {
  const { locale, setLocale } = useLocale();
  const session = useShellSession(locale, setLocale);
  const guard = useAreaGuard();
  const { me, pathname } = session;
  const planningTab = useSearchParams().get("tab");

  useEffect(() => {
    if (guard.redirect && guard.me) {
      guard.router.replace(membershipDefaultPath(guard.me));
    }
  }, [guard.redirect, guard.me, guard.router]);

  const areaSwitch =
    me && isUserSession(me) && me.capabilities.planning ? { href: "/planning", label: t(locale, "workbenchArea") } : undefined;

  return (
    <div className="flex min-h-screen bg-slate-50">
      <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-r border-slate-200 bg-white md:flex">
        <p className="px-4 py-4 text-sm font-semibold text-ink">{t(locale, "memberArea")}</p>
        <nav className="flex flex-col gap-1 p-2">
          {tabs.map((item) => {
            const Icon = item.icon;
            const active = tabActive(item.key, pathname, planningTab);
            return (
              <Link
                key={item.key}
                href={item.href}
                className={`flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm font-medium ${
                  active ? "bg-ink text-white" : "text-slate-700 hover:bg-slate-100"
                }`}
              >
                <Icon aria-hidden size={18} />
                {t(locale, item.key)}
              </Link>
            );
          })}
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-slate-200 bg-white px-4">
          <p className="min-w-0 flex-1 truncate text-sm font-semibold text-ink">{t(locale, "appName")}</p>
          <NotificationSlot />
          <ShellHeaderMenus session={session} areaSwitch={areaSwitch} />
        </header>
        <main className="mx-auto w-full min-w-0 max-w-3xl flex-1 px-4 py-4 pb-24 md:pb-6">{children}</main>
        <nav className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-slate-200 bg-white md:hidden">
          {tabs.map((item) => {
            const Icon = item.icon;
            const active = tabActive(item.key, pathname, planningTab);
            return (
              <Link
                key={item.key}
                href={item.href}
                className={`flex min-h-11 flex-col items-center justify-center gap-0.5 text-[0.65rem] font-semibold ${
                  active ? "text-ink" : "text-slate-500"
                }`}
              >
                <Icon aria-hidden size={18} />
                {t(locale, item.key)}
              </Link>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
