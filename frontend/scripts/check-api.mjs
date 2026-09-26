import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const temp = fs.mkdtempSync(path.join(os.tmpdir(), "shift-planner-api-"));
const openapi = path.join(temp, "openapi.json");
const schema = path.join(temp, "schema.d.ts");

execFileSync("node", [path.join(frontendRoot, "scripts/generate-api.mjs"), openapi, schema], {
  cwd: frontendRoot,
  stdio: "inherit"
});

function diff(committed, generated, label) {
  try {
    execFileSync("diff", ["-u", committed, generated], { stdio: "inherit" });
  } catch {
    console.error(`${label} drifted. Run npm run api:generate and commit frontend/lib/api/.`);
    process.exit(1);
  }
}

diff(path.join(frontendRoot, "lib/api/openapi.json"), openapi, "openapi.json");
diff(path.join(frontendRoot, "lib/api/schema.d.ts"), schema, "schema.d.ts");
