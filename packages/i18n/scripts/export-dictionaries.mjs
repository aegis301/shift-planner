import { writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const { dictionaries } = await import(path.join(packageRoot, "../../frontend/lib/i18n.ts"));
writeFileSync(path.join(packageRoot, "de.json"), `${JSON.stringify(dictionaries.de, null, 2)}\n`);
writeFileSync(path.join(packageRoot, "en.json"), `${JSON.stringify(dictionaries.en, null, 2)}\n`);
