// `tsx scripts/presence-check.ts`: two browser contexts (two staff members) open the SAME conversation of the mock
// backend and the script checks what each one sees: "đang xem" in the list and the thread, then "đang trả lời"
// plus the warning when the first one starts typing, and that the box is still usable (a warning, never a lock).
// Needs the mock backend and the app running (`pnpm dev:mock`, or `pnpm mock` + `pnpm start`).
//
//   SHOTS_BASE_URL=http://localhost:3000 [PRESENCE_DIR=shots/presence] tsx scripts/presence-check.ts
import { mkdirSync } from "node:fs";

import { chromium, type Browser, type Page } from "playwright";

const BASE = process.env.SHOTS_BASE_URL ?? "http://localhost:3000";
const OUT = process.env.PRESENCE_DIR ?? "shots/presence";
const CONVERSATION = "00000000-0000-4000-8007-000000000001";
const WAIT_MS = 15_000;

async function signIn(browser: Browser, email: string, name: string) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(`${name} pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(`${name} console: ${m.text()}`);
  });
  await page.goto(`${BASE}/login`);
  await page.fill("#email", email);
  await page.fill("#password", "demo1234");
  await Promise.all([
    page.waitForURL((url) => !url.pathname.startsWith("/login")),
    page.click("button[type=submit]"),
  ]);
  await page.goto(`${BASE}/inbox?c=${CONVERSATION}`, { waitUntil: "load" });
  return { context, page, errors };
}

async function waitForText(page: Page, text: string): Promise<void> {
  await page.getByText(text).first().waitFor({ timeout: WAIT_MS });
}

async function main(): Promise<void> {
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const mai = await signIn(browser, "cs@pema.test", "Mai Anh");
  const ha = await signIn(browser, "owner@pema.test", "Hà");

  // Both open the conversation: each sees the other as viewing.
  await waitForText(mai.page, "Hà đang xem");
  await waitForText(ha.page, "Anh đang xem");
  await ha.page.screenshot({ path: `${OUT}/viewing-ha.png` });

  // Mai starts typing: Hà sees "đang trả lời" and the warning, and can still type.
  await mai.page.getByLabel("Nội dung trả lời").fill("Dạ em chào chị ạ");
  await waitForText(ha.page, "Anh đang trả lời");
  await waitForText(ha.page, "Bạn vẫn nhắn được");
  const locked = await ha.page.getByLabel("Nội dung trả lời").isDisabled();
  await ha.page.screenshot({ path: `${OUT}/replying-ha.png` });
  await mai.page.screenshot({ path: `${OUT}/replying-mai.png` });

  await browser.close();
  const problems = [...mai.errors, ...ha.errors];
  if (locked) problems.push("the reply box is disabled while a colleague is replying");
  process.stdout.write(
    problems.length === 0
      ? "presence visible in both contexts, no errors\n"
      : `${problems.join("\n")}\n`,
  );
  process.exitCode = problems.length === 0 ? 0 : 1;
}

await main();
