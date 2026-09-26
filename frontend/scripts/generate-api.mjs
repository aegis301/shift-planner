import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { stampSchema } from "./stamp-schema.mjs";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(frontendRoot, "..");
const openapiPath = path.join(frontendRoot, "lib/api/openapi.json");
const schemaPath = path.join(frontendRoot, "lib/api/schema.d.ts");

function exportOpenApi(destination) {
  const backend = path.join(repoRoot, "backend");
  try {
    execFileSync("python", ["-c", "import app"], {
      cwd: backend,
      stdio: "ignore"
    });
    const json = execFileSync("python", ["-m", "app.scripts.export_openapi"], {
      cwd: backend,
      encoding: "utf8"
    });
    fs.writeFileSync(destination, json);
    return;
  } catch {
    // Fall through to Compose when the local interpreter cannot import the app.
  }
  const json = execFileSync(
    "docker",
    ["compose", "-f", path.join(repoRoot, "docker-compose.yml"), "exec", "-T", "backend", "python", "-m", "app.scripts.export_openapi"],
    { cwd: repoRoot, encoding: "utf8" }
  );
  fs.writeFileSync(destination, json);
}

const outOpenApi = process.argv[2] ?? openapiPath;
const outSchema = process.argv[3] ?? schemaPath;
fs.mkdirSync(path.dirname(outOpenApi), { recursive: true });
fs.mkdirSync(path.dirname(outSchema), { recursive: true });
exportOpenApi(outOpenApi);
execFileSync("npx", ["openapi-typescript", outOpenApi, "-o", outSchema], {
  cwd: frontendRoot,
  stdio: "inherit"
});
stampSchema(outSchema);
