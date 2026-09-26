import { expect, test as base, type APIRequestContext, type Locator, type Page } from "@playwright/test";
import { authFile } from "./global-setup";

const fixedClock = `(() => {
  const fixed = Date.parse("2026-09-15T08:00:00.000Z");
  const RealDate = Date;
  class FixedDate extends RealDate {
    constructor(...args) {
      super(...(args.length ? args : [fixed]));
    }
    static now() {
      return fixed;
    }
  }
  FixedDate.parse = RealDate.parse.bind(RealDate);
  FixedDate.UTC = RealDate.UTC.bind(RealDate);
  window.Date = FixedDate;
  const style = document.createElement("style");
  style.textContent = "*,*::before,*::after{animation-duration:0s!important;animation-delay:0s!important;transition-duration:0s!important;caret-color:transparent!important}nextjs-portal{display:none!important}";
  document.documentElement.append(style);
})();`;

export const test = base.extend({
  page: async ({ page }, use) => {
    await page.addInitScript(fixedClock);
    await use(page);
  }
});

export { expect };

export const desktop = { width: 1440, height: 900 };
export const phone = { width: 390, height: 844 };

export const adminAuth = authFile("admin");
export const plannerAuth = authFile("planner");
export const memberAuth = authFile("member");

type PlanningTarget = {
  periodId: number;
  shiftGroupId: number;
};

export async function planningTarget(request: APIRequestContext): Promise<PlanningTarget> {
  const periodsResponse = await request.get("/api/v1/planning-periods");
  if (!periodsResponse.ok()) {
    throw new Error(`Planning periods failed: ${periodsResponse.status()} ${await periodsResponse.text()}`);
  }
  const periods = (await periodsResponse.json()) as { id: number; year: number; month: number }[];
  const period = periods.find((row) => row.year === 2026 && row.month === 10);
  if (!period) {
    throw new Error("Planning period 2026-10 was not found");
  }
  const groupsResponse = await request.get("/api/v1/shift-groups?active_only=true");
  let shiftGroupId: number | undefined;
  if (groupsResponse.ok()) {
    const groups = (await groupsResponse.json()) as { id: number; code: string }[];
    shiftGroupId = groups.find((row) => row.code === "anaesthesie")?.id;
  }
  if (shiftGroupId == null) {
    const meResponse = await request.get("/api/v1/auth/me");
    if (!meResponse.ok()) {
      throw new Error(`Session failed: ${meResponse.status()} ${await meResponse.text()}`);
    }
    const me = (await meResponse.json()) as {
      shift_groups?: { id: number; code: string }[];
      planner_shift_groups?: { id: number; code: string }[];
    };
    const groups = [...(me.shift_groups ?? []), ...(me.planner_shift_groups ?? [])];
    shiftGroupId = groups.find((row) => row.code === "anaesthesie")?.id;
  }
  if (shiftGroupId == null) {
    throw new Error("Shift group anaesthesie was not found");
  }
  return { periodId: period.id, shiftGroupId };
}

export function planningPath(target: PlanningTarget, pathname = "/planning"): string {
  return `${pathname}?period=${target.periodId}&shiftGroup=${target.shiftGroupId}`;
}

export async function settle(page: Page): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
}

export async function shot(page: Page, name: string, mask: Locator[] = []): Promise<void> {
  await settle(page);
  await expect(page).toHaveScreenshot(`${name}.png`, { mask });
}

const dashboardSectionTitles = [
  "Nächste Dienste",
  "Vergangene Dienste",
  "Schichten pro Monat (Dienstvorlagen)",
  "Schichten nach Dienstvorlage",
  "Tagesstatus (aktueller Monat)",
  "Meine Planungsmonate"
];

export async function pinDashboardSections(page: Page): Promise<Locator[]> {
  await page.evaluate((titles) => {
    for (const heading of document.querySelectorAll("h2")) {
      if (!titles.includes(heading.textContent?.trim() ?? "")) {
        continue;
      }
      const section = heading.closest("section");
      if (section instanceof HTMLElement) {
        section.style.height = "96px";
        section.style.overflow = "hidden";
      }
    }
  }, dashboardSectionTitles);
  return dashboardSectionTitles.map((title) =>
    page.locator("section").filter({ has: page.getByRole("heading", { name: title, exact: true }) })
  );
}

export async function signOut(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Konto und Einstellungen" }).click();
  await page.getByRole("menuitem", { name: "Abmelden" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "Admin Login" })).toBeVisible();
}
