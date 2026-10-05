// Mechanical first pass of the zalo-agent `web/` port (package E).
//
// Usage (from pema-agent/frontend):
//   node scripts/port-web-file.mjs pages/kb-poll-guard.ts pages/kb-poll-guard.test.ts
//   node scripts/port-web-file.mjs --dir shared
//
// It reads `web/src/<path>` from the read-only reference clone, looks the target up in
// docs/PORT-MAP.md (rows owned by package E) and writes it with: the `// ported from:` header,
// `"use client"` for .tsx, the Zalo blue scale renamed to the Pema `brand-*` scale, and relative
// imports rewritten to `@/...` aliases using the same map. Everything it cannot decide (API types,
// react-router, Vite globals, assets) is printed as a TODO list: finish those by hand. Never
// overwrites an existing file unless --force is given.
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join, posix, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, "..");
const PORT_MAP = resolve(FRONTEND, "../docs/PORT-MAP.md");
const REF_WEB = process.env.ZALO_AGENT_REF_WEB ?? "E:/Desktop/zalo-agent-ref/web";

const args = process.argv.slice(2);
const force = args.includes("--force");
const all = args.includes("--all");
const dirIdx = args.indexOf("--dir");
let requested = args.filter((a, i) => !a.startsWith("--") && !(dirIdx >= 0 && i === dirIdx + 1));
if (dirIdx >= 0) {
  const dir = args[dirIdx + 1];
  requested = readdirSync(join(REF_WEB, "src", dir)).map((f) => `${dir}/${f}`);
}

/**
 * Route pages: PORT-MAP lists one page.tsx for several originals, but the app keeps one route per page of
 * the original dashboard (see README "Layout"), so the pages are placed here instead.
 */
const ROUTE_PAGES = {
  "pages/overview-page": "src/app/(admin)/admin/overview/page.tsx",
  "pages/sessions-page": "src/app/(admin)/admin/threads/page.tsx",
  "pages/contacts-page": "src/app/(admin)/admin/contacts/page.tsx",
  "pages/friends-page": "src/app/(admin)/admin/friends/page.tsx",
  "pages/schedule-page": "src/app/(admin)/admin/schedules/page.tsx",
  "pages/memory-page": "src/app/(admin)/admin/memory/page.tsx",
  "pages/knowledge-page": "src/app/(admin)/admin/kb/page.tsx",
  "pages/accounts-page": "src/app/(admin)/admin/accounts/page.tsx",
  "pages/agents-page": "src/app/(admin)/admin/agents/page.tsx",
  "pages/agent-create-page": "src/app/(admin)/admin/agents/new/page.tsx",
  "pages/agent-detail-page": "src/app/(admin)/admin/agents/[id]/page.tsx",
  "pages/tools-page": "src/app/(admin)/admin/tools/page.tsx",
  "pages/mcp-page": "src/app/(admin)/admin/mcp/page.tsx",
  "pages/trace-page": "src/app/(admin)/admin/traces/page.tsx",
  "pages/tuning-page": "src/app/(admin)/admin/tuning/page.tsx",
  "pages/logs-page": "src/app/(admin)/admin/logs/page.tsx",
};

/** web/src-relative path without extension -> target file (relative to frontend/) */
const targets = new Map();
for (const line of readFileSync(PORT_MAP, "utf8").split(/\r?\n/)) {
  const m = line.match(/^\| `web\/src\/([^`]+)` \| \d+ \| `([^`]+)` \| E \|/);
  if (!m) continue;
  if (!/^frontend\/src\/\S+\.(ts|tsx)$/.test(m[2])) continue;
  targets.set(m[1].replace(/\.(ts|tsx)$/, ""), m[2].replace(/^frontend\//, ""));
}

for (const [key, target] of Object.entries(ROUTE_PAGES)) targets.set(key, target);

function aliasFor(target) {
  const noExt = target.replace(/^src\//, "").replace(/\.(ts|tsx)$/, "");
  return `@/${noExt}`;
}

const todo = [];

function transform(rel, source, ownTarget) {
  const note = (msg) => todo.push(`${rel}: ${msg}`);
  let out = source;

  out = out
    .replace(/zalo-950/g, "brand-50")
    .replace(/zalo-(50|100|200|400|500|600|700)/g, "brand-$1");

  out = out.replace(/from "(\.{1,2}\/[^"]+)"/g, (whole, spec) => {
    const abs = posix.normalize(posix.join(posix.dirname(`src/${rel}`), spec));
    const key = abs.replace(/^src\//, "").replace(/\.(ts|tsx|js)$/, "");
    if (key === "dashboard-api-client") {
      note("imports dashboard-api-client: rewrite against the typed OpenAPI client");
      return `from "@/lib/api/UNPORTED"`;
    }
    const t = targets.get(key);
    if (!t) {
      note(`import ${spec} has no PORT-MAP target`);
      return whole;
    }
    if (/\/page\.tsx$/.test(t)) {
      note(`import ${spec} points at a route page`);
      return whole;
    }
    return `from "${aliasFor(t)}"`;
  });

  if (/react-router/.test(out)) note("uses react-router: switch to next/navigation and next/link");
  if (/import\.meta|__APP_VERSION__/.test(out)) note("uses a Vite global");
  if (/["'`]\/(zalo|dashboard-background|favicon|apple)/.test(out))
    note("references a Zalo public asset");
  if (/node:test/.test(out)) {
    out = out.replace(/from "node:test"/g, 'from "vitest"');
    note("test uses node:test: check mock/timers helpers against vitest");
  }
  if (/\bany\b/.test(out)) note("contains `any` (lint)");

  const isTsx = ownTarget.endsWith(".tsx");
  const header = `// ported from: web/src/${rel}\n${isTsx ? '"use client";\n' : ""}\n`;
  return header + out;
}

if (all) {
  requested = [...targets.keys()]
    .flatMap((key) => [`${key}.ts`, `${key}.tsx`])
    .filter((file) => existsSync(join(REF_WEB, "src", file)));
}

for (const rel of requested) {
  const key = rel.replace(/\.(ts|tsx)$/, "");
  const target = targets.get(key);
  if (!target) {
    todo.push(`${rel}: no file target in PORT-MAP (route page, config or not a package E row)`);
    continue;
  }
  const dest = join(FRONTEND, target);
  if (existsSync(dest) && !force) {
    todo.push(`${rel}: ${target} exists, skipped`);
    continue;
  }
  const source = readFileSync(join(REF_WEB, "src", rel), "utf8");
  mkdirSync(dirname(dest), { recursive: true });
  writeFileSync(dest, transform(rel, source, target));
  process.stdout.write(`ported ${rel} -> ${target}\n`);
}

if (todo.length)
  process.stdout.write(`\nTODO by hand:\n${todo.map((t) => `  - ${t}`).join("\n")}\n`);
