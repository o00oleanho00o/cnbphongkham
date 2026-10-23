// Shared by the specs: sign in as the owner of the stack under test, and watch a page for errors the user would
// never see on screen (a script that threw, a console error).
import { expect, type Page } from "playwright/test";

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Set ${name} to the owner account of the stack under test.`);
  return value;
}

export async function signIn(page: Page): Promise<void> {
  await page.goto("/login");
  await page.fill("#email", required("E2E_EMAIL"));
  await page.fill("#password", required("E2E_PASSWORD"));
  await Promise.all([
    page.waitForURL((url) => !url.pathname.startsWith("/login")),
    page.click("button[type=submit]"),
  ]);
}

/** Collects what the page threw or logged as an error; read `problems` at the end of the test. */
export function watch(page: Page): { problems: string[] } {
  const problems: string[] = [];
  page.on("pageerror", (err) => problems.push(`pageerror: ${err.message}`));
  page.on("console", (msg) => {
    if (msg.type() === "error") problems.push(`console: ${msg.text()}`);
  });
  return { problems };
}

export async function openAgent(page: Page, tab: string, heading: string): Promise<void> {
  await page.goto(`/admin/agent/${tab}`);
  await expect(page.locator("main h1").first()).toHaveText(heading);
}
