import {
  adminAuth,
  desktop,
  expect,
  memberAuth,
  phone,
  pinDashboardSections,
  plannerAuth,
  planningPath,
  planningTarget,
  shot,
  signOut,
  test
} from "./fixtures";

test.describe.configure({ mode: "serial" });

test.describe("planner", () => {
  test.use({ storageState: plannerAuth, viewport: desktop });

  test("switches wishes, roster, and analysis", async ({ page, request }) => {
    const target = await planningTarget(request);
    await page.goto(planningPath(target));
    await expect(page.getByRole("heading", { name: "Wünsche" })).toBeVisible();
    await expect(page.getByRole("table").first()).toBeVisible();
    await shot(page, "planning-wishes");

    await page.getByRole("button", { name: "Finaler Dienstplan" }).click();
    await expect(page.getByRole("heading", { name: "Finaler Dienstplan" })).toBeVisible();
    await expect(page.locator('button[aria-haspopup="listbox"]').first()).toBeVisible();
    await shot(page, "planning-roster");

    await page.getByRole("button", { name: "Analyse" }).click();
    await expect(page.getByRole("heading", { name: "Analyse" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Fairness" })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "Teammitglieder" }).first()).toBeVisible();
    await shot(page, "planning-analysis");
  });

  test("assigns a roster cell, reloads, and clears it", async ({ page, request }) => {
    const target = await planningTarget(request);
    await page.goto(planningPath(target));
    await page.getByRole("button", { name: "Finaler Dienstplan" }).click();
    await expect(page.locator('button[aria-haspopup="listbox"]').first()).toBeVisible();
    const name = await assignFirstOpenCell(page);
    await page.reload();
    await page.getByRole("button", { name: "Finaler Dienstplan" }).click();
    const cells = page.locator('button[aria-haspopup="listbox"]');
    await expect(cells.first()).toBeVisible();
    const assignedIndex = await indexOfCellText(page, name);
    expect(assignedIndex).toBeGreaterThanOrEqual(0);
    const assigned = cells.nth(assignedIndex);
    await assigned.scrollIntoViewIfNeeded();
    await assigned.click();
    const cleared = page.waitForResponse(
      (response) =>
        response.url().includes("/api/v1/roster-matrix/assignments/clear") &&
        response.request().method() === "POST"
    );
    await page.getByRole("listbox").getByRole("button", { name: "—", exact: true }).click();
    expect((await cleared).ok()).toBeTruthy();
    await expect(assigned).toHaveText("—");
    await page.reload();
    await page.getByRole("button", { name: "Finaler Dienstplan" }).click();
    await expect(cells.first()).toBeVisible();
    expect(await indexOfCellText(page, name)).toBe(-1);
  });
});

test.describe("admin", () => {
  test.use({ storageState: adminAuth, viewport: desktop });

  test("opens and closes a staff-directory row", async ({ page }) => {
    await page.goto("/organization/team");
    await expect(page.getByRole("heading", { name: "Teammitglieder" })).toBeVisible();
    const row = page.locator("tbody tr[role='button']").first();
    await expect(row).toBeVisible();
    await row.click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "Schließen" }).click();
    await expect(dialog).toBeHidden();
    await shot(page, "organization-team", [page.locator("span.font-mono")]);
  });

  test("shows the hours ledger", async ({ page }) => {
    await page.goto("/hours");
    await expect(page.getByRole("heading", { name: "Stundenkonto" })).toBeVisible();
    await expect(page.getByText("Anfangssaldo", { exact: true })).toBeVisible();
    await shot(page, "hours");
  });
});

test.describe("member", () => {
  test.use({ storageState: memberAuth, viewport: phone });

  test("shows wishes, roster, and my shifts", async ({ page, request }) => {
    const target = await planningTarget(request);
    await page.goto(planningPath(target, "/my-planning"));
    await expect(page.getByRole("heading", { name: "Wünsche" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Finaler Dienstplan" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Meine Schichten" })).toBeVisible();
    await page.getByRole("button", { name: "Finaler Dienstplan" }).click();
    await expect(page.getByRole("heading", { name: "Finaler Dienstplan" })).toBeVisible();
    await page.getByRole("button", { name: "Meine Schichten" }).click();
    await expect(page.getByRole("heading", { name: "Meine Schichten" })).toBeVisible();
    await page.getByRole("button", { name: "Wünsche" }).click();
    await expect(page.getByRole("heading", { name: "Wünsche" })).toBeVisible();
    await shot(page, "my-planning");
  });

  test("shows the member dashboard", async ({ page, request }) => {
    const target = await planningTarget(request);
    await page.goto(`/?shiftGroup=${target.shiftGroupId}`);
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await expect(page.getByText("Schichten (Jahr)", { exact: true })).toBeVisible();
    const sections = await pinDashboardSections(page);
    const yearSelect = page.getByRole("combobox", { name: "Jahr" });
    await shot(page, "member-dashboard", [...sections, yearSelect]);
  });
});

test.describe("admin signs out", () => {
  test.use({ storageState: adminAuth, viewport: desktop });

  test("signs out", async ({ page }) => {
    await page.goto("/");
    await signOut(page);
  });
});

test.describe("planner signs out", () => {
  test.use({ storageState: plannerAuth, viewport: desktop });

  test("signs out", async ({ page }) => {
    await page.goto("/planning");
    await signOut(page);
  });
});

test.describe("member signs out", () => {
  test.use({ storageState: memberAuth, viewport: desktop });

  test("signs out", async ({ page }) => {
    await page.goto("/my-planning");
    await signOut(page);
  });
});

async function indexOfCellText(page: import("@playwright/test").Page, text: string): Promise<number> {
  const cells = page.locator('button[aria-haspopup="listbox"]');
  const count = await cells.count();
  for (let index = 0; index < count; index += 1) {
    const current = (await cells.nth(index).innerText()).replace(/\s+/g, " ").trim();
    if (current.includes(text)) {
      return index;
    }
  }
  return -1;
}

async function assignFirstOpenCell(page: import("@playwright/test").Page): Promise<string> {
  const cells = page.locator('button[aria-haspopup="listbox"]');
  const count = await cells.count();
  let attempts = 0;
  for (let index = 0; index < count && attempts < 4; index += 1) {
    const cell = cells.nth(index);
    const current = (await cell.innerText()).replace(/\s+/g, " ").trim();
    if (current !== "—") {
      continue;
    }
    attempts += 1;
    await cell.scrollIntoViewIfNeeded();
    await cell.click();
    const listbox = page.getByRole("listbox");
    await expect(listbox).toBeVisible();
    const options = listbox.locator("button:has(span.font-medium)");
    const optionCount = Math.min(await options.count(), 6);
    for (let optionIndex = 0; optionIndex < optionCount; optionIndex += 1) {
      const option = options.nth(optionIndex);
      const label = (await option.innerText()).replace(/\s+/g, " ");
      if (label.includes("Konflikt")) {
        continue;
      }
      const name = (await option.locator("span.font-medium").innerText()).trim();
      if (!name) {
        continue;
      }
      const saved = page.waitForResponse(
        (response) =>
          response.url().includes("/api/v1/roster-matrix/assignments") &&
          response.request().method() === "PUT",
        { timeout: 8_000 }
      );
      await option.click();
      const response = await saved.catch(() => null);
      if (response?.ok()) {
        await expect(cell).toContainText(name);
        return name;
      }
      if (await page.getByRole("listbox").isHidden()) {
        await cell.click();
        await expect(listbox).toBeVisible();
      }
    }
    await page.keyboard.press("Escape");
  }
  throw new Error("No roster cell could be assigned");
}
