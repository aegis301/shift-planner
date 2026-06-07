"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowDown,
  ArrowDownUp,
  ArrowUp,
  BarChart3,
  CalendarCheck,
  CalendarClock,
  Columns3,
  Download,
  Heart,
  LayoutList,
  Plus,
  RotateCw,
  Save,
  Trash2,
  X
} from "lucide-react";
import { PlanningPeriodStatusMenu } from "@/components/PlanningPeriodStatusMenu";
import { Card, Field, inputClass } from "@/components/Card";
import { MatrixEditor } from "@/components/MatrixEditor";
import { DashboardUpcomingShiftsTable } from "@/components/DashboardUpcomingShiftsTable";
import { PlanningDayIntervalBar } from "@/components/PlanningDayIntervalBar";
import { PlanningDayStatusLegend } from "@/components/PlanningDayStatusLegend";
import { useLocale, useSession, type MeUser } from "@/components/LocaleProvider";
import { isUserSession } from "@/lib/membershipRouting";
import { RosterMatrixEditor, type RosterMatrix } from "@/components/RosterMatrixEditor";
import { API_BASE_URL, ApiError, apiFetch } from "@/lib/api";
import { dataTableScrollShellClassName } from "@/lib/dataTableLayout";
import { buildMemberWorkloadRows, formatWorkloadPeriodLabel, type TeamMemberWorkloadRow } from "@/lib/rosterWorkload";
import { fetchTeamMemberDashboard, type TeamMemberDashboard } from "@/lib/dashboard";
import { teamMemberPlanningDisplayName } from "@/lib/teamMemberDisplay";
import { labelForPlanningDayStatusCode, type PlanningDayStatusDefinition } from "@/lib/planningDayStatus";
import { t, type Locale, type TranslationKey } from "@/lib/i18n";

type ShiftGroupPlanningStatus = {
  shift_group_id: number;
  status: "draft" | "preliminary" | "published";
  published_at?: string | null;
};

type PlanningPeriod = {
  id: number;
  year: number;
  month: number;
  status: string;
  published_at?: string | null;
  shift_group_statuses?: ShiftGroupPlanningStatus[];
};

type ValidationWarning = {
  code: string;
  severity: "info" | "warning" | "error";
  message: string;
  team_member_id: number | null;
  date: string | null;
  details: Record<string, unknown>;
};

type PlanningViewMode = "stacked" | "tabs";
type PlanningTab = "wishes" | "roster" | "analysis" | "shifts";
type DestructiveAction =
  | "delete-period"
  | "regenerate-roster"
  | "status-draft"
  | "status-preliminary"
  | "status-published";

type ShiftGroupOption = { id: number; code: string; name: string };

function teamMemberLabel(member: { first_name: string; last_name: string; nickname?: string | null }): string {
  return teamMemberPlanningDisplayName(member);
}

function monthLabel(period: PlanningPeriod | undefined) {
  if (!period) {
    return "";
  }
  return formatWorkloadPeriodLabel(period);
}

function periodStatusLabelKey(status: string): TranslationKey {
  if (status === "published") {
    return "periodStatusPublished";
  }
  if (status === "preliminary") {
    return "periodStatusPreliminary";
  }
  return "periodStatusDraft";
}

function duplicateMemberDayKeysFromWarnings(warnings: ValidationWarning[]): Set<string> {
  const keys = new Set<string>();
  for (const w of warnings) {
    if (w.code !== "ROSTER_MATRIX_DUPLICATE_DAY" || w.team_member_id == null || !w.date) {
      continue;
    }
    keys.add(`${w.team_member_id}:${w.date}`);
  }
  return keys;
}

