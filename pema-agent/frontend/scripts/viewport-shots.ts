// `pnpm shots`: screenshots of every screen at the five project viewports (AGENT.md: 1920x1020, 1440x900,
// 1280x720, 1024x768, 390x844) against `pnpm dev:mock`. It also reports what an exit code cannot say:
// page errors, console errors, failed requests, and any document-level horizontal overflow.
//
//   SHOTS_BASE_URL=http://localhost:3000 SHOTS_ROLE=owner SHOTS_ROUTES=/today,/review pnpm shots
//   (SHOTS_VIEWPORTS=390x844,1440x900 limits the viewports)
import { mkdirSync } from "node:fs";

import { chromium, type Page } from "playwright";

const BASE = process.env.SHOTS_BASE_URL ?? "http://localhost:3000";
const OUT = process.env.SHOTS_DIR ?? "shots";
const ROLE = process.env.SHOTS_ROLE ?? "owner";

const VIEWPORTS = [
  { name: "1920x1020", width: 1920, height: 1020 },
  { name: "1440x900", width: 1440, height: 900 },
  { name: "1280x720", width: 1280, height: 720 },
  { name: "1024x768", width: 1024, height: 768 },
  { name: "390x844", width: 390, height: 844 },
] as const;

const ROUTES = [
  "/today",
  "/inbox",
  "/inbox?c=00000000-0000-4000-8007-000000000001",
  "/review",
  "/review?i=00000000-0000-4000-8009-000000000001",
  "/patients",
  "/patients/00000000-0000-4000-8002-000000000001",
  "/templates",
  "/admin/overview",
  "/admin/threads",
  "/admin/contacts",
  "/admin/friends",
  "/admin/schedules",
  "/admin/memory",
  "/admin/kb",
  "/admin/accounts",
  "/admin/agents",
  "/admin/agents/cskh-da-lieu",
  "/admin/tools",
  "/admin/mcp",
  "/admin/traces",
  "/admin/logs",
  "/admin/tuning/agent",
  "/admin/tuning/providers",
  "/admin/policy",
  "/admin/users",
  "/admin/auth",
];

const EMAIL: Record<string, string> = {
  owner: "owner@pema.test",
  manager: "manager@pema.test",
  doctor: "doctor@pema.test",
  cs: "cs@pema.test",
  reception: "reception@pema.test",
};

async function signIn(page: Page): Promise<void> {
  await page.goto(`${BASE}/login`);
  await page.fill("#email", EMAIL[ROLE] ?? EMAIL.owner ?? "");
  await page.fill("#password", "demo1234");
  await Promise.all([
    page.waitForURL((url) => !url.pathname.startsWith("/login")),
    page.click("button[type=submit]"),
  ]);
}

const slug = (route: string): string =>
  route.replace(/[^a-z0-9]+/gi, "_").replace(/^_|_$/g, "") || "root";

async function main(): Promise<void> {
  // comma separated, from the environment: MSYS shells on Windows rewrite a bare `/today` argument into a path
  const only = process.env.SHOTS_ROUTES?.split(",").filter(Boolean) ?? [];
  const routes = only.length > 0 ? only : ROUTES;
  const browser = await chromium.launch();
  const problems: string[] = [];

  // optional, e.g. SHOTS_VIEWPORTS=390x844,1440x900
  const onlyViewports = process.env.SHOTS_VIEWPORTS?.split(",").filter(Boolean) ?? [];
  const viewports = VIEWPORTS.filter(
    (v) => onlyViewports.length === 0 || onlyViewports.includes(v.name),
  );

  for (const vp of viewports) {
    const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
    const page = await context.newPage();
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(`console: ${m.text()}`);
    });
    page.on("response", (r) => {
      if (r.status() >= 500) errors.push(`http ${r.status()} ${r.url()}`);
    });
    await signIn(page);
    mkdirSync(`${OUT}/${ROLE}/${vp.name}`, { recursive: true });

    for (const route of routes) {
      errors.length = 0;
      // "load", not "networkidle": the live event stream (SSE) is a request that never ends.
      await page.goto(`${BASE}${route}`, { waitUntil: "load" });
      await page.waitForTimeout(1200);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      await page.screenshot({ path: `${OUT}/${ROLE}/${vp.name}/${slug(route)}.png` });
      if (overflow > 0) problems.push(`${vp.name} ${route}: document overflows by ${overflow}px`);
      errors.forEach((e) => problems.push(`${vp.name} ${route}: ${e}`));
    }
    await context.close();
  }

  await browser.close();
  process.stdout.write(
    problems.length === 0 ? "no overflow, no errors\n" : `${problems.join("\n")}\n`,
  );
  process.exitCode = problems.length === 0 ? 0 : 1;
}

await main();
