// Zalo is a connector, not an agent plugin: its pages are served by the connector service through the clinic web's
// `/connectors/zalo/...` proxy and hosted in "Điều khiển agent" (Plugins > Connector > zalo > Tài khoản Zalo).
import { expect, test } from "playwright/test";

import { signIn, watch } from "./session";

test("the Zalo accounts page opens from the agent menu through the connector proxy", async ({
  page,
}) => {
  const seen = watch(page);
  await signIn(page);
  await page.goto("/admin/agent/overview");
  const bar = page.getByRole("navigation", { name: "Trang quản trị agent" });

  await bar.getByRole("link", { name: "Plugins", exact: true }).click();
  await page.getByRole("list", { name: "Danh sách connector" }).getByRole("link", { name: /zalo/ }).click();
  await expect(page.locator("main h1").first()).toHaveText("zalo");

  const tabs = page.getByRole("navigation", { name: "Trang của connector zalo" });
  await tabs.getByRole("link", { name: "Tài khoản Zalo" }).click();
  await expect(page).toHaveURL(/\/admin\/agent\/plugins\/zalo\/accounts$/);
  await expect(page.getByRole("button", { name: "Thêm tài khoản" })).toBeVisible();

  expect(seen.problems).toEqual([]);
});

test("the connector proxy refuses a caller who is not signed in", async ({ request }) => {
  for (const path of ["/connectors", "/connectors/zalo/v1/admin/ui"]) {
    const answer = await request.get(path);
    expect([401, 403], `${path} answered ${answer.status()}`).toContain(answer.status());
  }
});