function PlanningWorkspaceContent({ variant }: { variant: "planner" | "team_member" }) {
  const { locale } = useLocale();
  const { me, loading: sessionLoading } = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const currentDate = new Date();
  const [periods, setPeriods] = useState<PlanningPeriod[]>([]);
  const [periodId, setPeriodId] = useState("");
  const [newYear, setNewYear] = useState(String(currentDate.getFullYear()));
  const [newMonth, setNewMonth] = useState(String(currentDate.getMonth() + 1));
  const [rosterMatrix, setRosterMatrix] = useState<RosterMatrix | null>(null);
  const [warnings, setWarnings] = useState<ValidationWarning[]>([]);
  const [message, setMessage] = useState("");
  const [rosterReloadToken, setRosterReloadToken] = useState(0);
  const [matrixReloadToken, setMatrixReloadToken] = useState(0);
  const [viewMode, setViewMode] = useState<PlanningViewMode>("tabs");
  const [activeTab, setActiveTab] = useState<PlanningTab>("wishes");
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isExportModalOpen, setIsExportModalOpen] = useState(false);
  const [destructiveAction, setDestructiveAction] = useState<DestructiveAction | null>(null);
  const [shiftGroupId, setShiftGroupId] = useState("");
  const [shiftGroups, setShiftGroups] = useState<ShiftGroupOption[]>([]);
  const [dayStatusDefinitions, setDayStatusDefinitions] = useState<PlanningDayStatusDefinition[]>([]);
  const [groupPlanningStatus, setGroupPlanningStatus] = useState<ShiftGroupPlanningStatus | null>(null);
  const [memberShifts, setMemberShifts] = useState<TeamMemberDashboard | null>(null);
  const [memberShiftsLoading, setMemberShiftsLoading] = useState(false);

  const userMe: MeUser | null = useMemo(() => (me && isUserSession(me) ? me : null), [me]);

  useEffect(() => {
    if (!userMe) {
      return;
    }
    void apiFetch<PlanningDayStatusDefinition[]>("/api/v1/planning-day-status-definitions?active_only=true")
      .then(setDayStatusDefinitions)
      .catch(() => setDayStatusDefinitions([]));
  }, [userMe]);

  useEffect(() => {
    if (sessionLoading || !me) {
      return;
    }
    if (!isUserSession(me)) {
      router.replace("/onboarding");
    }
  }, [me, router, sessionLoading]);

  const planningUi = variant === "planner" && Boolean(userMe?.capabilities.planning);
  const adminUi = variant === "planner" && Boolean(userMe?.capabilities.admin);
  const teamMemberPortalUi = variant === "team_member" && Boolean(userMe?.capabilities.team_member_portal);
  const editableMemberId =
    teamMemberPortalUi && userMe?.team_member_id != null ? userMe.team_member_id : undefined;
  const waitingForTeamMemberSession = variant === "team_member" && (sessionLoading || !teamMemberPortalUi);
  const waitingForPlannerSession = variant === "planner" && (sessionLoading || !userMe);
  const plannerNeedsShiftGroup = variant === "planner" && userMe?.role === "planner";

  useEffect(() => {
    if (sessionLoading || !userMe) {
      return;
    }
    if (variant === "planner" && !userMe.capabilities.planning) {
      router.replace(userMe.capabilities.team_member_portal ? "/my-planning" : "/");
    }
    if (variant === "team_member" && !userMe.capabilities.team_member_portal) {
      router.replace(userMe.capabilities.planning ? "/planning" : "/");
    }
  }, [userMe, router, sessionLoading, variant]);

  const shiftGroupQuery = useMemo(
    () => (shiftGroupId ? `?shift_group_id=${encodeURIComponent(shiftGroupId)}` : ""),
    [shiftGroupId]
  );
  const exportQuery = useMemo(() => {
    const params = new URLSearchParams();
    if (shiftGroupId) {
      params.set("shift_group_id", shiftGroupId);
    }
    if (teamMemberPortalUi) {
      params.set("team_member_portal", "true");
    }
    const query = params.toString();
    return query ? `?${query}` : "";
  }, [shiftGroupId, teamMemberPortalUi]);
  const myShiftsIcsQuery = useMemo(
    () => (shiftGroupId ? `?shift_group_id=${encodeURIComponent(shiftGroupId)}` : ""),
    [shiftGroupId]
  );
  const teamMemberExportReady = Boolean(shiftGroupId);
  const exportModalOpen = isExportModalOpen && (periodId || (teamMemberPortalUi && teamMemberExportReady));

  useEffect(() => {
    setShiftGroupId(searchParams.get("shiftGroup") ?? "");
  }, [searchParams]);

  useEffect(() => {
    const fromUrl = searchParams.get("period");
    if (fromUrl) {
      setPeriodId(fromUrl);
    }
  }, [searchParams]);

  useEffect(() => {
    if (!planningUi || !userMe) {
      return;
    }
    if (userMe.capabilities.admin) {
      void apiFetch<ShiftGroupOption[]>("/api/v1/shift-groups?active_only=true").then(setShiftGroups).catch(() => setShiftGroups([]));
      return;
    }
    setShiftGroups(
      (userMe.planner_shift_groups ?? []).map((g) => ({
        id: g.id,
        code: g.code,
        name: g.name
      }))
    );
  }, [planningUi, userMe]);

  useEffect(() => {
    if (variant !== "team_member" || !userMe?.shift_groups?.length) {
      return;
    }
    setShiftGroups(
      userMe.shift_groups.map((g) => ({
        id: g.id,
        code: g.code,
        name: g.name
      }))
    );
  }, [userMe, variant]);

  const activePeriod = periods.find((period) => String(period.id) === periodId);

  useEffect(() => {
    if (!teamMemberPortalUi || !shiftGroupId) {
      setMemberShifts(null);
      return;
    }
    const year = activePeriod?.year ?? new Date().getFullYear();
    setMemberShiftsLoading(true);
    void fetchTeamMemberDashboard({ year, shiftGroupId })
      .then(setMemberShifts)
      .catch(() => setMemberShifts(null))
      .finally(() => setMemberShiftsLoading(false));
  }, [teamMemberPortalUi, shiftGroupId, activePeriod?.year]);
  const stats = useMemo(() => buildMemberWorkloadRows(rosterMatrix, warnings), [rosterMatrix, warnings]);
  const duplicateMemberDayKeys = useMemo(() => duplicateMemberDayKeysFromWarnings(warnings), [warnings]);
  const duplicateDayWarningsCount = useMemo(
    () => warnings.filter((w) => w.code === "ROSTER_MATRIX_DUPLICATE_DAY").length,
    [warnings]
  );
  const exportRequiresShiftGroup = plannerNeedsShiftGroup || teamMemberPortalUi;
  const exportBlockedByShiftGroup = exportRequiresShiftGroup && !shiftGroupId;
  const exportPublishedReady = groupPlanningStatus?.status === "published";
  const teamMemberWishesEditable =
    teamMemberPortalUi &&
    (groupPlanningStatus?.status === "draft" || groupPlanningStatus?.status === "preliminary");
  const teamMemberRosterVisible = teamMemberPortalUi
    ? groupPlanningStatus?.status === "preliminary" || groupPlanningStatus?.status === "published"
    : true;

  const loadGroupPlanningStatus = useCallback(
    async (nextPeriodId: string) => {
      if (!nextPeriodId || !shiftGroupId) {
        setGroupPlanningStatus(null);
        return;
      }
      try {
        const matrix = await apiFetch<{ shift_group_planning_status: ShiftGroupPlanningStatus | null }>(
          `/api/v1/matrix/${nextPeriodId}?shift_group_id=${encodeURIComponent(shiftGroupId)}`
        );
        setGroupPlanningStatus(matrix.shift_group_planning_status ?? null);
      } catch {
        setGroupPlanningStatus(null);
      }
    },
    [shiftGroupId]
  );

  const loadWarnings = useCallback(
    async (nextPeriodId: string) => {
      if (!nextPeriodId || !planningUi) {
        setWarnings([]);
        return;
      }
      setWarnings(await apiFetch<ValidationWarning[]>(`/api/v1/validation/${nextPeriodId}${shiftGroupQuery}`));
    },
    [planningUi, shiftGroupQuery]
  );

  const loadRosterMatrix = useCallback(
    async (nextPeriodId: string) => {
      if (!nextPeriodId) {
        setRosterMatrix(null);
        return;
      }
      try {
        const nextRoster = await apiFetch<RosterMatrix>(`/api/v1/roster-matrix/${nextPeriodId}${shiftGroupQuery}`);
        setRosterMatrix(nextRoster);
        setGroupPlanningStatus(nextRoster.shift_group_planning_status ?? null);
        if (teamMemberPortalUi) {
          setMessage("");
        }
      } catch (error) {
        if (error instanceof ApiError && (error.status === 403 || error.status === 400)) {
          setRosterMatrix(null);
          if (teamMemberPortalUi) {
            setMessage(t(locale, "rosterNotVisibleYet"));
          }
          return;
        }
        throw error;
      }
    },
    [teamMemberPortalUi, locale, shiftGroupQuery]
  );

  useEffect(() => {
    void loadGroupPlanningStatus(periodId);
  }, [periodId, shiftGroupId, loadGroupPlanningStatus]);

  function updateShiftGroup(next: string) {
    setShiftGroupId(next);
    const params = new URLSearchParams(searchParams.toString());
    if (next) {
      params.set("shiftGroup", next);
    } else {
      params.delete("shiftGroup");
    }
    const qs = params.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }

  useEffect(() => {
    if (variant !== "team_member" || !userMe?.shift_groups?.length || shiftGroupId) {
      return;
    }
    if (userMe.shift_groups.length === 1) {
      const id = String(userMe.shift_groups[0].id);
      setShiftGroupId(id);
      const params = new URLSearchParams(searchParams.toString());
      params.set("shiftGroup", id);
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    }
  }, [variant, userMe, shiftGroupId, pathname, router, searchParams]);

  useEffect(() => {
    if (
      variant !== "planner" ||
      !userMe?.capabilities.planning ||
      userMe.capabilities.admin ||
      !userMe.planner_shift_groups?.length ||
      shiftGroupId
    ) {
      return;
    }
    if (userMe.planner_shift_groups.length === 1) {
      const id = String(userMe.planner_shift_groups[0].id);
      setShiftGroupId(id);
      const params = new URLSearchParams(searchParams.toString());
      params.set("shiftGroup", id);
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    }
  }, [variant, userMe, shiftGroupId, pathname, router, searchParams]);

  const refreshPeriods = useCallback(async () => {
    const next = await apiFetch<PlanningPeriod[]>("/api/v1/planning-periods");
    setPeriods(next);
    const fromUrl = searchParams.get("period");
    if (fromUrl && next.some((row) => String(row.id) === fromUrl)) {
      setPeriodId(fromUrl);
      return;
    }
    if (!periodId && next[0]) {
      setPeriodId(String(next[0].id));
    }
  }, [periodId, searchParams]);

  useEffect(() => {
    if (waitingForTeamMemberSession || waitingForPlannerSession) {
      return;
    }
    void refreshPeriods();
  }, [refreshPeriods, waitingForTeamMemberSession, waitingForPlannerSession]);

  useEffect(() => {
    if (
      !periodId ||
      waitingForTeamMemberSession ||
      waitingForPlannerSession ||
      (teamMemberPortalUi && !shiftGroupId) ||
      (plannerNeedsShiftGroup && !shiftGroupId)
    ) {
      return;
    }
    void loadWarnings(periodId);
    void loadRosterMatrix(periodId);
  }, [
    teamMemberPortalUi,
    loadRosterMatrix,
    loadWarnings,
    periodId,
    plannerNeedsShiftGroup,
    shiftGroupId,
    waitingForTeamMemberSession,
    waitingForPlannerSession
  ]);

  async function createAndLoadPeriod(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const period = await apiFetch<PlanningPeriod>("/api/v1/planning-periods", {
      method: "POST",
      body: JSON.stringify({ year: Number(newYear), month: Number(newMonth) })
    });
    const nextPeriodId = String(period.id);
    const nextPeriods = await apiFetch<PlanningPeriod[]>("/api/v1/planning-periods");
    setPeriods(nextPeriods);
    setPeriodId(nextPeriodId);
    setActiveTab("wishes");
    setIsCreateModalOpen(false);
    setMessage(`${t(locale, "saved")}: ${monthLabel(period)}`);
  }

  async function confirmDestructiveAction() {
    if (!periodId || !destructiveAction) {
      return;
    }
    const statusQuery = shiftGroupQuery;
    const groupName = shiftGroups.find((g) => String(g.id) === shiftGroupId)?.name;
    if (destructiveAction === "status-published") {
      await apiFetch<ShiftGroupPlanningStatus>(`/api/v1/planning-periods/${periodId}/publish${statusQuery}`, {
        method: "POST"
      });
      await refreshPeriods();
      await loadGroupPlanningStatus(periodId);
      await loadRosterMatrix(periodId);
      setMessage(
        groupName ? `${t(locale, "periodPublishedGroup")} (${groupName})` : t(locale, "periodPublishedGroup")
      );
    } else if (destructiveAction === "status-preliminary") {
      await apiFetch<ShiftGroupPlanningStatus>(`/api/v1/planning-periods/${periodId}/preliminary${statusQuery}`, {
        method: "POST"
      });
      await refreshPeriods();
      await loadGroupPlanningStatus(periodId);
      await loadRosterMatrix(periodId);
      setMessage(
        groupName
          ? `${t(locale, "periodSetPreliminaryGroup")} (${groupName})`
          : t(locale, "periodSetPreliminaryGroup")
      );
    } else if (destructiveAction === "status-draft") {
      await apiFetch<ShiftGroupPlanningStatus>(`/api/v1/planning-periods/${periodId}/draft${statusQuery}`, {
        method: "POST"
      });
      await refreshPeriods();
      await loadGroupPlanningStatus(periodId);
      await loadRosterMatrix(periodId);
      setMessage(
        groupName ? `${t(locale, "periodSetDraftGroup")} (${groupName})` : t(locale, "periodSetDraftGroup")
      );
    } else if (destructiveAction === "regenerate-roster") {
      await apiFetch<RosterMatrix>(`/api/v1/planning-periods/${periodId}/regenerate-roster${statusQuery}`, {
        method: "POST"
      });
      setRosterReloadToken((value) => value + 1);
      await loadRosterMatrix(periodId);
      await loadWarnings(periodId);
      setMessage(`${t(locale, "saved")}: ${t(locale, "regenerateRoster")}`);
    } else {
      await apiFetch(`/api/v1/planning-periods/${periodId}`, { method: "DELETE" });
      const nextPeriods = await apiFetch<PlanningPeriod[]>("/api/v1/planning-periods");
      setPeriods(nextPeriods);
      setPeriodId(nextPeriods[0] ? String(nextPeriods[0].id) : "");
      setRosterMatrix(null);
      setWarnings([]);
      setActiveTab("wishes");
      setMessage(t(locale, "deletePlanningPeriod"));
    }
    setDestructiveAction(null);
  }

  const handleRosterChange = useCallback(async (nextMatrix: RosterMatrix) => {
    setRosterMatrix(nextMatrix);
    setGroupPlanningStatus(nextMatrix.shift_group_planning_status ?? null);
    await loadWarnings(String(nextMatrix.planning_period.id));
  }, [loadWarnings]);

  const handleWishesChanged = useCallback(async () => {
    if (periodId) {
      await loadWarnings(periodId);
      setRosterReloadToken((value) => value + 1);
      await loadRosterMatrix(periodId);
    }
  }, [loadRosterMatrix, loadWarnings, periodId]);

  const handleDayIntervalApplied = useCallback(async () => {
    setMatrixReloadToken((value) => value + 1);
    await handleWishesChanged();
  }, [handleWishesChanged]);

  const wishesSection = periodId ? (
    <section className="grid min-w-0 gap-3">
      <div>
        <h2 className="text-xl font-semibold text-ink">{t(locale, "wishesSection")}</h2>
        <p className="mt-1 text-sm text-slate-600">{t(locale, "matrixHelp")}</p>
        {teamMemberPortalUi && teamMemberWishesEditable ? (
          <p className="mt-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 ring-1 ring-slate-100">
            {groupPlanningStatus?.status === "preliminary"
              ? t(locale, "myPlanningWishesFeedbackHintPreliminary")
              : t(locale, "myPlanningWishesFeedbackHintDraft")}
          </p>
        ) : null}
      </div>
      {waitingForPlannerSession ? null : (teamMemberPortalUi || plannerNeedsShiftGroup) && !shiftGroupId ? (
        <p className="text-sm text-amber-800">{t(locale, "selectPlanningShiftGroup")}</p>
      ) : (
        <MatrixEditor
          periodId={periodId}
          compact
          reloadToken={matrixReloadToken}
          shiftGroupId={shiftGroupId || undefined}
          editableMemberId={teamMemberWishesEditable ? editableMemberId : undefined}
          teamMemberPortal={teamMemberPortalUi}
          readOnly={teamMemberPortalUi && !teamMemberWishesEditable}
          dayFeedbackAlwaysVisible={Boolean(teamMemberPortalUi && teamMemberWishesEditable)}
          onChanged={handleWishesChanged}
        />
      )}
    </section>
  ) : null;

  const rosterSection = periodId ? (
    <section className="grid min-w-0 gap-3">
      <div>
        <h2 className="text-xl font-semibold text-ink">{t(locale, "rosterSection")}</h2>
        <p className="mt-1 text-sm text-slate-600">{t(locale, "finalRosterHelp")}</p>
        {teamMemberPortalUi && groupPlanningStatus?.status === "preliminary" && teamMemberWishesEditable ? (
          <p className="mt-2 rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-950 ring-1 ring-sky-100">
            {t(locale, "myPlanningRosterFeedbackRedirect")}
          </p>
        ) : null}
      </div>
      {duplicateDayWarningsCount > 0 ? (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm font-medium text-amber-950 ring-1 ring-amber-200">
          {t(locale, "rosterDuplicateDayPlanningHint", { count: String(duplicateDayWarningsCount) })}
        </p>
      ) : null}
      {waitingForPlannerSession ? null : (teamMemberPortalUi || plannerNeedsShiftGroup) && !shiftGroupId ? (
        <p className="text-sm text-amber-800">{t(locale, "selectPlanningShiftGroup")}</p>
      ) : teamMemberPortalUi && !teamMemberRosterVisible ? (
        <p className="text-sm text-slate-600">{t(locale, "rosterNotVisibleYet")}</p>
      ) : (
        <RosterMatrixEditor
          periodId={periodId}
          compact
          readOnly={Boolean(teamMemberPortalUi)}
          reloadToken={rosterReloadToken}
          shiftGroupId={shiftGroupId || undefined}
          duplicateMemberDayKeys={duplicateMemberDayKeys}
          validationWarnings={warnings}
          onMatrixChange={handleRosterChange}
          highlightTeamMemberId={
            teamMemberPortalUi && userMe?.team_member_id != null ? userMe.team_member_id : undefined
          }
        />
      )}
    </section>
  ) : null;

  const analysisSection = !teamMemberPortalUi ? (
    <section className="grid gap-4">
      <div>
        <h2 className="text-xl font-semibold text-ink">{t(locale, "analysisSection")}</h2>
        <p className="mt-1 text-sm text-slate-600">{t(locale, "analysisHelp")}</p>
      </div>
      <WorkloadStats rows={stats.rows} unassigned={stats.unassigned} />
    </section>
  ) : null;

  const shiftsSection = teamMemberPortalUi ? (
    <section className="grid gap-4">
      <div>
        <h2 className="text-xl font-semibold text-ink">{t(locale, "myPlanningShiftsSection")}</h2>
        <p className="mt-1 text-sm text-slate-600">{t(locale, "myPlanningShiftsSectionHelp")}</p>
      </div>
      {!shiftGroupId ? (
        <p className="text-sm text-amber-800">{t(locale, "selectPlanningShiftGroup")}</p>
      ) : memberShiftsLoading ? (
        <p className="text-sm text-slate-600">{t(locale, "saving")}</p>
      ) : memberShifts ? (
        <div className="grid gap-5">
          <div className="grid gap-2">
            <h3 className="text-base font-semibold text-ink">{t(locale, "dashboardUpcomingShifts")}</h3>
            <p className="text-sm text-slate-600">{t(locale, "dashboardUpcomingShiftsHint")}</p>
            <DashboardUpcomingShiftsTable locale={locale} slots={memberShifts.upcoming_slots} showIcsExport />
          </div>
          <div className="grid gap-2">
            <h3 className="text-base font-semibold text-ink">{t(locale, "dashboardPastShifts")}</h3>
            <p className="text-sm text-slate-600">{t(locale, "dashboardPastShiftsHint")}</p>
            <DashboardUpcomingShiftsTable locale={locale} slots={memberShifts.past_slots} emptyLabelKey="dashboardPastShiftsEmpty" showIcsExport />
          </div>
        </div>
      ) : (
        <p className="text-sm text-slate-500">{t(locale, "noData")}</p>
      )}
    </section>
  ) : null;

  const planningConflictSummary =
    periodId && planningUi && !waitingForPlannerSession ? (
      <InlineValidation rosterMatrix={rosterMatrix} warnings={warnings} dayStatusDefinitions={dayStatusDefinitions} />
    ) : null;

  return (
    <div className="grid min-w-0 gap-6">
      <Card>
        <div className="grid gap-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h1 className="text-2xl font-semibold text-ink">{teamMemberPortalUi ? t(locale, "myPlanning") : t(locale, "planning")}</h1>
            <div className="flex flex-wrap items-center gap-2">
              <Field label={t(locale, "planningPeriod")}>
                <select className={`${inputClass} h-10 min-w-40`} value={periodId} onChange={(event) => setPeriodId(event.target.value)}>
                  <option value="">{t(locale, "emptyValue")}</option>
                  {periods.map((period) => (
                    <option key={period.id} value={period.id}>
                      {monthLabel(period)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={t(locale, "selectPlanningShiftGroup")}>
                <select
                  className={`${inputClass} h-10 min-w-44`}
                  value={shiftGroupId}
                  onChange={(event) => updateShiftGroup(event.target.value)}
                  title={t(locale, "planningShiftGroupHelp")}
                >
                  {adminUi ? <option value="">{t(locale, "allShiftGroupsLabel")}</option> : null}
                  {shiftGroups.map((group) => (
                    <option key={group.id} value={String(group.id)}>
                      {group.name} ({group.code})
                    </option>
                  ))}
                </select>
              </Field>
              {planningUi ? (
                <>
                  {adminUi ? (
                    <button
                      aria-label={t(locale, "createPeriod")}
                      className="mt-5 inline-flex h-10 w-10 items-center justify-center rounded-lg bg-mint text-ink ring-1 ring-mint/60"
                      onClick={() => setIsCreateModalOpen(true)}
                      title={t(locale, "createPeriod")}
                      type="button"
                    >
                      <Plus size={19} />
                    </button>
                  ) : null}
                  <button
                    aria-label={t(locale, "exports")}
                    className="mt-5 inline-flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-700 shadow-sm disabled:cursor-not-allowed disabled:opacity-40"
                    disabled={!periodId}
                    onClick={() => setIsExportModalOpen(true)}
                    title={t(locale, "exports")}
                    type="button"
                  >
                    <Download size={18} />
                  </button>
                  <Field label={t(locale, "planningPeriodStatus")}>
                    <PlanningPeriodStatusMenu
                      disabled={!periodId || !shiftGroupId}
                      disabledReason="planningPeriodStatusSelectGroup"
                      locale={locale}
                      onSelectAction={setDestructiveAction}
                      status={groupPlanningStatus?.status ?? null}
                    />
                  </Field>
                  <button
                    aria-label={t(locale, "regenerateRoster")}
                    className="mt-5 inline-flex h-10 w-10 items-center justify-center rounded-lg border border-amber-200 bg-amber-50 text-amber-800 shadow-sm disabled:cursor-not-allowed disabled:opacity-40"
                    disabled={!periodId}
                    onClick={() => setDestructiveAction("regenerate-roster")}
                    title={t(locale, "regenerateRoster")}
                    type="button"
                  >
                    <RotateCw size={18} />
                  </button>
                  {adminUi ? (
                    <button
                      aria-label={t(locale, "deletePlanningPeriod")}
                      className="mt-5 inline-flex h-10 w-10 items-center justify-center rounded-lg border border-rose-200 bg-rose-50 text-rose-700 shadow-sm disabled:cursor-not-allowed disabled:opacity-40"
                      disabled={!periodId}
                      onClick={() => setDestructiveAction("delete-period")}
                      title={t(locale, "deletePlanningPeriod")}
                      type="button"
                    >
                      <Trash2 size={18} />
                    </button>
                  ) : null}
                  <div className="mt-5 inline-flex rounded-lg border border-slate-200 bg-white p-1 shadow-sm">
                    <button
                      aria-label={t(locale, "stackedView")}
                      className={`inline-flex h-8 w-9 items-center justify-center rounded-md text-sm font-semibold ${viewMode === "stacked" ? "bg-ink text-white" : "text-slate-600"}`}
                      onClick={() => setViewMode("stacked")}
                      title={t(locale, "stackedView")}
                      type="button"
                    >
                      <LayoutList size={17} />
                    </button>
                    <button
                      aria-label={t(locale, "tabbedView")}
                      className={`inline-flex h-8 w-9 items-center justify-center rounded-md text-sm font-semibold ${viewMode === "tabs" ? "bg-ink text-white" : "text-slate-600"}`}
                      onClick={() => setViewMode("tabs")}
                      title={t(locale, "tabbedView")}
                      type="button"
                    >
                      <Columns3 size={17} />
                    </button>
                  </div>
                </>
              ) : null}
              {teamMemberPortalUi ? (
                <button
                  aria-label={t(locale, "exports")}
                  className="mt-5 inline-flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-700 shadow-sm disabled:cursor-not-allowed disabled:opacity-40"
                  disabled={!teamMemberExportReady}
                  onClick={() => setIsExportModalOpen(true)}
                  title={t(locale, "exports")}
                  type="button"
                >
                  <Download size={18} />
                </button>
              ) : null}
            </div>
          </div>
          <div className="flex flex-wrap gap-3 text-sm">
            {activePeriod ? (
              <div className="flex flex-wrap items-center gap-2 text-slate-600">
                <p>
                  {t(locale, "selectedMonth")}: {monthLabel(activePeriod)}
                </p>
                {groupPlanningStatus ? (
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ${
                      groupPlanningStatus.status === "published"
                        ? "bg-emerald-50 text-emerald-900 ring-emerald-200"
                        : groupPlanningStatus.status === "preliminary"
                          ? "bg-sky-50 text-sky-900 ring-sky-200"
                          : "bg-amber-50 text-amber-900 ring-amber-200"
                    }`}
                  >
                    {t(locale, periodStatusLabelKey(groupPlanningStatus.status))}
                  </span>
                ) : shiftGroupId ? null : (
                  <span className="text-xs text-slate-500">{t(locale, "planningPeriodStatusSelectGroup")}</span>
                )}
              </div>
            ) : null}
            {message ? <p className="text-emerald-700">{message}</p> : null}
          </div>
          {teamMemberPortalUi && groupPlanningStatus?.status === "preliminary" ? (
            <div className="rounded-lg border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-950 ring-1 ring-sky-100">
              <p className="font-semibold">{t(locale, "myPlanningPreliminaryBannerTitle")}</p>
              <p className="mt-1 text-sky-900">{t(locale, "myPlanningPreliminaryBannerBody")}</p>
            </div>
          ) : null}
          <PlanningDayStatusLegend locale={locale} definitions={dayStatusDefinitions} />
          {periodId && shiftGroupId ? (
            <PlanningDayIntervalBar
              periodId={periodId}
              shiftGroupId={shiftGroupId}
              readOnly={teamMemberPortalUi && !teamMemberWishesEditable}
              teamMemberPortal={teamMemberPortalUi}
              editableMemberId={editableMemberId}
              dayStatusDefinitions={dayStatusDefinitions}
              onApplied={handleDayIntervalApplied}
            />
          ) : null}
        </div>
      </Card>

      {isCreateModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 px-4 py-6 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="create-period-title">
          <div className="w-full max-w-md rounded-xl bg-white p-5 shadow-soft ring-1 ring-slate-200">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 id="create-period-title" className="text-lg font-semibold text-ink">{t(locale, "createPeriod")}</h2>
              <button
                aria-label={t(locale, "close")}
                className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600"
                onClick={() => setIsCreateModalOpen(false)}
                type="button"
              >
                <X size={17} />
              </button>
            </div>
            <form className="grid gap-4 sm:grid-cols-2" onSubmit={createAndLoadPeriod}>
              <Field label={t(locale, "year")}>
                <input className={inputClass} value={newYear} onChange={(event) => setNewYear(event.target.value)} type="number" min="2020" max="2100" />
              </Field>
              <Field label={t(locale, "month")}>
                <input className={inputClass} value={newMonth} onChange={(event) => setNewMonth(event.target.value)} type="number" min="1" max="12" />
              </Field>
              <button className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-mint px-4 text-sm font-semibold text-ink sm:col-span-2">
                <Save size={17} />
                {t(locale, "createAndLoadPeriod")}
              </button>
            </form>
          </div>
        </div>
      ) : null}

      {exportModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 px-4 py-6 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="export-title">
          <div className="w-full max-w-md rounded-xl bg-white p-5 shadow-soft ring-1 ring-slate-200">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 id="export-title" className="text-lg font-semibold text-ink">{t(locale, "exports")}</h2>
              <button
                aria-label={t(locale, "close")}
                className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600"
                onClick={() => setIsExportModalOpen(false)}
                type="button"
              >
                <X size={17} />
              </button>
            </div>
            <div className="grid gap-3">
              {teamMemberPortalUi ? (
                <>
                  <a
                    className={`inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 ${
                      exportBlockedByShiftGroup ? "pointer-events-none opacity-40" : ""
                    }`}
                    href={`${API_BASE_URL}/api/v1/exports/my-shifts.ics${myShiftsIcsQuery}`}
                  >
                    <Download size={17} />
                    {t(locale, "myShiftsIcsExport")}
                  </a>
                  <a
                    className={`inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 ${
                      exportBlockedByShiftGroup || !periodId || !teamMemberRosterVisible ? "pointer-events-none opacity-40" : ""
                    }`}
                    href={`${API_BASE_URL}/api/v1/exports/my-shifts/${periodId}.ics${myShiftsIcsQuery}`}
                  >
                    <Download size={17} />
                    {t(locale, "myShiftsMonthIcsExport")}
                  </a>
                </>
              ) : null}
              {planningUi && periodId ? (
                <>
                  <a
                    className={`inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 ${
                      exportBlockedByShiftGroup ? "pointer-events-none opacity-40" : ""
                    }`}
                    href={`${API_BASE_URL}/api/v1/exports/matrix/${periodId}.csv${shiftGroupQuery}`}
                  >
                    <Download size={17} />
                    {t(locale, "wishesCsvExport")}
                  </a>
                  <a
                    className={`inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 ${
                      exportBlockedByShiftGroup ? "pointer-events-none opacity-40" : ""
                    }`}
                    href={`${API_BASE_URL}/api/v1/exports/roster-matrix/${periodId}.csv${shiftGroupQuery}`}
                  >
                    <Download size={17} />
                    {t(locale, "rosterCsvExport")}
                  </a>
                </>
              ) : null}
              {periodId ? (
                <>
                  <a
                    className={`inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 ${
                      exportBlockedByShiftGroup || !exportPublishedReady ? "pointer-events-none opacity-40" : ""
                    }`}
                    href={`${API_BASE_URL}/api/v1/exports/roster-matrix/${periodId}.xlsx${exportQuery}`}
                  >
                    <Download size={17} />
                    {t(locale, "rosterXlsxExport")}
                  </a>
                  <a
                    className={`inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 ${
                      exportBlockedByShiftGroup || !exportPublishedReady ? "pointer-events-none opacity-40" : ""
                    }`}
                    href={`${API_BASE_URL}/api/v1/exports/roster-matrix/${periodId}.pdf${exportQuery}`}
                  >
                    <Download size={17} />
                    {t(locale, "rosterPdfExport")}
                  </a>
                </>
              ) : null}
              {teamMemberPortalUi && periodId && !teamMemberRosterVisible ? (
                <p className="text-xs text-slate-500">{t(locale, "exportRosterVisibleHint")}</p>
              ) : null}
              {periodId && !exportPublishedReady ? (
                <p className="text-xs text-slate-500">{t(locale, "exportPublishedOnlyHint")}</p>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

      {destructiveAction ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 px-4 py-6 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="destructive-title">
          <div className="w-full max-w-md rounded-xl bg-white p-5 shadow-soft ring-1 ring-rose-200">
            <div className="mb-4 flex items-start justify-between gap-3">
              <div className="flex gap-3">
                <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-rose-50 text-rose-700 ring-1 ring-rose-200">
                  <AlertTriangle size={19} />
                </span>
                <div>
                  <h2 id="destructive-title" className="text-lg font-semibold text-ink">
                    {destructiveAction === "delete-period"
                      ? t(locale, "deletePlanningPeriod")
                      : destructiveAction === "status-published"
                        ? t(locale, "publishPlanningPeriod")
                        : destructiveAction === "status-preliminary"
                          ? t(locale, "setPlanningPeriodPreliminary")
                          : destructiveAction === "status-draft"
                            ? t(locale, "setPlanningPeriodDraft")
                        : t(locale, "regenerateRoster")}
                  </h2>
                  <p className="mt-1 text-sm text-slate-600">{t(locale, "destructiveAction")}</p>
                </div>
              </div>
              <button
                aria-label={t(locale, "close")}
                className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-600"
                onClick={() => setDestructiveAction(null)}
                type="button"
              >
                <X size={17} />
              </button>
            </div>
            <p
              className={`rounded-lg p-3 text-sm ring-1 ${
                destructiveAction === "status-published" || destructiveAction === "status-preliminary" || destructiveAction === "status-draft"
                  ? "bg-emerald-50 text-emerald-950 ring-emerald-100"
                  : "bg-rose-50 text-rose-900 ring-rose-100"
              }`}
            >
              {destructiveAction === "delete-period"
                ? t(locale, "deletePlanningPeriodWarning")
                : destructiveAction === "status-published"
                  ? t(locale, "publishPlanningPeriodConfirm")
                  : destructiveAction === "status-preliminary"
                    ? t(locale, "setPlanningPeriodPreliminaryConfirm")
                    : destructiveAction === "status-draft"
                      ? t(locale, "setPlanningPeriodDraftConfirm")
                  : t(locale, "regenerateRosterWarning")}
            </p>
            <div className="mt-5 flex flex-wrap justify-end gap-2">
              <button
                className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700"
                onClick={() => setDestructiveAction(null)}
                type="button"
              >
                {t(locale, "close")}
              </button>
              <button
                className={`inline-flex h-10 items-center justify-center gap-2 rounded-lg px-4 text-sm font-semibold text-white ${
                  destructiveAction === "status-published" || destructiveAction === "status-preliminary" || destructiveAction === "status-draft"
                    ? "bg-emerald-700"
                    : "bg-rose-700"
                }`}
                onClick={confirmDestructiveAction}
                type="button"
              >
                {destructiveAction === "delete-period" ? (
                  <Trash2 size={16} />
                ) : destructiveAction === "status-published" || destructiveAction === "status-preliminary" || destructiveAction === "status-draft" ? (
                  <CalendarCheck size={16} />
                ) : (
                  <RotateCw size={16} />
                )}
                {t(locale, "confirm")}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {waitingForTeamMemberSession || waitingForPlannerSession ? (
        <Card>
          <p className="text-sm text-slate-600">
            {waitingForPlannerSession ? t(locale, "planningSessionLoading") : t(locale, "saving")}
          </p>
        </Card>
      ) : periodId ? (
        viewMode === "stacked" ? (
          <>
            {wishesSection}
            {planningConflictSummary}
            {rosterSection}
            {!teamMemberPortalUi ? analysisSection : null}
          </>
        ) : (
          <div className="grid gap-5">
            <div className="flex gap-2 overflow-x-auto rounded-lg border border-slate-200 bg-white p-1 shadow-sm">
              {(teamMemberPortalUi
                ? ([
                    ["wishes", "wishesSection", Heart],
                    ["roster", "rosterSection", CalendarCheck],
                    ["shifts", "myPlanningShiftsSection", CalendarClock]
                  ] as const)
                : ([
                    ["wishes", "wishesSection", Heart],
                    ["roster", "rosterSection", CalendarCheck],
                    ["analysis", "analysisSection", BarChart3]
                  ] as const)
              ).map(([tab, label, Icon]) => (
                <button
                  key={tab}
                  aria-label={t(locale, label)}
                  className={`inline-flex h-10 w-12 shrink-0 items-center justify-center rounded-md text-sm font-semibold ${activeTab === tab ? "bg-ink text-white" : "text-slate-600"}`}
                  onClick={() => setActiveTab(tab)}
                  title={t(locale, label)}
                  type="button"
                >
                  <Icon size={19} />
                </button>
              ))}
            </div>
            {activeTab === "wishes" ? wishesSection : null}
            {activeTab === "roster" ? (
              <>
                {planningConflictSummary}
                {rosterSection}
              </>
            ) : null}
            {activeTab === "analysis" ? (
              <>
                {planningConflictSummary}
                {analysisSection}
              </>
            ) : null}
            {activeTab === "shifts" ? shiftsSection : null}
          </div>
        )
      ) : (
        <Card>
          <p className="text-sm text-slate-500">{t(locale, "noPlanningPeriodSelected")}</p>
        </Card>
      )}
    </div>
  );
}

function summarizeRosterSlot(slot: RosterMatrix["slots"][number], locale: Locale): string {
  const name = slot.template_name;
  const base = name || slot.label || slot.template_code || `#${slot.id}`;
  return slot.variant_label ? `${base} (${slot.variant_label})` : base;
}

function shiftVariantLabelFromMatrix(matrix: RosterMatrix, variantId: number, locale: Locale): string {
  const slot = matrix.slots.find((row) => row.shift_variant_id === variantId);
  if (slot) {
    return summarizeRosterSlot(slot, locale);
  }
  return `#${variantId}`;
}

const PROPERTY_REQ_OP_KEYS: Record<string, TranslationKey> = {
  eq: "propertyReqOpEq",
  neq: "propertyReqOpNeq",
  gte: "propertyReqOpGte",
  lte: "propertyReqOpLte",
  before: "propertyReqOpBefore",
  after: "propertyReqOpAfter",
  contains: "propertyReqOpContains",
  one_of: "propertyReqOpOneOf",
  contains_all: "propertyReqOpContainsAll",
  contains_any: "propertyReqOpContainsAny",
  eq_set: "propertyReqOpEqSet"
};

function formatPropertyRequirementValue(value: unknown, locale: Locale): string {
  if (value === null || value === undefined) {
    return t(locale, "emptyValue");
  }
  if (Array.isArray(value)) {
    return value.map((item) => String(item)).join(", ");
  }
  return String(value);
}

function teamMemberPropertyViolationDetailText(warning: ValidationWarning, locale: Locale): string {
  const raw = warning.details?.violations;
  if (!Array.isArray(raw) || !raw.length) {
    return t(locale, "validationDetailConstraintTeamMemberProperties");
  }
  const lines: string[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const row = item as Record<string, unknown>;
    const property = String(row.property_name ?? "—");
    const op = typeof row.op === "string" ? row.op : "";
    const opKey = PROPERTY_REQ_OP_KEYS[op];
    const opLabel = opKey ? t(locale, opKey) : op;
    const required = formatPropertyRequirementValue(row.required_value, locale);
    if (row.missing === true) {
      lines.push(t(locale, "validationDetailPropertyViolationMissing", { property, op: opLabel, required }));
    } else {
      const actual = formatPropertyRequirementValue(row.actual_value, locale);
      lines.push(t(locale, "validationDetailPropertyViolationMismatch", { property, op: opLabel, required, actual }));
    }
  }
  if (!lines.length) {
    return t(locale, "validationDetailConstraintTeamMemberProperties");
  }
  return lines.join(" · ");
}

function shiftTypeLabelForMaxAssignmentsWarning(warning: ValidationWarning, matrix: RosterMatrix, locale: Locale): string {
  const templateId = warning.details?.shift_template_id;
  if (typeof templateId === "number") {
    const summary = matrix.shift_templates?.find((row) => row.id === templateId);
    if (summary) {
      const name = summary.name;
      const label = name.trim() || summary.code;
      return `${label} (${summary.code})`;
    }
  }
  const slotIds = warning.details?.violating_roster_slot_ids as number[] | undefined;
  const firstSlotId = Array.isArray(slotIds) && slotIds.length ? slotIds[0] : undefined;
  const slot =
    typeof firstSlotId === "number" ? matrix.slots.find((row) => row.id === firstSlotId) : undefined;
  if (slot) {
    return summarizeRosterSlot(slot, locale);
  }
  return "—";
}

function validationWarningDetailText(
  warning: ValidationWarning,
  matrix: RosterMatrix | null,
  locale: Locale,
  dayStatusDefinitions: PlanningDayStatusDefinition[]
): string | null {
  if (!matrix) {
    return null;
  }
  if (warning.code === "ROSTER_MATRIX_DUPLICATE_DAY") {
    const ids = (warning.details?.roster_slot_ids as number[] | undefined) ?? [];
    const labels = ids
      .map((id) => matrix.slots.find((slot) => slot.id === id))
      .filter((slot): slot is NonNullable<typeof slot> => Boolean(slot))
      .map((slot) => summarizeRosterSlot(slot, locale));
    const count = (warning.details?.count as number | undefined) ?? labels.length;
    const slotsText = labels.length ? labels.join(" · ") : ids.map(String).join(", ");
    if (!slotsText) {
      return null;
    }
    return t(locale, "validationDetailDuplicateDay", { count: String(count), slots: slotsText });
  }
  if (warning.code === "ROSTER_MATRIX_UNAVAILABLE_CONFLICT") {
    const st = String(warning.details?.unavailable_status ?? "");
    const wishLabel = labelForPlanningDayStatusCode(st, dayStatusDefinitions, locale);
    const slotId = warning.details?.roster_slot_id as number | undefined;
    const slot = slotId != null ? matrix.slots.find((s) => s.id === slotId) : undefined;
    const slotLabel = slot ? summarizeRosterSlot(slot, locale) : "—";
    return t(locale, "validationDetailUnavailable", { wish: wishLabel, slot: slotLabel });
  }
  if (warning.code === "ROSTER_TEMPLATE_NO_GO_CONFLICT") {
    const slotId = warning.details?.roster_slot_id as number | undefined;
    const slot = slotId != null ? matrix.slots.find((s) => s.id === slotId) : undefined;
    const slotLabel = slot ? summarizeRosterSlot(slot, locale) : "—";
    return t(locale, "validationDetailNoGo", { slot: slotLabel });
  }
  if (warning.code === "ROSTER_CONSTRAINT_SAME_DAY") {
    const ids = (warning.details?.conflicting_roster_slot_ids as number[] | undefined) ?? [];
    const labels = ids
      .map((id) => matrix.slots.find((slot) => slot.id === id))
      .filter((slot): slot is NonNullable<typeof slot> => Boolean(slot))
      .map((slot) => summarizeRosterSlot(slot, locale));
    const slotsText = labels.length ? labels.join(" · ") : ids.map(String).join(", ");
    return t(locale, "validationDetailConstraintSameDay", { slots: slotsText || "—" });
  }
  if (warning.code === "ROSTER_CONSTRAINT_MIN_REST_HOURS") {
    const slotId = warning.details?.related_roster_slot_id as number | undefined;
    const slot = slotId != null ? matrix.slots.find((s) => s.id === slotId) : undefined;
    const slotLabel = slot ? summarizeRosterSlot(slot, locale) : "—";
    const required = String(warning.details?.required_rest_hours ?? "—");
    const actual = String(warning.details?.actual_rest_hours ?? "—");
    return t(locale, "validationDetailConstraintRestHours", { required, actual, slot: slotLabel });
  }
  if (warning.code === "ROSTER_CONSTRAINT_CROSS_DAY_UNAVAILABLE") {
    return t(locale, "validationDetailConstraintCrossDayUnavailable", {
      endDay: String(warning.details?.end_day ?? warning.date ?? "—")
    });
  }
  if (warning.code === "ROSTER_CONSTRAINT_MAX_ASSIGNMENTS_PER_MONTH") {
    const max = String(warning.details?.max_assignments_per_month ?? "—");
    const actual = String(warning.details?.actual_assignments_per_month ?? "—");
    const shift = shiftTypeLabelForMaxAssignmentsWarning(warning, matrix, locale);
    return t(locale, "validationDetailConstraintMaxAssignmentsPerMonth", { max, actual, shift });
  }
  if (warning.code === "ROSTER_CONSTRAINT_COUPLED_SHIFT_REQUIRED") {
    const pid = warning.details?.paired_shift_variant_id as number | undefined;
    const partner = typeof pid === "number" ? shiftVariantLabelFromMatrix(matrix, pid, locale) : "—";
    const partnerDate = String(warning.details?.partner_date ?? "—");
    const sid = warning.details?.shift_variant_id as number | undefined;
    const source = typeof sid === "number" ? shiftVariantLabelFromMatrix(matrix, sid, locale) : "—";
    return t(locale, "validationDetailConstraintCoupledShift", { source, partner, partnerDate });
  }
  if (warning.code === "ROSTER_CONSTRAINT_TEAM_MEMBER_PROPERTIES") {
    return teamMemberPropertyViolationDetailText(warning, locale);
  }
  if (warning.code === "MEMBER_PATTERN_AVOID_TIME_WINDOW") {
    return t(locale, "validationDetailMemberPatternAvoidTimeWindow", {
      label: String(warning.details?.pattern_label ?? "—"),
      windowStart: String(warning.details?.window_start ?? "—"),
      windowEnd: String(warning.details?.window_end ?? "—"),
      weekday: String(warning.details?.weekday ?? "—"),
      severity: String(warning.details?.constraint_severity ?? warning.severity)
    });
  }
  if (warning.code === "MEMBER_PATTERN_WEEK_PARITY") {
    return t(locale, "validationDetailMemberPatternWeekParity", {
      label: String(warning.details?.pattern_label ?? "—"),
      requiredParity: String(warning.details?.required_parity ?? "—"),
      isoWeek: String(warning.details?.iso_week ?? "—"),
      severity: String(warning.details?.constraint_severity ?? warning.severity)
    });
  }
  if (warning.code === "ROSTER_CONSECUTIVE_WEEKENDS") {
    const raw = warning.details?.pairs;
    if (!Array.isArray(raw) || raw.length === 0) {
      return null;
    }
    const parts: string[] = [];
    for (const item of raw) {
      if (item && typeof item === "object") {
        const row = item as { first_weekend_saturday?: string; second_weekend_saturday?: string };
        if (row.first_weekend_saturday && row.second_weekend_saturday) {
          parts.push(`${row.first_weekend_saturday} → ${row.second_weekend_saturday}`);
        }
      }
    }
    if (!parts.length) {
      return null;
    }
    return t(locale, "validationDetailConsecutiveWeekends", { ranges: parts.join("; ") });
  }
  return null;
}

function rosterWarningSeverityRank(severity: ValidationWarning["severity"]): number {
  if (severity === "error") {
    return 2;
  }
  if (severity === "warning") {
    return 1;
  }
  return 0;
}

function worstRosterWarningSeverity(warnings: ValidationWarning[]): ValidationWarning["severity"] {
  let best = -1;
  let picked: ValidationWarning["severity"] = "info";
  for (const warning of warnings) {
    const rank = rosterWarningSeverityRank(warning.severity);
    if (rank > best) {
      best = rank;
      picked = warning.severity;
    }
  }
  return picked;
}

function inlineValidationBadgeTone(warnings: ValidationWarning[]): "clear" | ValidationWarning["severity"] {
  if (!warnings.length) {
    return "clear";
  }
  return worstRosterWarningSeverity(warnings);
}

function inlineValidationBadgeClass(tone: ReturnType<typeof inlineValidationBadgeTone>): string {
  if (tone === "clear") {
    return "bg-emerald-100 text-emerald-800 ring-emerald-200";
  }
  if (tone === "error") {
    return "bg-rose-100 text-rose-800 ring-rose-200";
  }
  if (tone === "warning") {
    return "bg-amber-100 text-amber-900 ring-amber-200";
  }
  return "bg-sky-100 text-sky-900 ring-sky-200";
}

function inlineValidationRowTone(severity: ValidationWarning["severity"]): "info" | "warning" | "error" {
  if (severity === "error" || severity === "warning" || severity === "info") {
    return severity;
  }
  return "warning";
}

function inlineValidationRowClasses(tone: ReturnType<typeof inlineValidationRowTone>): {
  wrap: string;
  lead: string;
  sep: string;
  detail: string;
  fallback: string;
} {
  if (tone === "error") {
    return {
      wrap: "rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-900 ring-1 ring-rose-200",
      lead: "flex flex-wrap items-baseline gap-x-2 gap-y-0.5 font-semibold text-rose-950",
      sep: "text-rose-800/80",
      detail: "text-xs font-medium leading-snug text-rose-900/95",
      fallback: "text-xs leading-snug text-rose-900/90"
    };
  }
  if (tone === "warning") {
    return {
      wrap: "rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-950 ring-1 ring-amber-200",
      lead: "flex flex-wrap items-baseline gap-x-2 gap-y-0.5 font-semibold text-amber-950",
      sep: "text-amber-900/80",
      detail: "text-xs font-medium leading-snug text-amber-950/95",
      fallback: "text-xs leading-snug text-amber-950/90"
    };
  }
  return {
    wrap: "rounded-lg bg-sky-50 px-3 py-2 text-sm text-sky-950 ring-1 ring-sky-200",
    lead: "flex flex-wrap items-baseline gap-x-2 gap-y-0.5 font-semibold text-sky-950",
    sep: "text-sky-900/80",
    detail: "text-xs font-medium leading-snug text-sky-950/95",
    fallback: "text-xs leading-snug text-sky-950/90"
  };
}

function InlineValidation({
  rosterMatrix,
  warnings,
  dayStatusDefinitions
}: {
  rosterMatrix: RosterMatrix | null;
  warnings: ValidationWarning[];
  dayStatusDefinitions: PlanningDayStatusDefinition[];
}) {
  const { locale } = useLocale();
  const rosterWarnings = warnings.filter(
    (warning) =>
      warning.code.startsWith("ROSTER_MATRIX") ||
      warning.code === "ROSTER_TEMPLATE_NO_GO_CONFLICT" ||
      warning.code.startsWith("ROSTER_CONSTRAINT") ||
      warning.code.startsWith("MEMBER_PATTERN") ||
      warning.code === "ROSTER_CONSECUTIVE_WEEKENDS"
  );
  const badgeTone = inlineValidationBadgeTone(rosterWarnings);
  return (
    <Card>
      <div className="grid gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold text-ink">{t(locale, "conflictSummary")}</h2>
          <span className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 ${inlineValidationBadgeClass(badgeTone)}`}>
            {rosterWarnings.length}
          </span>
        </div>
        {rosterWarnings.length ? (
          <div className="grid gap-2">
            {rosterWarnings.slice(0, 6).map((warning, index) => {
              const member =
                warning.team_member_id != null
                  ? rosterMatrix?.team_members.find((row) => row.id === warning.team_member_id)
                  : null;
              const memberName = member ? teamMemberLabel(member) : null;
              const detail = validationWarningDetailText(warning, rosterMatrix, locale, dayStatusDefinitions);
              const hasLead = Boolean(warning.date || memberName || warning.team_member_id != null);
              const rowTone = inlineValidationRowTone(warning.severity);
              const rowClass = inlineValidationRowClasses(rowTone);
              return (
                <div
                  key={`${warning.code}-${warning.team_member_id}-${warning.date}-${index}`}
                  className={rowClass.wrap}
                >
                  {hasLead ? (
                    <div className={rowClass.lead}>
                      {warning.date ? <span className="tabular-nums">{warning.date}</span> : null}
                      {warning.date && (memberName || warning.team_member_id != null) ? <span className={rowClass.sep}>·</span> : null}
                      {memberName ? <span>{memberName}</span> : warning.team_member_id != null ? <span>ID {warning.team_member_id}</span> : null}
                    </div>
                  ) : null}
                  {detail ? (
                    <p className={`${rowClass.detail} ${hasLead ? "mt-1" : ""}`}>{detail}</p>
                  ) : (
                    <p className={`${rowClass.fallback} ${hasLead ? "mt-1" : ""}`}>{warning.message}</p>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-sm text-slate-600">{t(locale, "noConflicts")}</p>
        )}
      </div>
    </Card>
  );
}

type WorkloadSortColumn =
  | "name"
  | "employmentPercentage"
  | "total"
  | "onCallDuty"
  | "standbyDuty"
  | "lateDuty"
  | "other"
  | "weekendHolidayShifts"
  | "conflicts";

function defaultWorkloadSortDir(col: WorkloadSortColumn): "asc" | "desc" {
  return col === "name" ? "asc" : "desc";
}

function compareWorkloadRows(
  a: TeamMemberWorkloadRow,
  b: TeamMemberWorkloadRow,
  col: WorkloadSortColumn,
  dir: "asc" | "desc"
): number {
  const mul = dir === "asc" ? 1 : -1;
  if (col === "name") {
    return a.name.localeCompare(b.name, undefined, { sensitivity: "base" }) * mul;
  }
  const av = a[col];
  const bv = b[col];
  if (av !== bv) {
    return (av - bv) * mul;
  }
  return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
}

function SortableWorkloadTh({
  locale,
  labelKey,
  column,
  active,
  dir,
  onSort,
  numeric
}: {
  locale: Locale;
  labelKey: TranslationKey;
  column: WorkloadSortColumn;
  active: boolean;
  dir: "asc" | "desc";
  onSort: (col: WorkloadSortColumn) => void;
  numeric?: boolean;
}) {
  return (
    <th
      scope="col"
      aria-sort={active ? (dir === "asc" ? "ascending" : "descending") : "none"}
      className={`sticky top-0 z-10 bg-slate-50 p-0 font-semibold shadow-[0_1px_0_0_rgb(226_232_240)] ${numeric ? "text-right" : "text-left"}`}
    >
      <button
        type="button"
        title={t(locale, "workloadTableSortHint")}
        onClick={() => onSort(column)}
        className={`flex w-full items-center gap-1 px-3 py-3 text-slate-700 hover:bg-slate-100/80 ${numeric ? "justify-end" : "justify-start"}`}
      >
        <span>{t(locale, labelKey)}</span>
        {active ? (
          dir === "asc" ? (
            <ArrowUp className="h-3.5 w-3.5 shrink-0 text-ink" strokeWidth={2} aria-hidden />
          ) : (
            <ArrowDown className="h-3.5 w-3.5 shrink-0 text-ink" strokeWidth={2} aria-hidden />
          )
        ) : (
          <ArrowDownUp className="h-3.5 w-3.5 shrink-0 opacity-35" strokeWidth={2} aria-hidden />
        )}
      </button>
    </th>
  );
}

function WorkloadStats({ rows, unassigned }: { rows: TeamMemberWorkloadRow[]; unassigned: number }) {
  const { locale } = useLocale();
  const [sort, setSort] = useState<{ col: WorkloadSortColumn; dir: "asc" | "desc" }>({ col: "name", dir: "asc" });

  const sortedRows = useMemo(() => {
    const next = [...rows];
    next.sort((a, b) => compareWorkloadRows(a, b, sort.col, sort.dir));
    return next;
  }, [rows, sort]);

  const activateSort = useCallback((col: WorkloadSortColumn) => {
    setSort((prev) =>
      prev.col === col ? { col, dir: prev.dir === "asc" ? "desc" : "asc" } : { col, dir: defaultWorkloadSortDir(col) }
    );
  }, []);

  return (
    <Card>
      <div className="grid gap-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold text-ink">{t(locale, "workloadStats")}</h2>
            <p className="mt-1 text-sm text-slate-600">{t(locale, "unassignedSlots")}: {unassigned}</p>
          </div>
        </div>
        {rows.length ? (
          <div className={`${dataTableScrollShellClassName} rounded-lg border border-slate-200`}>
            <table className="min-w-full text-sm">
              <thead className="text-left text-slate-600">
                <tr className="border-b border-slate-200">
                  <SortableWorkloadTh
                    locale={locale}
                    labelKey="teamMembers"
                    column="name"
                    active={sort.col === "name"}
                    dir={sort.dir}
                    onSort={activateSort}
                  />
                  <SortableWorkloadTh
                    locale={locale}
                    labelKey="employment"
                    column="employmentPercentage"
                    active={sort.col === "employmentPercentage"}
                    dir={sort.dir}
                    onSort={activateSort}
                    numeric
                  />
                  <SortableWorkloadTh
                    locale={locale}
                    labelKey="totalShifts"
                    column="total"
                    active={sort.col === "total"}
                    dir={sort.dir}
                    onSort={activateSort}
                    numeric
                  />
                  <SortableWorkloadTh
                    locale={locale}
                    labelKey="onCallDutyCategory"
                    column="onCallDuty"
                    active={sort.col === "onCallDuty"}
                    dir={sort.dir}
                    onSort={activateSort}
                    numeric
                  />
                  <SortableWorkloadTh
                    locale={locale}
                    labelKey="standbyDutyCategory"
                    column="standbyDuty"
                    active={sort.col === "standbyDuty"}
                    dir={sort.dir}
                    onSort={activateSort}
                    numeric
                  />
                  <SortableWorkloadTh
                    locale={locale}
                    labelKey="lateDutyCategory"
                    column="lateDuty"
                    active={sort.col === "lateDuty"}
                    dir={sort.dir}
                    onSort={activateSort}
                    numeric
                  />
                  <SortableWorkloadTh
                    locale={locale}
                    labelKey="other"
                    column="other"
                    active={sort.col === "other"}
                    dir={sort.dir}
                    onSort={activateSort}
                    numeric
                  />
                  <SortableWorkloadTh
                    locale={locale}
                    labelKey="workloadWeekendHolidayShifts"
                    column="weekendHolidayShifts"
                    active={sort.col === "weekendHolidayShifts"}
                    dir={sort.dir}
                    onSort={activateSort}
                    numeric
                  />
                  <SortableWorkloadTh
                    locale={locale}
                    labelKey="conflicts"
                    column="conflicts"
                    active={sort.col === "conflicts"}
                    dir={sort.dir}
                    onSort={activateSort}
                    numeric
                  />
                </tr>
              </thead>
              <tbody>
                {sortedRows.map((row) => (
                  <tr key={row.memberId} className="border-t border-slate-100">
                    <td className="p-3 font-medium text-ink">{row.name}</td>
                    <td className="p-3 text-right tabular-nums">{row.employmentPercentage}%</td>
                    <td className="p-3 text-right tabular-nums">{row.total}</td>
                    <td className="p-3 text-right tabular-nums">{row.onCallDuty}</td>
                    <td className="p-3 text-right tabular-nums">{row.standbyDuty}</td>
                    <td className="p-3 text-right tabular-nums">{row.lateDuty}</td>
                    <td className="p-3 text-right tabular-nums">{row.other}</td>
                    <td className="p-3 text-right tabular-nums">{row.weekendHolidayShifts}</td>
                    <td className={row.conflicts ? "p-3 text-right font-semibold tabular-nums text-rose-700" : "p-3 text-right tabular-nums"}>
                      {row.conflicts}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-slate-500">{t(locale, "noData")}</p>
        )}
      </div>
    </Card>
  );
}

export function PlanningWorkspace({ variant = "planner" }: { variant?: "planner" | "team_member" } = {}) {
  return <PlanningWorkspaceContent variant={variant} />;
}
