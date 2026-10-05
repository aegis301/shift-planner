import { describe, expect, it } from "vitest";
import { buildPaletteCommands, type PaletteContext } from "@/lib/paletteCommands";

function context(overrides: Partial<PaletteContext> = {}): PaletteContext {
  return {
    isAdmin: false,
    hasPeriod: true,
    hasShiftGroup: true,
    status: "draft",
    labels: {
      planning: "Planning",
      hours: "Hours",
      publish: "Publish",
      preliminary: "Preliminary",
      draft: "Draft",
      solver: "Solver",
      export: "Export",
      deletePeriod: "Delete month",
      adminOnly: "Administrators only",
      published: "The plan is published",
      statusForbidden: "The plan status does not allow this",
      needGroup: "Choose a shift group first",
      needPeriod: "Choose a month first",
      sync: "Sync roster",
      regenerate: "Regenerate roster",
      rosterViewTemplate: "Template",
      rosterViewDayNight: "Day/night",
      rosterViewVariant: "Variant"
    },
    periods: [],
    groups: [],
    members: [],
    days: [],
    go: () => undefined,
    publish: () => undefined,
    preliminary: () => undefined,
    draft: () => undefined,
    solver: () => undefined,
    export: () => undefined,
    deletePeriod: () => undefined,
    selectPeriod: () => undefined,
    selectGroup: () => undefined,
    selectMember: () => undefined,
    selectDay: () => undefined,
    sync: () => undefined,
    regenerate: () => undefined,
    selectRosterView: () => undefined,
    ...overrides
  };
}

function reasonFor(commands: ReturnType<typeof buildPaletteCommands>, id: string) {
  return commands.find((row) => row.id === id)?.disabledReason;
}

describe("palette commands", () => {
  it("disables planner-only admin actions and publish from draft", () => {
    const commands = buildPaletteCommands(context());
    expect(reasonFor(commands, "delete-period")).toBe("Administrators only");
    expect(reasonFor(commands, "publish")).toBe("The plan status does not allow this");
    expect(reasonFor(commands, "solver")).toBeNull();
  });

  it("lets an admin delete a period and blocks the solver when published", () => {
    const draftAdmin = buildPaletteCommands(context({ isAdmin: true, status: "draft" }));
    expect(reasonFor(draftAdmin, "delete-period")).toBeNull();
    const published = buildPaletteCommands(context({ isAdmin: true, status: "published" }));
    expect(reasonFor(published, "solver")).toBe("The plan is published");
    expect(reasonFor(published, "publish")).toBe("The plan status does not allow this");
    expect(reasonFor(published, "preliminary")).toBeNull();
    expect(reasonFor(published, "sync")).toBe("The plan is published");
    expect(reasonFor(published, "regenerate")).toBe("The plan is published");
  });

  it("lists periods, shift groups, members, and days", () => {
    const commands = buildPaletteCommands(
      context({
        periods: [{ id: "4", label: "2026-10" }],
        groups: [{ id: "2", label: "Anaesthesie" }],
        members: [{ id: "9", label: "Adler" }],
        days: [{ id: "2026-10-03", label: "2026-10-03" }]
      })
    );
    expect(commands.map((row) => row.id)).toEqual(
      expect.arrayContaining([
        "period-4",
        "group-2",
        "member-9",
        "day-2026-10-03",
        "sync",
        "regenerate",
        "roster-view-template",
        "roster-view-day-night",
        "roster-view-variant"
      ])
    );
  });
});
