// Model: each model of the list carries its context window; one out of range is refused on the form.
import { expect, test } from "playwright/test";

import { openAgent, signIn } from "./session";

test("the list shows each model's window and the form refuses one out of range", async ({
  page,
}) => {
  await signIn(page);
  await openAgent(page, "model", "Model");
  await expect(page.getByText(/cửa sổ (\d|theo profile)/).first()).toBeVisible();

  await page.getByRole("button", { name: /^Sửa / }).first().click();
  const window = page.getByLabel(/^Cửa sổ ngữ cảnh/);
  await expect(window).toBeVisible();
  await window.fill("3000");

  await expect(page.locator("main").getByRole("alert")).toBeVisible();
  await expect(page.getByRole("button", { name: "Lưu thay đổi" })).toBeDisabled();
});
