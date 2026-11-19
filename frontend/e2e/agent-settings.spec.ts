// Cài đặt: the limits are edited from the page. A value out of its bounds never leaves the page; a value saved
// reaches the agent (read back through its API) and survives a reload; "Về mặc định" gives it back to the profile.
import { expect, test } from "playwright/test";

import { openAgent, signIn } from "./session";

const FIELD = "#setting-max_steps";
const LABEL = "Số bước tối đa mỗi lượt";

test("the four groups of limits are on the page, each with its range", async ({ page }) => {
  await signIn(page);
  await openAgent(page, "settings", "Cài đặt");

  for (const group of [
    "Ca chủ động",
    "Ngân sách token",
    "Giới hạn mỗi lượt trả lời",
    "Nén hội thoại dài",
  ]) {
    await expect(page.getByText(group, { exact: true }).first()).toBeVisible();
  }
  await expect(page.getByText(/^1 - 50\. Mỗi bước là một lần model nghĩ/)).toBeVisible();
});

test("a value out of its bounds is refused on the page and nothing can be saved", async ({
  page,
}) => {
  await signIn(page);
  await openAgent(page, "settings", "Cài đặt");

  await page.locator("#setting-max_turn_s").fill("5");

  await expect(page.locator("main").getByRole("alert")).toBeVisible();
  await expect(page.getByRole("button", { name: "Lưu thay đổi" })).toBeDisabled();
});

test("a limit saved from the page reaches the agent, survives a reload and goes back to the profile", async ({
  page,
}) => {
  await signIn(page);
  await openAgent(page, "settings", "Cài đặt");
  const reset = page.getByRole("button", { name: `Về mặc định: ${LABEL}` });
  test.skip(
    await reset.isVisible(),
    "max_steps is already set by hand on this stack: not touching it",
  );
  const original = await page.locator(FIELD).inputValue();
  const next = String(Number(original) === 11 ? 12 : 11);

  try {
    await page.locator(FIELD).fill(next);
    await page.getByRole("button", { name: "Lưu thay đổi" }).click();
    await expect(page.getByText("Đã lưu - áp dụng từ lượt trả lời tiếp theo.")).toBeVisible();

    const shown = await page.request.get("/agent/v1/admin/settings");
    expect((await shown.json()).max_steps).toBe(Number(next));
    await page.reload();
    await expect(page.locator(FIELD)).toHaveValue(next);
  } finally {
    await page.goto("/admin/agent/settings");
    const back = page.getByRole("button", { name: `Về mặc định: ${LABEL}` });
    if (await back.isVisible()) await back.click();
  }

  await expect(page.locator(FIELD)).toHaveValue(original);
  const after = await page.request.get("/agent/v1/admin/settings");
  expect((await after.json()).max_steps).toBe(Number(original));
});
