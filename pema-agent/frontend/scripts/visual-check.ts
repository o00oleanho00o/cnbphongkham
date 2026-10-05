// `pnpm visual`: screenshots of every route of the app at the five project viewports, plus the check an exit
// code cannot say on its own: no document-level horizontal overflow (`scrollWidth > innerWidth`).
//
// Needs the app running against the mock backend:  pnpm dev:mock   (then, in another shell)  pnpm visual
//   VISUAL_BASE_URL=http://localhost:3000   where the app listens (default)
//   VISUAL_ROLE=owner                       which mock user signs in (owner, manager, doctor, cs, reception)
//   VISUAL_ROUTES=/today,/patients          limit to some routes (comma separated)
//   VISUAL_VIEWPORTS=1920x1020,390x844      limit to some viewports
//   VISUAL_SCHEME=dark                      take the dark-mode screenshots (files get a -dark suffix)
//
// Routes come from `src/app/**/page.tsx`, the same list the navigation test uses; dynamic routes get sample ids
// of the mock data (`SAMPLE_PARAMS`). `/dev/*` (the kit examples) is left out. Output:
//   visual-ref/new/<viewport>-<route>.png   one image per screen and viewport (git-ignored)
//   visual-ref/new/summary.json             per screen: viewport, route, overflow px, HTTP status, errors
// Reference images of the old web live in visual-ref/old (see its README).
import { mkdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { chromium, type Page } from "playwright";

import { EXTRA_VISUAL_ROUTES, concreteRoute, listPageRoutes } from "./app-routes";

const BASE = process.env.VISUAL_BASE_URL ?? "http://localhost:3000";
const ROLE = process.env.VISUAL_ROLE ?? "owner";
const DARK = process.env.VISUAL_SCHEME === "dark";
const OUT = fileURLToPath(new URL("../visual-ref/new", import.meta.url));
const APP_DIR = fileURLToPath(new URL("../src/app", import.meta.url));

const VIEWPORTS = [
  { name: "1920x1020", width: 1920, height: 1020 },
  { name: "1440x900", width: 1440, height: 900 },
  { name: "1280x720", width: 1280, height: 720 },
  { name: "1024x768", width: 1024, height: 768 },
  { name: "390x844", width: 390, height: 844 },
] as const;

const EMAIL: Record<string, string> = {
  owner: "owner@pema.test",
  manager: "manager@pema.test",
  doctor: "doctor@pema.test",
  cs: "cs@pema.test",
  reception: "reception@pema.test",
};

type Row = {
  viewport: string;
  route: string;
  file: string;
  overflowPx: number;
  status: number;
  errors: string[];
};

const fileSlug = (route: string): string =>
  route.replace(/[^a-z0-9]+/gi, "_").replace(/^_|_$/g, "") || "root";

function selectedRoutes(): string[] {
  const only = process.env.VISUAL_ROUTES?.split(",").filter(Boolean) ?? [];
  if (only.length > 0) return only;
  return listPageRoutes(APP_DIR)
    .filter((route) => !route.startsWith("/dev"))
    .filter((route) => route !== "/login")
    .map(concreteRoute)
    .concat(EXTRA_VISUAL_ROUTES);
}

async function signIn(page: Page): Promise<void> {
  await page.goto(`${BASE}/login`);
  await page.fill("#email", EMAIL[ROLE] ?? EMAIL["owner"] ?? "");
  await page.fill("#password", "demo1234");
  await Promise.all([
    page.waitForURL((url) => !url.pathname.startsWith("/login")),
    page.click("button[type=submit]"),
  ]);
}

async function captureRoute(
  page: Page,
  viewport: string,
  route: string,
  errors: string[],
): Promise<Row> {
  errors.length = 0;
  // "load", not "networkidle": the live event stream (SSE) is a request that never ends.
  const response = await page.goto(`${BASE}${route}`, { waitUntil: "load" });
  await page.waitForTimeout(1200);
  const overflowPx = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  const file = `${viewport}-${fileSlug(route)}${DARK ? "-dark" : ""}.png`;
  await page.screenshot({ path: `${OUT}/${file}` });
  return {
    viewport,
    route,
    file,
    overflowPx,
    status: response?.status() ?? 0,
    errors: [...errors],
  };
}

async function captureViewport(
  browser: Awaited<ReturnType<typeof chromium.launch>>,
  viewport: (typeof VIEWPORTS)[number],
  routes: string[],
): Promise<Row[]> {
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
    colorScheme: DARK ? "dark" : "light",
  });
  const page = await context.newPage();
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(`console: ${m.text()}`);
  });
  await signIn(page);
  // One page, routes in sequence: the session cookie and the dev server's compile cache are shared.
  const rows = await routes.reduce<Promise<Row[]>>(async (previous, route) => {
    const done = await previous;
    return [...done, await captureRoute(page, viewport.name, route, errors)];
  }, Promise.resolve([]));
  await context.close();
  return rows;
}

const isFailure = (row: Row): boolean =>
  row.overflowPx > 0 || row.status >= 400 || row.errors.length > 0;

async function main(): Promise<void> {
  const onlyViewports = process.env.VISUAL_VIEWPORTS?.split(",").filter(Boolean) ?? [];
  const viewports = VIEWPORTS.filter(
    (v) => onlyViewports.length === 0 || onlyViewports.includes(v.name),
  );
  const routes = selectedRoutes();
  mkdirSync(OUT, { recursive: true });

  const browser = await chromium.launch();
  const perViewport = await viewports.reduce<Promise<Row[][]>>(async (previous, viewport) => {
    const done = await previous;
    return [...done, await captureViewport(browser, viewport, routes)];
  }, Promise.resolve([]));
  await browser.close();

  const rows = perViewport.flat();
  const failures = rows.filter(isFailure);
  writeFileSync(
    `${OUT}/summary.json`,
    `${JSON.stringify(
      {
        base: BASE,
        role: ROLE,
        screens: rows.length,
        routes: routes.length,
        viewports: viewports.map((v) => v.name),
        overflowFailures: rows.filter((r) => r.overflowPx > 0).length,
        failures,
        rows,
      },
      null,
      2,
    )}\n`,
  );
  process.stdout.write(
    `${rows.length} screens (${routes.length} routes x ${viewports.length} viewports), ` +
      `${rows.filter((r) => r.overflowPx > 0).length} with horizontal overflow, ${failures.length} failing\n`,
  );
  failures.forEach((r) =>
    process.stdout.write(
      `  ${r.viewport} ${r.route}: overflow ${r.overflowPx}px, HTTP ${r.status}${r.errors.length > 0 ? `, ${r.errors.join(" | ")}` : ""}\n`,
    ),
  );
  process.exitCode = failures.length === 0 ? 0 : 1;
}

await main();
