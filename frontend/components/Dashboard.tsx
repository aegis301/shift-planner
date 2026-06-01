"use client";

import { LayoutDashboard, UserRound, UsersRound } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Card } from "@/components/Card";
import { DashboardAdminPanel } from "@/components/DashboardAdminPanel";
import { DashboardMemberPanel } from "@/components/DashboardMemberPanel";
import { DashboardPlannerPanel } from "@/components/DashboardPlannerPanel";
import { useLocale, useSession, type MeUser } from "@/components/LocaleProvider";
import { isUserSession } from "@/lib/membershipRouting";
import { ApiError, apiFetch } from "@/lib/api";
import {
  fetchAdminDashboard,
  fetchPlannerDashboard,
  fetchTeamMemberDashboard,
  type AdminDashboard,
  type PlannerDashboard,
  type TeamMemberDashboard,
} from "@/lib/dashboard";
import { t } from "@/lib/i18n";

type DashboardTab = "admin" | "planner" | "member";

type ShiftGroupOption = { id: number; code: string; name_de: string; name_en: string };

export function Dashboard() {
  const { locale } = useLocale();
  const { me, loading: sessionLoading } = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const userMe: MeUser | null = useMemo(() => (me && isUserSession(me) ? me : null), [me]);

  const tabs = useMemo(() => {
    if (!userMe) {
      return [] as DashboardTab[];
    }
    const next: DashboardTab[] = [];
    if (userMe.capabilities.admin) {
      next.push("admin");
    }
    if (userMe.capabilities.planning) {
      next.push("planner");
    }
    if (userMe.capabilities.team_member_portal) {
      next.push("member");
    }
    return next;
  }, [userMe]);

  const [activeTab, setActiveTab] = useState<DashboardTab>("admin");
  const [shiftGroupId, setShiftGroupId] = useState("");
  const [shiftGroups, setShiftGroups] = useState<ShiftGroupOption[]>([]);
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [adminData, setAdminData] = useState<AdminDashboard | null>(null);
  const [plannerData, setPlannerData] = useState<PlannerDashboard | null>(null);
  const [memberData, setMemberData] = useState<TeamMemberDashboard | null>(null);

  const scopeTabs: DashboardTab[] = ["planner", "member"];

  useEffect(() => {
    if (tabs.length === 0) {
      return;
    }
    const fromUrl = searchParams.get("tab") as DashboardTab | null;
    if (fromUrl && tabs.includes(fromUrl)) {
      setActiveTab(fromUrl);
      return;
    }
    setActiveTab(tabs[0]);
  }, [tabs, searchParams]);

  useEffect(() => {
    setShiftGroupId(searchParams.get("shiftGroup") ?? "");
  }, [searchParams]);

  useEffect(() => {
    if (!userMe) {
      return;
    }
    if (userMe.capabilities.admin && activeTab === "admin") {
      void apiFetch<ShiftGroupOption[]>("/api/v1/shift-groups?active_only=true")
        .then(setShiftGroups)
        .catch(() => setShiftGroups([]));
      return;
    }
    if (activeTab === "planner" && userMe.capabilities.planning) {
      if (userMe.capabilities.admin) {
        void apiFetch<ShiftGroupOption[]>("/api/v1/shift-groups?active_only=true")
          .then(setShiftGroups)
          .catch(() => setShiftGroups([]));
      } else {
        setShiftGroups(
          (userMe.planner_shift_groups ?? []).map((g) => ({
            id: g.id,
            code: g.code,
            name_de: g.name_de,
            name_en: g.name_en,
          }))
        );
      }
      return;
    }
    if (activeTab === "member" && userMe.shift_groups?.length) {
      setShiftGroups(
        userMe.shift_groups.map((g) => ({
          id: g.id,
          code: g.code,
          name_de: g.name_de,
          name_en: g.name_en,
        }))
      );
    }
  }, [userMe, activeTab]);

  function updateTab(tab: DashboardTab) {
    setActiveTab(tab);
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", tab);
    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
  }

  function updateShiftGroup(next: string) {
    setShiftGroupId(next);
    const params = new URLSearchParams(searchParams.toString());
    if (next) {
      params.set("shiftGroup", next);
    } else {
      params.delete("shiftGroup");
    }
    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
  }

  const loadDashboard = useCallback(async () => {
    if (!userMe || tabs.length === 0) {
      return;
    }
    setLoading(true);
    setError("");
    try {
      const yearNum = Number(year) || new Date().getFullYear();
      if (activeTab === "admin" && userMe.capabilities.admin) {
        setAdminData(
          await fetchAdminDashboard({
            year: yearNum,
            shiftGroupId: shiftGroupId || undefined,
          })
        );
      } else if (activeTab === "planner" && userMe.capabilities.planning) {
        setPlannerData(
          await fetchPlannerDashboard({
            year: yearNum,
            shiftGroupId: shiftGroupId || undefined,
          })
        );
      } else if (activeTab === "member" && userMe.capabilities.team_member_portal) {
        setMemberData(
          await fetchTeamMemberDashboard({
            year: yearNum,
            shiftGroupId: shiftGroupId || undefined,
          })
        );
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t(locale, "dashboardLoadError"));
    } finally {
      setLoading(false);
    }
  }, [activeTab, locale, shiftGroupId, tabs.length, userMe, year]);

  useEffect(() => {
    if (sessionLoading) {
      return;
    }
    void loadDashboard();
  }, [loadDashboard, sessionLoading]);

  if (sessionLoading) {
    return <p className="text-sm text-slate-500">{t(locale, "planningSessionLoading")}</p>;
  }

  if (!userMe || tabs.length === 0) {
    return (
      <Card>
        <p className="text-sm text-slate-600">{t(locale, "mvpFocus")}</p>
      </Card>
    );
  }

  const tabDefs: { id: DashboardTab; labelKey: "dashboardTabAdmin" | "dashboardTabPlanner" | "dashboardTabMember"; icon: typeof LayoutDashboard }[] = [
    { id: "admin", labelKey: "dashboardTabAdmin", icon: LayoutDashboard },
    { id: "planner", labelKey: "dashboardTabPlanner", icon: UsersRound },
    { id: "member", labelKey: "dashboardTabMember", icon: UserRound },
  ];

  const showShiftGroupSelector =
    scopeTabs.includes(activeTab) &&
    ((activeTab === "planner" && (shiftGroups.length > 1 || userMe.capabilities.admin)) ||
      (activeTab === "member" && shiftGroups.length > 1));

  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-ink">{t(locale, "dashboard")}</h1>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          {t(locale, "year")}
          <select
            className="rounded-md border border-slate-200 bg-white px-2 py-1.5 text-sm"
            value={year}
            onChange={(event) => setYear(event.target.value)}
          >
            {[0, 1, 2].map((offset) => {
              const y = new Date().getFullYear() - offset;
              return (
                <option key={y} value={String(y)}>
                  {y}
                </option>
              );
            })}
          </select>
        </label>
      </div>
      {tabs.length > 1 ? (
        <div className="flex gap-2 overflow-x-auto rounded-lg border border-slate-200 bg-white p-1 shadow-sm">
          {tabDefs
            .filter((tab) => tabs.includes(tab.id))
            .map((tab) => {
              const Icon = tab.icon;
              const active = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  className={`inline-flex h-10 shrink-0 items-center gap-2 rounded-md px-3 text-sm font-semibold ${active ? "bg-ink text-white" : "text-slate-600"}`}
                  onClick={() => updateTab(tab.id)}
                >
                  <Icon size={18} aria-hidden />
                  {t(locale, tab.labelKey)}
                </button>
              );
            })}
        </div>
      ) : null}
      {showShiftGroupSelector ? (
        <label className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
          {t(locale, "selectPlanningShiftGroup")}
          <select
            className="min-w-[12rem] rounded-md border border-slate-200 bg-white px-2 py-1.5 text-sm"
            value={shiftGroupId}
            onChange={(event) => updateShiftGroup(event.target.value)}
          >
            <option value="">{t(locale, "allShiftGroupsLabel")}</option>
            {shiftGroups.map((group) => (
              <option key={group.id} value={String(group.id)}>
                {locale === "de" ? group.name_de : group.name_en} ({group.code})
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {error ? (
        <Card>
          <p className="text-sm text-coral">{error}</p>
        </Card>
      ) : null}
      {loading ? <p className="text-sm text-slate-500">{t(locale, "planningSessionLoading")}</p> : null}
      {!loading && activeTab === "admin" && adminData ? (
        <DashboardAdminPanel locale={locale} data={adminData} shiftGroupId={shiftGroupId} />
      ) : null}
      {!loading && activeTab === "planner" && plannerData ? (
        <DashboardPlannerPanel locale={locale} data={plannerData} shiftGroupId={shiftGroupId} />
      ) : null}
      {!loading && activeTab === "member" && memberData ? (
        <DashboardMemberPanel locale={locale} data={memberData} shiftGroupId={shiftGroupId} />
      ) : null}
    </div>
  );
}
