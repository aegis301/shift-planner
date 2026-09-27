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
  };
  go: (href: string) => void;
  publish: () => void;
  preliminary: () => void;
  draft: () => void;
  solver: () => void;
  export: () => void;
  deletePeriod: () => void;
};

function reason(ok: boolean, message: string): string | null {
  return ok ? null : message;
}

export function buildPaletteCommands(context: PaletteContext): PaletteCommand[] {
  const needsScope = context.hasPeriod && context.hasShiftGroup;
  const solverOk = needsScope && context.status !== "published";
  return [
    { id: "go-planning", label: context.labels.planning, disabledReason: null, run: () => context.go("/planning") },
    { id: "go-hours", label: context.labels.hours, disabledReason: null, run: () => context.go("/hours") },
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
