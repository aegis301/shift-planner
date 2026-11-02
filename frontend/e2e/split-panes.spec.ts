import AxeBuilder from "@axe-core/playwright";
import { desktop, expect, plannerAuth, planningPath, planningTarget, test } from "./fixtures";

test.describe("resizable workbench panes", () => {
  test.use({ storageState: plannerAuth, viewport: desktop });

  test("drags the workload divider, keeps the width after reload, and collapses the inspector", async ({ page, request }) => {
    const target = await planningTarget(request);
    await page.goto(planningPath(target));
    await page.getByRole("button", { name: "Finaler Dienstplan" }).click();
    await page.evaluate(() => window.localStorage.removeItem("shift-planner-split:planning-roster"));
    await page.reload();
    await page.getByRole("button", { name: "Finaler Dienstplan" }).click();
    const workload = page.locator('[data-split-pane="workload"]');
    await expect(page.getByRole("grid", { name: "Dienstplan" })).toBeVisible();
    await expect(workload).toBeVisible();
    const before = (await workload.boundingBox())?.width ?? 0;
    const divider = page.getByRole("separator", { name: "Breite der Arbeitslast ändern" });
    await divider.scrollIntoViewIfNeeded();
    const handle = await divider.boundingBox();
    expect(handle).not.toBeNull();
    if (!handle) {
      return;
    }
    const x = handle.x + handle.width / 2;
    const y = handle.y + Math.min(handle.height / 2, 80);
    await page.mouse.move(x, y);
    await page.mouse.down();
    await page.mouse.move(x - 60, y, { steps: 6 });
    await page.mouse.move(x - 120, y, { steps: 6 });
    await page.mouse.up();
    await expect.poll(async () => (await workload.boundingBox())?.width ?? 0).toBeGreaterThan(before + 10);
    const dragged = (await workload.boundingBox())?.width ?? 0;

    await page.reload();
    await page.getByRole("button", { name: "Finaler Dienstplan" }).click();
    await expect(workload).toBeVisible();
    await expect.poll(async () => Math.abs(((await workload.boundingBox())?.width ?? 0) - dragged)).toBeLessThan(3);

    const inspector = page.locator('[data-split-pane="inspector"]');
    await expect(inspector).toBeVisible();
    await page.getByRole("separator", { name: "Breite des Detailbereichs ändern" }).focus();
    await page.keyboard.press("Enter");
    await expect(inspector).toBeHidden();
  });

  test("passes axe with the separators on the roster tab", async ({ page, request }) => {
    const target = await planningTarget(request);
    await page.goto(planningPath(target));
    await page.getByRole("button", { name: "Finaler Dienstplan" }).click();
    await expect(page.getByRole("grid", { name: "Dienstplan" })).toBeVisible();
    await expect(page.getByRole("separator").first()).toBeVisible();
    const results = await new AxeBuilder({ page }).include("[role=grid]").include("[role=separator]").analyze();
    expect(results.violations).toEqual([]);
  });
});
