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
