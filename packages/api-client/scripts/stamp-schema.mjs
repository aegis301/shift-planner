import fs from "node:fs";

const header = "/* generated, do not edit */\n";

export function stampSchema(filePath) {
  const body = fs.readFileSync(filePath, "utf8").replace(/^\/\* generated, do not edit \*\/\n/, "");
  fs.writeFileSync(filePath, header + body);
}
