// `pnpm inventory`: keeps FEATURE-INVENTORY.md honest (package U, step U1). The checks are in inventory-lib.ts.
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { listPageRoutes } from "./app-routes";
import {
  checkAllTestFilesListed,
  checkRoutes,
  checkTestIds,
  routeRows,
  testIds,
} from "./inventory-lib";

const FRONTEND = fileURLToPath(new URL("..", import.meta.url));
const TEST_FILE = /\.test\.tsx?$/;
const TEST_ROOTS = ["src", "mock"];

function testFilesUnder(dir: string): string[] {
  if (!existsSync(dir)) return [];
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === "node_modules" ? [] : testFilesUnder(full);
    return TEST_FILE.test(entry.name) ? [full] : [];
  });
}

function readOrNull(file: string): string | null {
  const full = join(FRONTEND, file);
  return existsSync(full) ? readFileSync(full, "utf8") : null;
}

const markdown = readFileSync(join(FRONTEND, "FEATURE-INVENTORY.md"), "utf8");
const rows = routeRows(markdown);
const ids = testIds(markdown);
const testFiles = TEST_ROOTS.flatMap((root) => testFilesUnder(join(FRONTEND, root))).map((f) =>
  relative(FRONTEND, f).replaceAll("\\", "/"),
);
const problems = [
  ...checkRoutes(rows, listPageRoutes(join(FRONTEND, "src/app"))),
  ...checkTestIds(ids, readOrNull),
  ...checkAllTestFilesListed(ids, testFiles),
];

if (problems.length > 0) {
  process.stderr.write(`${problems.join("\n")}\ninventory: ${problems.length} problem(s)\n`);
  process.exit(1);
}
process.stdout.write(
  `inventory: ${rows.length} routes, ${ids.length} test ids, ${testFiles.length} test files, all green\n`,
);
