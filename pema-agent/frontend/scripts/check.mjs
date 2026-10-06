// `pnpm check`: everything that has to be green before a change to the staff web is reported (package U, U1):
// lint, types, formatting, unit tests, the feature inventory, then the two browser checks (`pnpm smoke`: every
// route renders; `pnpm visual`: five viewports, no horizontal overflow) against the app on CHECK_BASE_URL
// (default http://localhost:3000, i.e. `pnpm dev:mock` in another shell). The browser checks need that app: when
// it does not answer, `pnpm check` FAILS and says so. `CHECK_SKIP_BROWSER=1` leaves them out on purpose
// (a machine without a browser); the report of a step must then say they were not run.
import { spawnSync } from "node:child_process";

const base = process.env.CHECK_BASE_URL ?? "http://localhost:3000";

const STATIC_STEPS = ["lint", "typecheck", "format:check", "test", "inventory"];
const BROWSER_STEPS = ["smoke", "visual"];

function run(script) {
  process.stdout.write(`\n== pnpm ${script}\n`);
  const result = spawnSync("pnpm", [script], {
    stdio: "inherit",
    shell: true,
    env: { ...process.env, SMOKE_BASE_URL: base, VISUAL_BASE_URL: base },
  });
  return result.status === 0;
}

async function appAnswers() {
  try {
    const response = await fetch(`${base}/healthz`, { signal: AbortSignal.timeout(5000) });
    return response.status < 500;
  } catch {
    return false;
  }
}

const failedStatic = STATIC_STEPS.filter((script) => !run(script));
if (failedStatic.length > 0) {
  process.stderr.write(`\ncheck: failed: ${failedStatic.join(", ")}\n`);
  process.exit(1);
}

if (process.env.CHECK_SKIP_BROWSER === "1") {
  process.stdout.write(
    "\ncheck: static steps green; browser steps skipped (CHECK_SKIP_BROWSER=1)\n",
  );
  process.exit(0);
}
if (!(await appAnswers())) {
  process.stderr.write(
    `\ncheck: nothing answers on ${base}: start \`pnpm dev:mock\` (or set CHECK_SKIP_BROWSER=1)\n`,
  );
  process.exit(1);
}
const failedBrowser = BROWSER_STEPS.filter((script) => !run(script));
if (failedBrowser.length > 0) {
  process.stderr.write(`\ncheck: failed: ${failedBrowser.join(", ")}\n`);
  process.exit(1);
}
process.stdout.write("\ncheck: all green\n");
