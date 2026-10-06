#!/usr/bin/env node
// Screenshot one screen of crm-lab (or of the old prototype, for a "before" shot) at one or more viewports.
//
//   node crm-lab/tools/shot.cjs --url "http://127.0.0.1:4177/clinic-web/?staff=owner-tam" \
//        --click ".sidebar [data-nav=\"crm\"]" --wait ".page-title" \
//        --out crm-ideas/<slug>/shots/after-crm [--viewports 1440x900,390x844]
//
// --click may be repeated (clicks run in order). Files: <out>-<width>x<height>.png.
// Playwright: set PLAYWRIGHT_MODULE to a playwright folder, or run `pnpm install` in pema-agent/frontend
// (the script then finds pema-agent/frontend/node_modules/playwright) and `npx playwright install chromium` once.
"use strict";

const path = require("node:path");
const fs = require("node:fs");

function parseArgs(argv) {
  const out = { clicks: [], viewports: "1440x900,390x844" };
  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i];
    const value = argv[i + 1];
    if (key === "--url") out.url = value;
    else if (key === "--out") out.out = value;
    else if (key === "--wait") out.wait = value;
    else if (key === "--viewports") out.viewports = value;
    else if (key === "--click") out.clicks.push(value);
    else continue;
    i += 1;
  }
  return out;
}

function loadPlaywright() {
  const repoRoot = path.resolve(__dirname, "..", "..");
  const candidates = [
    process.env.PLAYWRIGHT_MODULE,
    path.join(repoRoot, "pema-agent", "frontend", "node_modules", "playwright"),
    "playwright",
  ].filter(Boolean);
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch {
      // try the next one
    }
  }
  throw new Error(
    "Playwright not found. Run `pnpm install` in pema-agent/frontend and `npx playwright install chromium`, " +
      "or set PLAYWRIGHT_MODULE to a playwright folder.",
  );
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.url || !args.out) {
    process.stderr.write("Usage: node crm-lab/tools/shot.cjs --url <url> --out <path-prefix> [--click <sel>]... [--wait <sel>] [--viewports 1440x900,390x844]\n");
    process.exit(2);
  }
  const { chromium } = loadPlaywright();
  fs.mkdirSync(path.dirname(path.resolve(args.out)), { recursive: true });
  const browser = await chromium.launch();
  const errors = [];
  try {
    for (const spec of args.viewports.split(",")) {
      const [width, height] = spec.split("x").map(Number);
      const page = await browser.newPage({ viewport: { width, height } });
      page.on("pageerror", (error) => errors.push(`${spec}: ${error.message}`));
      await page.goto(args.url, { waitUntil: "networkidle" });
      for (const selector of args.clicks) {
        await page.click(selector);
        await page.waitForLoadState("networkidle");
      }
      if (args.wait) await page.waitForSelector(args.wait, { timeout: 10000 });
      const file = `${args.out}-${width}x${height}.png`;
      await page.screenshot({ path: file, fullPage: true });
      process.stdout.write(`${file}\n`);
      await page.close();
    }
  } finally {
    await browser.close();
  }
  if (errors.length > 0) {
    process.stderr.write(`Page errors:\n${errors.join("\n")}\n`);
    process.exit(1);
  }
}

main().catch((error) => {
  process.stderr.write(`${error.message}\n`);
  process.exit(1);
});
