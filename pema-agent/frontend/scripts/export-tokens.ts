// `pnpm tokens`: regenerate src/ui/tokens.json from src/ui/tokens.css (the KMP app reads the JSON).
// `pnpm tokens --check` only compares and exits 1 when the committed JSON is stale.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { renderTokensJson } from "../src/ui/tokens-export";

const cssPath = fileURLToPath(new URL("../src/ui/tokens.css", import.meta.url));
const jsonPath = fileURLToPath(new URL("../src/ui/tokens.json", import.meta.url));

const next = renderTokensJson(readFileSync(cssPath, "utf8"));

if (process.argv.includes("--check")) {
  let current = "";
  try {
    current = readFileSync(jsonPath, "utf8");
  } catch {
    current = "";
  }
  if (current !== next) {
    process.stderr.write("tokens.json is out of date: run `pnpm tokens`\n");
    process.exitCode = 1;
  }
} else {
  writeFileSync(jsonPath, next);
  process.stdout.write("tokens.json written\n");
}
