import fs from "node:fs";
import path from "node:path";
import { request, type FullConfig } from "@playwright/test";

const roles = [
  ["admin", "e2e-admin@example.com"],
  ["planner", "e2e-planner@example.com"],
  ["member", "e2e-member@example.com"]
] as const;

export const authDir = path.join(__dirname, ".auth");

export function authFile(role: (typeof roles)[number][0]): string {
  return path.join(authDir, `${role}.json`);
}

async function writeSession(
  baseURL: string,
  cookieDomain: string,
  email: string,
  password: string,
  file: string
): Promise<boolean> {
  const context = await request.newContext({ baseURL });
  try {
    const response = await context.post("/api/v1/auth/login", {
      data: { email, password }
    });
    if (!response.ok()) {
      throw new Error(`Login failed for ${email}: ${response.status()} ${await response.text()}`);
    }
    const state = await context.storageState();
    const cookie = state.cookies.find((item) => item.name === "shift_planner_session");
    if (!cookie) {
      return false;
    }
    fs.writeFileSync(
      file,
      JSON.stringify(
        {
          cookies: [
            {
              ...cookie,
              domain: cookieDomain,
              secure: false,
              sameSite: cookie.sameSite === "Strict" || cookie.sameSite === "None" ? cookie.sameSite : "Lax"
            }
          ],
          origins: []
        },
        null,
        2
      )
    );
    return true;
  } finally {
    await context.dispose();
  }
}

export default async function globalSetup(config: FullConfig): Promise<void> {
  const password = process.env.E2E_SEED_PASSWORD?.trim() ?? "";
  if (!password) {
    throw new Error("E2E_SEED_PASSWORD is required");
  }
  const baseURL = String(config.projects[0]?.use.baseURL ?? "http://localhost:18130");
  const apiURL = process.env.E2E_API_URL ?? "http://localhost:18180";
  const cookieDomain = new URL(baseURL).hostname;
  fs.mkdirSync(authDir, { recursive: true });
  for (const [role, email] of roles) {
    const file = authFile(role);
    const saved = await writeSession(baseURL, cookieDomain, email, password, file);
    if (!saved) {
      const savedFromApi = await writeSession(apiURL, cookieDomain, email, password, file);
      if (!savedFromApi) {
        throw new Error(`Login for ${email} did not set shift_planner_session`);
      }
    }
  }
}
