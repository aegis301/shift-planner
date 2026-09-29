import {
  adminAuth,
  desktop,
  expect,
  memberAuth,
  phone,
  plannerAuth,
  planningPath,
  planningTarget,
  signOut,
  test
} from "./fixtures";

test.describe("planner screenshots", () => {
  test.use({ storageState: plannerAuth, viewport: desktop });

  test("shows the wishes matrix", async ({ page, request }) => {
    const target = await planningTarget(request);
    await page.goto(planningPath(target));
    await expect(page.getByRole("heading", { name: "Wünsche" })).toBeVisible();
    await expect(page.getByRole("table").first()).toBeVisible();
  });

  test("shows the roster", async ({ page, request }) => {
    const target = await planningTarget(request);
    await page.goto(planningPath(target));
    await page.getByRole("button", { name: "Finaler Dienstplan" }).click();
    await expect(page.getByRole("heading", { name: "Finaler Dienstplan" })).toBeVisible();
    await expect(page.locator('button[aria-haspopup="listbox"]').first()).toBeVisible();
  });

  test("shows the analysis", async ({ page, request }) => {
    const target = await planningTarget(request);
    await page.goto(planningPath(target));
    await page.getByRole("button", { name: "Analyse" }).click();
    await expect(page.getByRole("heading", { name: "Analyse" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Fairness" })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "Teammitglieder" }).first()).toBeVisible();
  });
});

test.describe("planner", () => {
  test.use({ storageState: plannerAuth, viewport: desktop });

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

  test("loads each planning resource once", async ({ page, request }) => {
    const target = await planningTarget(request);
    const counts = { roster: 0, wishes: 0, validation: 0, fairness: 0 };
    page.on("request", (req) => {
      if (req.method() !== "GET") {
        return;
      }
      const url = req.url();
      if (/\/api\/v1\/roster-matrix\/\d+/.test(url) && !url.includes("/change-sets")) {
        counts.roster += 1;
      } else if (/\/api\/v1\/matrix\/\d+(\?|$)/.test(url)) {
        counts.wishes += 1;
      } else if (/\/api\/v1\/validation\/\d+/.test(url)) {
        counts.validation += 1;
      } else if (/\/api\/v1\/fairness\/\d+/.test(url)) {
        counts.fairness += 1;
      }
    });
    await page.goto(planningPath(target));
    await expect(page.getByRole("heading", { name: "Wünsche" })).toBeVisible();
    await page.getByRole("button", { name: "Finaler Dienstplan" }).click();
    await expect(page.locator('button[aria-haspopup="listbox"]').first()).toBeVisible();
    await page.getByRole("button", { name: "Analyse" }).click();
    await expect(page.getByRole("heading", { name: "Fairness" })).toBeVisible();
    expect(counts.roster).toBeLessThanOrEqual(1);
    expect(counts.wishes).toBeLessThanOrEqual(1);
    expect(counts.validation).toBeLessThanOrEqual(1);
    expect(counts.fairness).toBeLessThanOrEqual(1);
    expect(counts.roster).toBeGreaterThan(0);
    expect(counts.wishes).toBeGreaterThan(0);
  });

  test("rolls back a refused roster assignment", async ({ page, request }) => {
    const target = await planningTarget(request);
    await page.route("**/api/v1/roster-matrix/assignments?**", async (route) => {
      if (route.request().method() === "PUT") {
        await route.fulfill({
          status: 400,
          contentType: "application/json",
          body: JSON.stringify({ detail: "No-Go" })
        });
        return;
      }
      await route.continue();
    });
    await page.goto(planningPath(target));
    await page.getByRole("button", { name: "Finaler Dienstplan" }).click();
    const cell = page.locator('button[aria-haspopup="listbox"]', { hasText: "—" }).first();
    await cell.scrollIntoViewIfNeeded();
    await cell.click();
    const option = page.getByRole("listbox").getByRole("option").first();
    await option.click();
    await expect(page.getByText("No-Go")).toBeVisible();
    await expect(cell).toHaveText("—");
  });

  test("shows slot candidates in the inspector and restores a deep link", async ({ page, request }) => {
    const target = await planningTarget(request);
    await page.goto(planningPath(target));
    await expect(page.locator("[data-slot='workbench-context-bar']")).toBeVisible();
    await page.getByRole("button", { name: "Finaler Dienstplan" }).click();
    const cell = page.locator('button[aria-haspopup="listbox"]').first();
    await cell.click();
    await expect(page.getByRole("heading", { name: "Kann den Dienst übernehmen" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Blockiert" })).toBeVisible();
    const url = new URL(page.url());
    expect(url.searchParams.get("slot")).toBeTruthy();
    await page.reload();
    await expect(page.getByRole("heading", { name: "Kann den Dienst übernehmen" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Blockiert" })).toBeVisible();
    await page.keyboard.press("Control+K");
    await expect(page.getByPlaceholder("Seite, Person oder Aktion suchen")).toBeVisible();
  });

  test("keeps the density choice after reload", async ({ page }) => {
    await page.goto("/planning");
    await page.getByRole("button", { name: "Konto und Einstellungen" }).click();
    await page.getByRole("menuitem", { name: /Dichte/ }).click();
    await expect.poll(() => page.evaluate(() => document.documentElement.dataset.density)).toBe("compact");
    await page.reload();
    await expect.poll(() => page.evaluate(() => document.documentElement.dataset.density)).toBe("compact");
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
  });

  test("shows the hours ledger", async ({ page }) => {
    await page.goto("/hours");
    await expect(page.getByRole("heading", { level: 1, name: "Stundenkonto" })).toBeVisible();
    await expect(page.getByText("Anfangssaldo", { exact: true })).toBeVisible();
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
  });

  test("shows the member dashboard", async ({ page, request }) => {
    const target = await planningTarget(request);
    await page.goto(`/my?shiftGroup=${target.shiftGroupId}`);
    await expect(page.getByRole("heading", { name: "Mein Bereich" })).toBeVisible();
    await expect(page.getByText("Schichten (Jahr)", { exact: true })).toBeVisible();
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

test.describe("routes", () => {
  test.use({ storageState: adminAuth, viewport: desktop });

  test("keeps the existing workbench URLs", async ({ page }) => {
    for (const path of ["/planning", "/hours", "/organization/team", "/organization/shifts/groups", "/shift-groups", "/shift-types", "/organization/users", "/organization/team/members"]) {
      await page.goto(path);
      await expect(page.getByRole("heading").first()).toBeVisible();
    }
  });
});

test.describe("member home", () => {
  test.use({ storageState: memberAuth, viewport: phone });

  test("redirects / to /my and keeps the page within the viewport", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/my$/);
    await expect(page.getByRole("heading", { name: "Mein Bereich" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Start" })).toBeVisible();
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(scrollWidth).toBeLessThanOrEqual(390);
  });
});

test.describe("dual role", () => {
  test.use({ storageState: plannerAuth, viewport: desktop });

  test("switches between the workbench and the member area", async ({ page }) => {
    await page.goto("/planning");
    await page.getByRole("button", { name: "Konto und Einstellungen" }).click();
    await page.getByRole("menuitem", { name: "Mitgliederbereich" }).click();
    await expect(page).toHaveURL(/\/my$/);
    await page.getByRole("button", { name: "Konto und Einstellungen" }).click();
    await page.getByRole("menuitem", { name: "Planungsbereich" }).click();
    await expect(page).toHaveURL(/\/planning/);
  });
});

test.describe("narrow workbench", () => {
  test.use({ storageState: plannerAuth, viewport: { width: 1000, height: 800 } });

  test("shows the narrow-screen notice", async ({ page }) => {
    await page.goto("/planning");
    await expect(page.getByText("Dieser Bereich ist für größere Bildschirme gedacht.")).toBeVisible();
    await page.getByRole("button", { name: "Trotzdem weiter" }).click();
    await expect(page.getByText("Dieser Bereich ist für größere Bildschirme gedacht.")).toBeHidden();
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
    const options = listbox.getByRole("option");
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
