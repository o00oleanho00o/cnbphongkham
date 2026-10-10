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
  "/orders/[id]": "/orders/00000000-0000-4000-8041-000000000001",
  "/orders/[id]/print": "/orders/00000000-0000-4000-8041-000000000002/print",
  "/admin/agent/plugins/[name]": "/admin/agent/plugins/zalo",
  "/admin/agent/plugins/[name]/[page]": "/admin/agent/plugins/zalo/accounts",
};

/** The URL to open for a route: itself, or the sample of its dynamic segments. */
export function concreteRoute(route: string): string {
  if (!isDynamicRoute(route)) return route;
  const sample = SAMPLE_PARAMS[route];
  if (sample === undefined) throw new Error(`no sample ids for ${route}: add it to SAMPLE_PARAMS`);
  return sample;
}

/** `YYYY-MM` of the clinic's month `n` months ago (Vietnam time), for the finance screens of a closed or paid month. */
function monthsAgo(n: number): string {
  const now = new Date(Date.now() + 7 * 3_600_000);
  const index = now.getUTCFullYear() * 12 + now.getUTCMonth() - n;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
}

/** Screens that are a state of one route, not a route of their own (a tab kept in `?tab=`): the visual harness opens them too. */
export const EXTRA_VISUAL_ROUTES: readonly string[] = [
  ...["consult", "plan", "session", "photos"].map(
    (tab) => `/patients/00000000-0000-4000-8002-000000000001?tab=${tab}`,
  ),
  // The cashier: the order dialog of a patient (WF3), the review of a draft (WF5) and of an approved order (WF6),
  // the print page of a draft (blocked, WF19) and one sheet of an approved order.
  "/cashier?patient=00000000-0000-4000-8002-000000000001",
  "/orders/00000000-0000-4000-8041-000000000002",
  "/orders/00000000-0000-4000-8041-000000000001/print",
  "/orders/00000000-0000-4000-8041-000000000002/print?sheet=CONSULTATION",
  // Finance (U6): the entry form open (WG3), a closed month (WG13) and a paid one (WG14), the personal view of the
  // owner (WG6); the other tabs are routes of their own. A doctor's views (WG6, WG7) need `VISUAL_ROLE=doctor`.
  "/finance/entries?form=open",
  `/finance/entries?month=${monthsAgo(2)}`,
  `/finance/entries?month=${monthsAgo(3)}`,
  "/finance?scope=own",
];
