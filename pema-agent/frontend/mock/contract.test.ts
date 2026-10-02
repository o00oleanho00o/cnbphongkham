// The mock backend must serve every path of the OpenAPI contract the frontend is typed against, and
// nothing outside it (a mock-only route would hide a missing BE feature). Webhooks are called by Zalo,
// not by the browser, so they are exempt.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { buildRouter } from "./server";

type Spec = { paths: Record<string, Record<string, unknown>> };

const spec = JSON.parse(
  readFileSync(
    fileURLToPath(new URL("../../backend/apps/api/openapi.json", import.meta.url)),
    "utf8",
  ),
) as Spec;

const METHODS = new Set(["get", "post", "put", "patch", "delete"]);
const EXEMPT = /\/webhooks\//;

// Routes of the "several people at once" package that the backend has not put into openapi.json yet, so the
// mock serves them as PENDING. Live events, presence and `GET /api/v1/staff/assignable` are in the contract
// now. When the mock serves a route the regenerated openapi.json lacks, add it here: the last test fails on
// a stale entry.
const PENDING_CONTRACT: string[] = [];

function specOperations(): string[] {
  const ops: string[] = [];
  for (const [path, item] of Object.entries(spec.paths)) {
    if (EXEMPT.test(path)) continue;
    for (const method of Object.keys(item)) {
      if (METHODS.has(method)) ops.push(`${method.toUpperCase()} ${path}`);
    }
  }
  return ops.sort();
}

describe("mock backend vs openapi.json", () => {
  it("serves every operation of the contract", async () => {
    const router = await buildRouter();
    const served = new Set(router.routes.map((r) => `${r.method} ${r.template}`));
    const missing = specOperations().filter((op) => !served.has(op));
    expect(missing).toEqual([]);
  });

  it("serves nothing outside the contract", async () => {
    const router = await buildRouter();
    const known = new Set(specOperations());
    const extra = router.routes
      .map((r) => `${r.method} ${r.template}`)
      .filter((op) => !known.has(op) && !op.endsWith("/healthz") && !PENDING_CONTRACT.includes(op));
    expect(extra).toEqual([]);
  });

  it("serves every pending route, and none of them is in the contract yet", async () => {
    const router = await buildRouter();
    const served = new Set(router.routes.map((r) => `${r.method} ${r.template}`));
    const known = new Set(specOperations());
    expect(PENDING_CONTRACT.filter((op) => !served.has(op))).toEqual([]);
    expect(PENDING_CONTRACT.filter((op) => known.has(op))).toEqual([]);
  });
});
