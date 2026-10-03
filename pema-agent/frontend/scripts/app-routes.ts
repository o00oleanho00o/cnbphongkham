// Lists the routes of the App Router tree (`src/app/**/page.tsx`). Shared by the visual harness and by the
// navigation test, so "every screen" means the same thing in both.
import { readdirSync } from "node:fs";
import { join } from "node:path";

const PAGE_FILE = "page.tsx";

/** `(admin)/patients/[id]/page.tsx` -> `/patients/[id]` (route groups vanish, the root is `/`). */
export function routeOfPageFile(relativePath: string): string {
  const segments = relativePath
    .split(/[\\/]/)
    .slice(0, -1)
    .filter((segment) => !(segment.startsWith("(") && segment.endsWith(")")));
  return `/${segments.join("/")}`;
}

function pageFilesUnder(dir: string, prefix: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const relative = prefix === "" ? entry.name : join(prefix, entry.name);
    if (entry.isDirectory()) return pageFilesUnder(join(dir, entry.name), relative);
    return entry.name === PAGE_FILE ? [relative] : [];
  });
}

/** Every page route, sorted; dynamic segments stay as `[param]`. */
export function listPageRoutes(appDir: string): string[] {
  return pageFilesUnder(appDir, "")
    .map(routeOfPageFile)
    .toSorted((a, b) => a.localeCompare(b));
}

export const isDynamicRoute = (route: string): boolean => route.includes("[");

/** Sample values (ids of the mock backend data) for the dynamic segments of the routes. */
export const SAMPLE_PARAMS: Readonly<Record<string, string>> = {
  "/patients/[id]": "/patients/00000000-0000-4000-8002-000000000001",
  "/care/patients/[id]": "/care/patients/00000000-0000-4000-8002-000000000007",
  "/care/patients/[id]/release": "/care/patients/00000000-0000-4000-8002-000000000007/release",
  "/care/patients/[id]/tell-agent":
    "/care/patients/00000000-0000-4000-8002-000000000007/tell-agent",
  "/care/patients/[id]/timeline": "/care/patients/00000000-0000-4000-8002-000000000007/timeline",
  "/admin/agents/[id]": "/admin/agents/cskh-da-lieu",
  "/admin/tuning/[group]": "/admin/tuning/agent",
};

/** The URL to open for a route: itself, or the sample of its dynamic segments. */
export function concreteRoute(route: string): string {
  if (!isDynamicRoute(route)) return route;
  const sample = SAMPLE_PARAMS[route];
  if (sample === undefined) throw new Error(`no sample ids for ${route}: add it to SAMPLE_PARAMS`);
  return sample;
}

/** Screens that are a state of one route, not a route of their own (a tab kept in `?tab=`): the visual harness opens them too. */
export const EXTRA_VISUAL_ROUTES: readonly string[] = ["consult", "plan", "session", "photos"].map(
  (tab) => `/patients/00000000-0000-4000-8002-000000000001?tab=${tab}`,
);
