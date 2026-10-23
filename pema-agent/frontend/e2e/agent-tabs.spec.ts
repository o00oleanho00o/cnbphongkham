// Điều khiển agent: every tab opens from the tab bar, shows its heading and throws nothing; the agent's admin
// routes refuse a caller who is not signed in.
import { expect, test } from "playwright/test";

import { signIn, watch } from "./session";

const TABS = ["Tổng quan", "Phiên chat", "Trace", "Ca", "Model", "Cài đặt", "Công cụ", "Plugins"];

test("every tab of the agent opens and throws nothing", async ({ page }) => {
  const seen = watch(page);
  await signIn(page);
  await page.goto("/admin/agent/overview");
  const bar = page.getByRole("navigation", { name: "Trang quản trị agent" });

  for (const tab of TABS) {
    await bar.getByRole("link", { name: tab, exact: true }).click();
    await expect(page.locator("main h1").first()).toHaveText(tab);
  }

  expect(seen.problems).toEqual([]);
});

test("the agent's admin routes refuse a caller who is not signed in", async ({ request }) => {
  for (const path of [
    "/agent/v1/admin/settings",
    "/agent/v1/admin/cases",
    "/agent/v1/admin/model",
  ]) {
    const answer = await request.get(path);
    expect([401, 403], `${path} answered ${answer.status()}`).toContain(answer.status());
  }
});
