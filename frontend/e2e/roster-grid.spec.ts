import AxeBuilder from "@axe-core/playwright";
import { desktop, expect, plannerAuth, planningPath, planningTarget, test } from "./fixtures";

test.describe("roster grid", () => {
  test.use({ storageState: plannerAuth, viewport: desktop });

  test("assigns a week from the keyboard and undoes it after reload", async ({ page, request }) => {
    const target = await planningTarget(request);
    await page.goto(planningPath(target));
    await page.getByRole("button", { name: "Finaler Dienstplan" }).click();
    const grid = page.getByRole("grid", { name: "Dienstplan" });
    await expect(grid).toBeVisible();
    await grid.getByRole("gridcell").first().focus();
    let assigned = false;
    for (let day = 0; day < 4 && !assigned; day += 1) {
      assigned = await assignWithKeyboard(page);
      if (!assigned) {
        await page.keyboard.press("ArrowDown");
      }
    }
    expect(assigned).toBeTruthy();
    const history = page.waitForResponse(
      (response) => response.url().includes("/change-sets") && response.request().method() === "GET"
    );
    await page.reload();
    await page.getByRole("button", { name: "Finaler Dienstplan" }).click();
    await history;
    await grid.getByRole("gridcell").first().focus();
    const reverted = page.waitForResponse((response) => response.url().includes("/revert") && response.request().method() === "POST");
    await page.keyboard.press("Control+z");
    expect((await reverted).ok()).toBeTruthy();
  });

  test("pastes a range as one change set", async ({ page, request, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    const target = await planningTarget(request);
    await page.goto(planningPath(target));
    await page.getByRole("button", { name: "Finaler Dienstplan" }).click();
    const cell = page.getByRole("grid", { name: "Dienstplan" }).locator("[data-roster-slot]").nth(1);
    await cell.click();
    await page.keyboard.press("Escape");
    await cell.focus();
    await page.keyboard.press("Control+c");
    await page.keyboard.press("ArrowRight");
    const posts: string[] = [];
    page.on("request", (req) => {
      if (req.method() === "POST" && req.url().includes("/change-sets") && !req.url().includes("/revert")) {
        posts.push(req.postData() ?? "");
      }
    });
    await page.keyboard.press("Control+v");
    await expect.poll(() => posts.length).toBe(1);
  });

  test("shows a refused paste and the legal subset", async ({ page, request, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    const target = await planningTarget(request);
    await page.route("**/api/v1/roster-matrix/*/change-sets**", async (route) => {
      if (route.request().method() !== "POST") {
        await route.continue();
        return;
      }
      const body = route.request().postDataJSON() as { mode?: string; items?: { roster_slot_id: number }[] };
      if (body.mode === "best_effort") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: 90,
            organization_id: 1,
            planning_period_id: target.periodId,
            shift_group_id: target.shiftGroupId,
            created_by_user_id: 1,
            actor: "planner@example.com",
            source: "ui",
            mode: "best_effort",
            status: "partially_applied",
            reverts_change_set_id: null,
            label: "Paste",
            created_at: "2026-10-01T00:00:00Z",
            items: (body.items ?? []).map((item, index) => ({
              id: index + 1,
              roster_slot_id: item.roster_slot_id,
              before_team_member_id: null,
              after_team_member_id: 1,
              before_manual_override: false,
              after_manual_override: false,
              before_comment: null,
              after_comment: null,
              outcome: "applied",
              findings: [],
              refusal_code: null
            }))
          })
        });
        return;
      }
      await route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({
          id: 91,
          organization_id: 1,
          planning_period_id: target.periodId,
          shift_group_id: target.shiftGroupId,
          created_by_user_id: 1,
          actor: "planner@example.com",
          source: "ui",
          mode: "all_or_nothing",
          status: "refused",
          reverts_change_set_id: null,
          label: "Paste",
          created_at: "2026-10-01T00:00:00Z",
          items: (body.items ?? []).map((item, index) => ({
            id: index + 1,
            roster_slot_id: item.roster_slot_id,
            before_team_member_id: null,
            after_team_member_id: 1,
            before_manual_override: false,
            after_manual_override: false,
            before_comment: null,
            after_comment: null,
            outcome: "refused",
            findings: [{ code: "RULE_ERROR", severity: "error", message: "No-Go", team_member_id: 1, date: "2026-10-01", details: {} }],
            refusal_code: "RULE_ERROR"
          }))
        })
      });
    });
    await page.goto(planningPath(target));
    await page.getByRole("button", { name: "Finaler Dienstplan" }).click();
    const grid = page.getByRole("grid", { name: "Dienstplan" });
    await grid.getByRole("gridcell").first().click();
    await page.keyboard.press("Escape");
    await grid.getByRole("gridcell").first().focus();
    await page.keyboard.press("Control+c");
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("Control+v");
    await expect(page.getByRole("heading", { name: "Änderung abgelehnt" })).toBeVisible();
    await expect(page.getByText("RULE_ERROR").first()).toBeVisible();
    await page.getByRole("button", { name: "Nur das Zulässige übernehmen" }).click();
    await expect(page.getByRole("heading", { name: "Änderung abgelehnt" })).toBeHidden();
  });

  test("reports an unknown pasted name", async ({ page, request, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    const target = await planningTarget(request);
    await page.goto(planningPath(target));
    await page.getByRole("button", { name: "Finaler Dienstplan" }).click();
    const cell = page.getByRole("grid", { name: "Dienstplan" }).locator("[data-roster-slot]").first();
    await cell.click();
    await page.keyboard.press("Escape");
    await cell.focus();
    await page.evaluate(() => navigator.clipboard.writeText("Not A Person"));
    await page.keyboard.press("Control+v");
    await expect(page.getByText("Unbekannte Namen: Not A Person")).toBeVisible();
  });

  test("moves the active cell quickly", async ({ page, request }) => {
    const target = await planningTarget(request);
    await page.goto(planningPath(target));
    await page.getByRole("button", { name: "Finaler Dienstplan" }).click();
    const grid = page.getByRole("grid", { name: "Dienstplan" });
    await grid.getByRole("gridcell").first().focus();
    const elapsed = await page.evaluate(async () => {
      const start = performance.now();
      for (let step = 0; step < 100; step += 1) {
        document.activeElement?.dispatchEvent(
          new KeyboardEvent("keydown", { key: step % 2 === 0 ? "ArrowRight" : "ArrowLeft", bubbles: true, cancelable: true })
        );
      }
      return performance.now() - start;
    });
    expect(elapsed).toBeLessThan(2000);
  });

  test("exposes grid semantics", async ({ page, request }) => {
    const target = await planningTarget(request);
    await page.goto(planningPath(target));
    await page.getByRole("button", { name: "Finaler Dienstplan" }).click();
    const grid = page.getByRole("grid", { name: "Dienstplan" });
    await expect(grid).toBeVisible();
    await grid.getByRole("gridcell").first().focus();
    const results = await new AxeBuilder({ page }).include("[role=grid]").analyze();
    expect(results.violations).toEqual([]);
  });
});

async function assignWithKeyboard(page: import("@playwright/test").Page): Promise<boolean> {
  await page.keyboard.press("Enter");
  const list = page.getByRole("listbox");
  const opened = await list.waitFor({ state: "visible", timeout: 1500 }).then(() => true).catch(() => false);
  if (!opened) {
    return false;
  }
  for (let attempt = 0; attempt < 8; attempt += 1) {
    if (attempt > 0) {
      await page.keyboard.press("Enter");
      await list.waitFor({ state: "visible" });
    }
    for (let step = 0; step <= attempt; step += 1) {
      await page.keyboard.press("ArrowDown");
    }
    const pending = page.waitForResponse(
      (response) => response.url().includes("/api/v1/roster-matrix/assignments") && response.request().method() === "PUT",
      { timeout: 8000 }
    );
    await page.keyboard.press("Enter");
    const response = await pending;
    if (response.ok()) {
      return true;
    }
  }
  await page.keyboard.press("Escape");
  return false;
}
