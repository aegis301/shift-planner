"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, BarChart3, CalendarCheck, Columns3, Download, Heart, LayoutList, Plus, RotateCw, Save, Trash2, X } from "lucide-react";
import { Card, Field, inputClass } from "@/components/Card";
import { MatrixEditor } from "@/components/MatrixEditor";
import { PlanningDayStatusLegend } from "@/components/PlanningDayStatusLegend";
import { useLocale, useSession } from "@/components/LocaleProvider";
import { RosterMatrixEditor, type RosterMatrix } from "@/components/RosterMatrixEditor";
import { API_BASE_URL, ApiError, apiFetch } from "@/lib/api";
import { t, type Locale, type TranslationKey } from "@/lib/i18n";

type PlanningPeriod = {
  id: number;
  year: number;
  month: number;
  status: string;
  published_at?: string | null;
};

type ValidationWarning = {
  code: string;
  severity: "info" | "warning" | "error";
  message: string;
  team_member_id: number | null;
  date: string | null;
  details: Record<string, unknown>;
};

type TeamMemberWorkloadRow = {
  memberId: number;
  name: string;
  total: number;
  onCallDuty: number;
  standbyDuty: number;
  lateDuty: number;
  other: number;
  conflicts: number;
};

type PlanningViewMode = "stacked" | "tabs";
type PlanningTab = "wishes" | "roster" | "analysis";
type DestructiveAction = "delete-period" | "regenerate-roster" | "publish-period" | "unpublish-period";

type ShiftGroupOption = { id: number; code: string; name_de: string; name_en: string };

function teamMemberLabel(member: { first_name: string; last_name: string }): string {
  return `${member.first_name} ${member.last_name}`.trim();
}

function monthLabel(period: PlanningPeriod | undefined) {
  if (!period) {
    return "";
  }
  return `${period.year}-${String(period.month).padStart(2, "0")}`;
}

