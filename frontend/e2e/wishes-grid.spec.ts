import { expect, plannerAuth, planningPath, planningTarget, test, desktop } from "./fixtures";

test.describe("wishes grid", () => {
  test.use({ storageState: plannerAuth, viewport: desktop });

  test("sets a status over a range with one bulk request", async ({ page, request }) => {
    const target = await planningTarget(request);
    await page.goto(planningPath(target));
    const grid = page.getByRole("grid", { name: "Wünsche" });
    await expect(grid).toBeVisible();
    await grid.getByRole("gridcell").first().focus();
    await page.keyboard.press("Shift+ArrowDown");
    await page.keyboard.press("u");
    await expect(page.getByRole("listbox")).toBeVisible();
    await page.keyboard.press("r");
    const bulks: string[] = [];
    page.on("request", (req) => {
      if (req.method() === "PUT" && req.url().includes("/cells/bulk")) {
        bulks.push(req.postData() ?? "");
      }
    });
    await page.keyboard.press("Enter");
    await expect.poll(() => bulks.length).toBe(1);
    const body = JSON.parse(bulks[0] ?? "{}") as { cells?: { status?: string }[] };
    expect(body.cells).toHaveLength(2);
    expect(body.cells?.every((cell) => cell.status === "urlaub")).toBeTruthy();
    expect(bulks[0]).not.toContain("expected_updated_at");
  });

  test("pastes status codes from a TSV", async ({ page, request, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    const target = await planningTarget(request);
    await page.goto(planningPath(target));
    const grid = page.getByRole("grid", { name: "Wünsche" });
    const cell = grid.getByRole("gridcell").nth(2);
    await cell.focus();
    await page.evaluate(() => navigator.clipboard.writeText("frei\nlehre"));
    const bulks: string[] = [];
    page.on("request", (req) => {
      if (req.method() === "PUT" && req.url().includes("/cells/bulk")) {
        bulks.push(req.postData() ?? "");
      }
    });
    await page.keyboard.press("Control+v");
    await expect.poll(() => bulks.length).toBe(1);
    const body = JSON.parse(bulks[0] ?? "{}") as { cells?: { status?: string }[] };
    expect(body.cells?.map((row) => row.status)).toEqual(["frei", "lehre"]);
  });

  test("undoes and redoes a status edit", async ({ page, request }) => {
    const target = await planningTarget(request);
    await page.goto(planningPath(target));
    const grid = page.getByRole("grid", { name: "Wünsche" });
    const cell = grid.getByRole("gridcell").nth(4);
    await cell.focus();
    const cleared = page.waitForResponse(
      (response) => response.url().includes("/cells/clear") && response.request().method() === "POST"
    );
    await page.keyboard.press("Delete");
    expect((await cleared).ok()).toBeTruthy();
    await cell.focus();
    await page.keyboard.press("u");
    await expect(page.getByRole("listbox")).toBeVisible();
    const saved = page.waitForResponse(
      (response) => response.url().includes("/cells/bulk") && response.request().method() === "PUT"
    );
    await page.keyboard.press("r");
    await page.keyboard.press("Enter");
    expect((await saved).ok()).toBeTruthy();
    await cell.focus();
    const undone = page.waitForResponse((response) => wishesWrite(response));
    await page.keyboard.press("Control+z");
    const undoBody = (await undone).request().postDataJSON() as { cells?: { expected_updated_at?: string }[] };
    expect(undoBody.cells?.[0]?.expected_updated_at).toBeTruthy();
    await expect(cell).not.toContainText("Urlaub");
    await cell.focus();
    const redone = page.waitForResponse(
      (response) => response.url().includes("/cells/bulk") && response.request().method() === "PUT"
    );
    await page.keyboard.press("Control+y");
    expect((await redone).ok()).toBeTruthy();
    await expect(cell).toContainText("Urlaub");
  });

  test("skips a cell another write changed", async ({ page, request }) => {
    const target = await planningTarget(request);
    await page.goto(planningPath(target));
    const grid = page.getByRole("grid", { name: "Wünsche" });
    const cell = grid.getByRole("gridcell").nth(6);
    await cell.focus();
    await page.keyboard.press("Shift+ArrowDown");
    await page.keyboard.press("u");
    const saved = page.waitForResponse(
      (response) => response.url().includes("/cells/bulk") && response.request().method() === "PUT"
    );
    await page.keyboard.press("r");
    await page.keyboard.press("Enter");
    const savedResponse = await saved;
    const requestBody = savedResponse.request().postDataJSON() as { cells: { team_member_id: number; cell_date: string }[] };
    const first = requestBody.cells[0];
    expect(first).toBeTruthy();
    const overwrite = await page.request.put(
      `/api/v1/matrix/${target.periodId}/cells/bulk?shift_group_id=${target.shiftGroupId}`,
      {
        data: {
          cells: [{ team_member_id: first.team_member_id, cell_date: first.cell_date, status: "lehre" }]
        }
      }
    );
    expect(overwrite.ok()).toBeTruthy();
    await cell.focus();
    const undone = page.waitForResponse((response) => wishesWrite(response));
    await page.keyboard.press("Control+z");
    const undoResponse = await undone;
    const undoJson = (await undoResponse.json()) as { conflicts?: { cell_date: string }[] };
    expect(undoJson.conflicts?.some((row) => row.cell_date === first.cell_date)).toBeTruthy();
    await expect(page.getByText("geänderte Zellen wurden übersprungen")).toBeVisible();
  });

  test("keeps a published group read-only", async ({ page, request }) => {
    const target = await planningTarget(request);
    await page.route("**/api/v1/matrix/**", async (route) => {
      if (route.request().method() !== "GET" || route.request().url().includes("/notes")) {
        await route.continue();
        return;
      }
      const response = await route.fetch();
      const json = (await response.json()) as { shift_group_planning_status?: { status?: string } | null };
      json.shift_group_planning_status = { ...(json.shift_group_planning_status ?? {}), status: "published" };
      await route.fulfill({ response, json });
    });
    await page.route("**/api/v1/roster-matrix/**", async (route) => {
      const url = route.request().url();
      if (route.request().method() !== "GET" || url.includes("/change-sets") || url.includes("/candidates")) {
        await route.continue();
        return;
      }
      const response = await route.fetch();
      const json = (await response.json()) as { shift_group_planning_status?: { status?: string } | null };
      json.shift_group_planning_status = { ...(json.shift_group_planning_status ?? {}), status: "published" };
      await route.fulfill({ response, json });
    });
    await page.goto(planningPath(target));
    const reason = "Die Wünsche sind schreibgeschützt, weil diese Dienstgruppe veröffentlicht ist.";
    await expect(page.getByText(reason)).toBeVisible();
    const grid = page.getByRole("grid", { name: "Wünsche" });
    await grid.getByRole("gridcell").first().focus();
    let writes = 0;
    page.on("request", (req) => {
      if (req.method() === "PUT" && req.url().includes("/cells/bulk")) {
        writes += 1;
      }
    });
    await page.keyboard.press("u");
    await expect(page.getByRole("listbox")).toHaveCount(0);
    expect(writes).toBe(0);
  });
});

function wishesWrite(response: { url: () => string; request: () => { method: () => string } }): boolean {
  const url = response.url();
  const method = response.request().method();
  return (method === "PUT" && url.includes("/cells/bulk")) || (method === "POST" && url.includes("/cells/clear"));
}
