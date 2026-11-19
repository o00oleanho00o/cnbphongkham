// Trả lời có kiểm (docs/PLAN-rag-graph.md): switched on from the knowledge store's settings, a customer's turn walks
// the answer graph, and the Trace page shows its steps (search, answer, check). Needs a model key on the stack: the
// turn really runs. The switch is put back as it was.
import { expect, test, type Page } from "playwright/test";

import { signIn, watch } from "./session";

const SWITCH = "Trả lời có kiểm";

async function openSettings(page: Page): Promise<void> {
  await page.goto("/admin/agent/plugins/knowledge/store");
  await page.getByRole("tablist", { name: "Kho tri thức" }).getByRole("tab", { name: "Cài đặt" }).click();
  await expect(page.getByRole("switch", { name: SWITCH })).toBeVisible();
}

async function setSwitch(page: Page, on: boolean): Promise<void> {
  const toggle = page.getByRole("switch", { name: SWITCH });
  if ((await toggle.getAttribute("aria-checked")) === String(on)) return;
  await toggle.click();
  await page.getByRole("button", { name: `Lưu ${SWITCH.toLowerCase()}` }).click();
  await expect(page.getByText(on ? "Đã bật trả lời có kiểm." : "Đã tắt trả lời có kiểm.")).toBeVisible();
}

test("a turn with checked answers on shows its graph steps on the Trace page", async ({ page }) => {
  test.setTimeout(180_000);
  const seen = watch(page);
  await signIn(page);
  await openSettings(page);
  const before = (await page.getByRole("switch", { name: SWITCH }).getAttribute("aria-checked")) === "true";
  const user = `e2e-rag-${Date.now().toString(36)}`;

  try {
    await setSwitch(page, true);
    const shown = await page.request.get("/agent/v1/plugins/knowledge/settings");
    expect((await shown.json()).answer.graph).toBe("on");

    const answer = await page.request.post("/agent/v1/chat", {
      data: { message_id: `${user}-1`, user_id: user, text: "Giá dịch vụ trị nám là bao nhiêu một buổi?" },
      timeout: 150_000,
    });
    expect(answer.ok(), await answer.text()).toBe(true);
    const turn = (await answer.json()) as { session_id: string; text: string };
    expect(turn.text.trim().length).toBeGreaterThan(0);

    await page.goto(`/admin/agent/traces?session=${encodeURIComponent(turn.session_id)}`);
    await page.getByRole("button", { name: /^Xem các bước của lượt lúc/ }).first().click();
    const steps = page.locator("main");
    await expect(steps.getByText("Bước đồ thị").first()).toBeVisible();
    for (const node of ["search", "answer", "check"]) {
      await expect(steps.getByText(node, { exact: true }).first()).toBeVisible();
    }
  } finally {
    await openSettings(page);
    await setSwitch(page, before);
  }
  expect(seen.problems).toEqual([]);
});

test("a wrong value of the switch is refused by the agent", async ({ page }) => {
  await signIn(page);
  const refused = await page.request.patch("/agent/v1/plugins/knowledge/settings", {
    data: { answer: { graph: "maybe" } },
  });
  expect(refused.status()).toBe(422);
});
