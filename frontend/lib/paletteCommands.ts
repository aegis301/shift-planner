export type PaletteChoice = { id: string; label: string };

export type PaletteCommand = {
  id: string;
  label: string;
  disabledReason: string | null;
  run: () => void;
};

export type PaletteContext = {
  isAdmin: boolean;
  hasPeriod: boolean;
  hasShiftGroup: boolean;
  status: "draft" | "preliminary" | "published" | null;
  labels: {
    planning: string;
    hours: string;
    publish: string;
    preliminary: string;
    draft: string;
    solver: string;
    export: string;
    deletePeriod: string;
    adminOnly: string;
    published: string;
    statusForbidden: string;
    needGroup: string;
    needPeriod: string;
    sync: string;
    regenerate: string;
  };
  periods: PaletteChoice[];
  groups: PaletteChoice[];
  members: PaletteChoice[];
  days: PaletteChoice[];
  go: (href: string) => void;
  publish: () => void;
  preliminary: () => void;
  draft: () => void;
  solver: () => void;
  export: () => void;
  deletePeriod: () => void;
  selectPeriod: (id: string) => void;
  selectGroup: (id: string) => void;
  selectMember: (id: string) => void;
  selectDay: (id: string) => void;
  sync: () => void;
  regenerate: () => void;
};

function reason(ok: boolean, message: string): string | null {
  return ok ? null : message;
}

export function buildPaletteCommands(context: PaletteContext): PaletteCommand[] {
  const needsScope = context.hasPeriod && context.hasShiftGroup;
  const solverOk = needsScope && context.status !== "published";
  const syncOk = context.hasPeriod && (context.isAdmin || context.hasShiftGroup) && context.status !== "published";
  const regenerateOk = context.hasPeriod && context.status !== "published";
  const scopeReason = !context.hasPeriod ? context.labels.needPeriod : context.labels.needGroup;
  return [
    { id: "go-planning", label: context.labels.planning, disabledReason: null, run: () => context.go("/planning") },
    { id: "go-hours", label: context.labels.hours, disabledReason: null, run: () => context.go("/hours") },
    ...context.periods.map((period) => ({
      id: `period-${period.id}`,
      label: period.label,
      disabledReason: null,
      run: () => context.selectPeriod(period.id)
    })),
    ...context.groups.map((group) => ({
      id: `group-${group.id}`,
      label: group.label,
      disabledReason: null,
      run: () => context.selectGroup(group.id)
    })),
    ...context.members.map((member) => ({
      id: `member-${member.id}`,
      label: member.label,
      disabledReason: null,
      run: () => context.selectMember(member.id)
    })),
    ...context.days.map((day) => ({
      id: `day-${day.id}`,
      label: day.label,
      disabledReason: null,
      run: () => context.selectDay(day.id)
    })),
    {
      id: "publish",
      label: context.labels.publish,
      disabledReason: reason(needsScope && context.status === "preliminary", context.hasPeriod && context.hasShiftGroup ? context.labels.statusForbidden : context.labels.needGroup),
      run: context.publish
    },
    {
      id: "preliminary",
      label: context.labels.preliminary,
      disabledReason: reason(needsScope && context.status !== "preliminary", context.hasPeriod && context.hasShiftGroup ? context.labels.statusForbidden : context.labels.needGroup),
      run: context.preliminary
    },
    {
      id: "draft",
      label: context.labels.draft,
      disabledReason: reason(needsScope && context.status === "preliminary", context.hasPeriod && context.hasShiftGroup ? context.labels.statusForbidden : context.labels.needGroup),
      run: context.draft
    },
    {
      id: "solver",
      label: context.labels.solver,
      disabledReason: reason(solverOk, !needsScope ? context.labels.needGroup : context.labels.published),
      run: context.solver
    },
    {
      id: "sync",
      label: context.labels.sync,
      disabledReason: reason(syncOk, context.status === "published" ? context.labels.published : scopeReason),
      run: context.sync
    },
    {
      id: "regenerate",
      label: context.labels.regenerate,
      disabledReason: reason(regenerateOk, context.status === "published" ? context.labels.published : context.labels.needPeriod),
      run: context.regenerate
    },
    {
      id: "export",
      label: context.labels.export,
      disabledReason: reason(context.hasPeriod && (context.isAdmin || context.hasShiftGroup), context.hasPeriod ? context.labels.needGroup : context.labels.needPeriod),
      run: context.export
    },
    {
      id: "delete-period",
      label: context.labels.deletePeriod,
      disabledReason: reason(context.isAdmin && context.hasPeriod, context.isAdmin ? context.labels.needPeriod : context.labels.adminOnly),
      run: context.deletePeriod
    }
  ];
}
