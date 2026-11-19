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

test("a connector is switched off and on and removed from the Connectors page", async ({ page }) => {
  const name = `e2e-${Date.now().toString(36)}`;
  await signIn(page);
  await page.goto("/admin/agent/overview");
  await page.getByRole("navigation", { name: "Trang quản trị agent" }).getByRole("link", { name: "Connectors", exact: true }).click();

  await page.locator("main").getByRole("textbox").first().fill(name);
  await page.getByRole("button", { name: "Thêm và cấp khóa" }).click();
  const card = page.locator("section, div").filter({ hasText: `Cấp lúc` }).filter({ has: page.getByText(name, { exact: true }) }).last();
  await expect(card.getByText("Đang dùng", { exact: true })).toBeVisible();

  await card.getByRole("button", { name: "Tắt", exact: true }).click();
  await expect(card.getByText("Đã tắt", { exact: true })).toBeVisible();
  await card.getByRole("button", { name: "Bật", exact: true }).click();
  await expect(card.getByText("Đang dùng", { exact: true })).toBeVisible();

  await card.getByRole("button", { name: "Tắt", exact: true }).click();
  await expect(card.getByText("Đã tắt", { exact: true })).toBeVisible();
  await card.getByRole("button", { name: "Xóa", exact: true }).click();
  await card.getByRole("button", { name: "Xóa", exact: true }).click();
  await expect(page.getByText(name, { exact: true })).toHaveCount(0);
});
