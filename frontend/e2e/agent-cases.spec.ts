// Ca: the cases of the agent and their log. "Gửi thử ngay" writes to a REAL customer chat, so it runs only when
// E2E_ALLOW_SEND=1 and the stack has a live case; the case must be left exactly as it was.
import { expect, test } from "playwright/test";

import { openAgent, signIn } from "./session";

test("the cases are listed and the log of one opens", async ({ page }) => {
  await signIn(page);
  await openAgent(page, "cases", "Ca");

  const list = page.getByRole("list", { name: "Danh sách ca" });
  test.skip(!(await list.isVisible()), "this stack has no case yet");
  const first = list.getByRole("listitem").first();
  await first.getByRole("button", { name: /^Xem nhật ký ca #/ }).click();

  await expect(page.getByRole("list", { name: /^Nhật ký ca #/ })).toBeVisible();
  await expect(page.getByText("Mở ca").first()).toBeVisible();
});

test("a test send is confirmed first, says what happened and leaves the case as it was", async ({
  page,
}) => {
  test.skip(process.env.E2E_ALLOW_SEND !== "1", "writes to a real chat: set E2E_ALLOW_SEND=1");
  await signIn(page);
  await openAgent(page, "cases", "Ca");
  const live = page.getByRole("button", { name: /^Gửi thử ngay ca #/ }).first();
  test.skip(!(await live.isVisible()), "no live case on this stack");
  const row = page.getByRole("listitem").filter({ has: live });
  const before = await row.innerText();

  await live.click();
  await expect(page.getByRole("dialog")).toContainText("nhắn thật cho khách");
  await page.getByRole("dialog").getByRole("button", { name: "Gửi thử" }).click();

  await expect(page.getByText(/Đã gửi thử cho ca #|không gửi:/)).toBeVisible();
  expect(await row.innerText()).toBe(before);
});