function buildStats(matrix: RosterMatrix | null, warnings: ValidationWarning[]): { rows: TeamMemberWorkloadRow[]; unassigned: number } {
  if (!matrix) {
    return { rows: [], unassigned: 0 };
  }
  const slots = new Map(matrix.slots.map((slot) => [slot.id, slot]));
  const stats = new Map<number, TeamMemberWorkloadRow>(
    matrix.team_members.map((member) => [
      member.id,
      {
        memberId: member.id,
        name: teamMemberLabel(member),
        total: 0,
        onCallDuty: 0,
        standbyDuty: 0,
        lateDuty: 0,
        other: 0,
        conflicts: 0
      }
    ])
  );

  for (const assignment of matrix.assignments) {
    const memberStats = stats.get(assignment.team_member_id);
    const slot = slots.get(assignment.roster_slot_id);
    const category = slot?.category;
    if (!memberStats || !category) {
      continue;
    }
    memberStats.total += 1;
    if (category === "bereitschaftsdienst") {
      memberStats.onCallDuty += 1;
    } else if (category === "rufdienst") {
      memberStats.standbyDuty += 1;
    } else if (category === "spaetdienst") {
      memberStats.lateDuty += 1;
    } else {
      memberStats.other += 1;
    }
  }

  for (const warning of warnings) {
    const rosterRelated =
      warning.code.startsWith("ROSTER_MATRIX") || warning.code === "ROSTER_TEMPLATE_NO_GO_CONFLICT";
    if (!rosterRelated || !warning.team_member_id) {
      continue;
    }
    const memberStats = stats.get(warning.team_member_id);
    if (memberStats) {
      memberStats.conflicts += 1;
    }
  }

  return {
    rows: [...stats.values()].sort((a, b) => a.name.localeCompare(b.name)),
    unassigned: Math.max(0, matrix.slots.length - matrix.assignments.length)
  };
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
  const [viewMode, setViewMode] = useState<PlanningViewMode>("tabs");
  const [activeTab, setActiveTab] = useState<PlanningTab>("wishes");
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isExportModalOpen, setIsExportModalOpen] = useState(false);
  const [destructiveAction, setDestructiveAction] = useState<DestructiveAction | null>(null);
  const [shiftGroupId, setShiftGroupId] = useState("");
  const [shiftGroups, setShiftGroups] = useState<ShiftGroupOption[]>([]);

  const planningUi = variant === "planner" && Boolean(me?.capabilities?.planning);
  const adminUi = variant === "planner" && Boolean(me?.capabilities?.admin);
  const teamMemberPortalUi = variant === "team_member" && Boolean(me?.capabilities?.team_member_portal);
  const editableMemberId = teamMemberPortalUi && me?.team_member_id != null ? me.team_member_id : undefined;
  const waitingForTeamMemberSession = variant === "team_member" && (sessionLoading || !teamMemberPortalUi);
  const waitingForPlannerSession = variant === "planner" && (sessionLoading || !me);
  const plannerNeedsShiftGroup = variant === "planner" && me?.role === "planner";

  useEffect(() => {
    if (sessionLoading || !me) {
      return;
    }
    if (variant === "planner" && !me.capabilities?.planning) {
      router.replace(me.capabilities?.team_member_portal ? "/my-planning" : "/");
    }
    if (variant === "team_member" && !me.capabilities?.team_member_portal) {
      router.replace(me.capabilities?.planning ? "/planning" : "/");
    }
  }, [me, router, sessionLoading, variant]);

  const shiftGroupQuery = useMemo(
    () => (shiftGroupId ? `?shift_group_id=${encodeURIComponent(shiftGroupId)}` : ""),
    [shiftGroupId]
  );

  useEffect(() => {
    setShiftGroupId(searchParams.get("shiftGroup") ?? "");
  }, [searchParams]);

  useEffect(() => {
    if (!planningUi || !me) {
      return;
    }
    if (me.capabilities?.admin) {
      void apiFetch<ShiftGroupOption[]>("/api/v1/shift-groups?active_only=true").then(setShiftGroups).catch(() => setShiftGroups([]));
      return;
    }
    setShiftGroups(
      (me.planner_shift_groups ?? []).map((g) => ({
        id: g.id,
        code: g.code,
        name_de: g.name_de,
        name_en: g.name_en
      }))
    );
  }, [planningUi, me]);

  useEffect(() => {
    if (variant !== "team_member" || !me?.shift_groups?.length) {
      return;
    }
    setShiftGroups(
      me.shift_groups.map((g) => ({
        id: g.id,
        code: g.code,
        name_de: g.name_de,
        name_en: g.name_en
      }))
    );
  }, [me, variant]);

  const activePeriod = periods.find((period) => String(period.id) === periodId);
  const stats = useMemo(() => buildStats(rosterMatrix, warnings), [rosterMatrix, warnings]);

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
        setRosterMatrix(await apiFetch<RosterMatrix>(`/api/v1/roster-matrix/${nextPeriodId}${shiftGroupQuery}`));
        if (teamMemberPortalUi) {
          setMessage("");
        }
      } catch (error) {
        if (error instanceof ApiError && (error.status === 403 || error.status === 400)) {
          setRosterMatrix(null);
          if (teamMemberPortalUi) {
            setMessage(t(locale, "rosterNotPublishedYet"));
          }
          return;
        }
        throw error;
      }
    },
    [teamMemberPortalUi, locale, shiftGroupQuery]
  );

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
    if (variant !== "team_member" || !me?.shift_groups?.length || shiftGroupId) {
      return;
    }
    if (me.shift_groups.length === 1) {
      const id = String(me.shift_groups[0].id);
      setShiftGroupId(id);
      const params = new URLSearchParams(searchParams.toString());
      params.set("shiftGroup", id);
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    }
  }, [variant, me, shiftGroupId, pathname, router, searchParams]);

  useEffect(() => {
    if (variant !== "planner" || !me?.capabilities?.planning || me.capabilities.admin || !me.planner_shift_groups?.length || shiftGroupId) {
      return;
    }
    if (me.planner_shift_groups.length === 1) {
      const id = String(me.planner_shift_groups[0].id);
      setShiftGroupId(id);
      const params = new URLSearchParams(searchParams.toString());
      params.set("shiftGroup", id);
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    }
  }, [variant, me, shiftGroupId, pathname, router, searchParams]);

  const refreshPeriods = useCallback(async () => {
    const next = await apiFetch<PlanningPeriod[]>("/api/v1/planning-periods");
    setPeriods(next);
    if (!periodId && next[0]) {
      setPeriodId(String(next[0].id));
    }
  }, [periodId]);

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
    if (destructiveAction === "publish-period") {
      await apiFetch<PlanningPeriod>(`/api/v1/planning-periods/${periodId}/publish`, { method: "POST" });
      await refreshPeriods();
      await loadRosterMatrix(periodId);
      setMessage(t(locale, "periodPublished"));
    } else if (destructiveAction === "unpublish-period") {
      await apiFetch<PlanningPeriod>(`/api/v1/planning-periods/${periodId}/unpublish`, { method: "POST" });
      await refreshPeriods();
      await loadRosterMatrix(periodId);
      setMessage(t(locale, "periodUnpublished"));
    } else if (destructiveAction === "regenerate-roster") {
      await apiFetch<RosterMatrix>(`/api/v1/planning-periods/${periodId}/regenerate-roster`, {
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
    await loadWarnings(String(nextMatrix.planning_period.id));
  }, [loadWarnings]);

  const handleWishesChanged = useCallback(async () => {
    if (periodId) {
      await loadWarnings(periodId);
      setRosterReloadToken((value) => value + 1);
      await loadRosterMatrix(periodId);
    }
  }, [loadRosterMatrix, loadWarnings, periodId]);

  const wishesSection = periodId ? (
    <section className="grid gap-3">
      <div>
        <h2 className="text-xl font-semibold text-ink">{t(locale, "wishesSection")}</h2>
        <p className="mt-1 text-sm text-slate-600">{t(locale, "matrixHelp")}</p>
      </div>
      {waitingForPlannerSession ? null : (teamMemberPortalUi || plannerNeedsShiftGroup) && !shiftGroupId ? (
        <p className="text-sm text-amber-800">{t(locale, "selectPlanningShiftGroup")}</p>
      ) : (
        <MatrixEditor
          periodId={periodId}
          compact
          shiftGroupId={shiftGroupId || undefined}
          editableMemberId={editableMemberId}
          onChanged={handleWishesChanged}
        />
      )}
    </section>
  ) : null;

  const rosterSection = periodId ? (
    <section className="grid gap-3">
      <div>
        <h2 className="text-xl font-semibold text-ink">{t(locale, "rosterSection")}</h2>
        <p className="mt-1 text-sm text-slate-600">{t(locale, "finalRosterHelp")}</p>
      </div>
      {waitingForPlannerSession ? null : (teamMemberPortalUi || plannerNeedsShiftGroup) && !shiftGroupId ? (
        <p className="text-sm text-amber-800">{t(locale, "selectPlanningShiftGroup")}</p>
      ) : (
        <RosterMatrixEditor
          periodId={periodId}
          compact
          readOnly={Boolean(teamMemberPortalUi)}
          reloadToken={rosterReloadToken}
          shiftGroupId={shiftGroupId || undefined}
          onMatrixChange={handleRosterChange}
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
      <InlineValidation rosterMatrix={rosterMatrix} warnings={warnings} />
      <WorkloadStats rows={stats.rows} unassigned={stats.unassigned} />
    </section>
  ) : null;

  return (
    <div className="grid gap-6">
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
                      {locale === "de" ? group.name_de : group.name_en} ({group.code})
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
                  <button
                    aria-label={activePeriod?.status === "published" ? t(locale, "unpublishPlanningPeriod") : t(locale, "publishPlanningPeriod")}
                    className={`mt-5 inline-flex h-10 w-10 items-center justify-center rounded-lg border shadow-sm disabled:cursor-not-allowed disabled:opacity-40 ${
                      activePeriod?.status === "published"
                        ? "border-slate-200 bg-slate-50 text-slate-800"
                        : "border-emerald-200 bg-emerald-50 text-emerald-900"
                    }`}
                    disabled={!periodId}
                    onClick={() => setDestructiveAction(activePeriod?.status === "published" ? "unpublish-period" : "publish-period")}
                    title={activePeriod?.status === "published" ? t(locale, "unpublishPlanningPeriod") : t(locale, "publishPlanningPeriod")}
                    type="button"
                  >
                    <CalendarCheck size={18} />
                  </button>
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
            </div>
          </div>
          <div className="flex flex-wrap gap-3 text-sm">
            {activePeriod ? (
              <div className="flex flex-wrap items-center gap-2 text-slate-600">
                <p>
                  {t(locale, "selectedMonth")}: {monthLabel(activePeriod)}
                </p>
                <span
                  className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ${
                    activePeriod.status === "published"
                      ? "bg-emerald-50 text-emerald-900 ring-emerald-200"
                      : "bg-amber-50 text-amber-900 ring-amber-200"
                  }`}
                >
                  {activePeriod.status === "published" ? t(locale, "periodStatusPublished") : t(locale, "periodStatusDraft")}
                </span>
              </div>
            ) : null}
            {message ? <p className="text-emerald-700">{message}</p> : null}
          </div>
          <PlanningDayStatusLegend locale={locale} />
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

      {isExportModalOpen && periodId ? (
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
              <a
                className={`inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 ${
                  plannerNeedsShiftGroup && !shiftGroupId ? "pointer-events-none opacity-40" : ""
                }`}
                href={`${API_BASE_URL}/api/v1/exports/matrix/${periodId}.csv${shiftGroupQuery}`}
              >
                <Download size={17} />
                {t(locale, "wishesCsvExport")}
              </a>
              <a
                className={`inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 ${
                  plannerNeedsShiftGroup && !shiftGroupId ? "pointer-events-none opacity-40" : ""
                }`}
                href={`${API_BASE_URL}/api/v1/exports/roster-matrix/${periodId}.csv${shiftGroupQuery}`}
              >
                <Download size={17} />
                {t(locale, "rosterCsvExport")}
              </a>
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
                      : destructiveAction === "publish-period"
                        ? t(locale, "publishPlanningPeriod")
                        : destructiveAction === "unpublish-period"
                          ? t(locale, "unpublishPlanningPeriod")
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
                destructiveAction === "publish-period" || destructiveAction === "unpublish-period"
                  ? "bg-emerald-50 text-emerald-950 ring-emerald-100"
                  : "bg-rose-50 text-rose-900 ring-rose-100"
              }`}
            >
              {destructiveAction === "delete-period"
                ? t(locale, "deletePlanningPeriodWarning")
                : destructiveAction === "publish-period"
                  ? t(locale, "publishPlanningPeriodConfirm")
                  : destructiveAction === "unpublish-period"
                    ? t(locale, "unpublishPlanningPeriodConfirm")
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
                  destructiveAction === "publish-period" || destructiveAction === "unpublish-period"
                    ? "bg-emerald-700"
                    : "bg-rose-700"
                }`}
                onClick={confirmDestructiveAction}
                type="button"
              >
                {destructiveAction === "delete-period" ? (
                  <Trash2 size={16} />
                ) : destructiveAction === "publish-period" || destructiveAction === "unpublish-period" ? (
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
            {rosterSection}
            {!teamMemberPortalUi ? analysisSection : null}
          </>
        ) : (
          <div className="grid gap-5">
            <div className="flex gap-2 overflow-x-auto rounded-lg border border-slate-200 bg-white p-1 shadow-sm">
              {(teamMemberPortalUi
                ? ([
                    ["wishes", "wishesSection", Heart],
                    ["roster", "rosterSection", CalendarCheck]
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
            {activeTab === "roster" ? rosterSection : null}
            {activeTab === "analysis" ? analysisSection : null}
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
  const name = locale === "de" ? slot.template_name_de : slot.template_name_en;
  const base = name || slot.label || slot.template_code || `#${slot.id}`;
  return slot.variant_label ? `${base} (${slot.variant_label})` : base;
}

function validationWarningDetailText(warning: ValidationWarning, matrix: RosterMatrix | null, locale: Locale): string | null {
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
    const wishLabel =
      st === "urlaub" || st === "forschung" || st === "lehre" || st === "frei" ? t(locale, st as TranslationKey) : st;
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
  return null;
}

function InlineValidation({ rosterMatrix, warnings }: { rosterMatrix: RosterMatrix | null; warnings: ValidationWarning[] }) {
  const { locale } = useLocale();
  const rosterWarnings = warnings.filter(
    (warning) => warning.code.startsWith("ROSTER_MATRIX") || warning.code === "ROSTER_TEMPLATE_NO_GO_CONFLICT"
  );
  return (
    <Card>
      <div className="grid gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold text-ink">{t(locale, "conflictSummary")}</h2>
          <span className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 ${rosterWarnings.length ? "bg-rose-100 text-rose-800 ring-rose-200" : "bg-emerald-100 text-emerald-800 ring-emerald-200"}`}>
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
              const detail = validationWarningDetailText(warning, rosterMatrix, locale);
              const hasLead = Boolean(warning.date || memberName || warning.team_member_id != null);
              return (
                <div
                  key={`${warning.code}-${warning.team_member_id}-${warning.date}-${index}`}
                  className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-900 ring-1 ring-rose-200"
                >
                  {hasLead ? (
                    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 font-semibold text-rose-950">
                      {warning.date ? <span className="tabular-nums">{warning.date}</span> : null}
                      {warning.date && (memberName || warning.team_member_id != null) ? <span className="text-rose-800/80">·</span> : null}
                      {memberName ? <span>{memberName}</span> : warning.team_member_id != null ? <span>ID {warning.team_member_id}</span> : null}
                    </div>
                  ) : null}
                  {detail ? (
                    <p className={`text-xs font-medium leading-snug text-rose-900/95 ${hasLead ? "mt-1" : ""}`}>{detail}</p>
                  ) : (
                    <p className={`text-xs leading-snug text-rose-900/90 ${hasLead ? "mt-1" : ""}`}>{warning.message}</p>
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

function WorkloadStats({ rows, unassigned }: { rows: TeamMemberWorkloadRow[]; unassigned: number }) {
  const { locale } = useLocale();
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
          <div className="overflow-auto rounded-lg border border-slate-200">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-left text-slate-600">
                <tr>
                  <th className="p-3 font-semibold">{t(locale, "teamMembers")}</th>
                  <th className="p-3 font-semibold">{t(locale, "totalShifts")}</th>
                  <th className="p-3 font-semibold">{t(locale, "onCallDutyCategory")}</th>
                  <th className="p-3 font-semibold">{t(locale, "standbyDutyCategory")}</th>
                  <th className="p-3 font-semibold">{t(locale, "lateDutyCategory")}</th>
                  <th className="p-3 font-semibold">{t(locale, "other")}</th>
                  <th className="p-3 font-semibold">{t(locale, "conflicts")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.memberId} className="border-t border-slate-100">
                    <td className="p-3 font-medium text-ink">{row.name}</td>
                    <td className="p-3">{row.total}</td>
                    <td className="p-3">{row.onCallDuty}</td>
                    <td className="p-3">{row.standbyDuty}</td>
                    <td className="p-3">{row.lateDuty}</td>
                    <td className="p-3">{row.other}</td>
                    <td className={row.conflicts ? "p-3 font-semibold text-rose-700" : "p-3"}>{row.conflicts}</td>
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
