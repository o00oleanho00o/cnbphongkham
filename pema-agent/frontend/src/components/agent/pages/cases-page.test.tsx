// @vitest-environment jsdom
// Ca của agent: the cases newest first with their state, "Chạy ngay" only on a live one (it posts the wake and says
// the checks still run), a closed case refused in words, and each case's log on demand.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CasesPage } from "./cases-page";

const item = (id: number, fields: Record<string, unknown> = {}) => ({
  id,
  kind: "follow_up",
  key: `zalo-botthang:c${id}`,
  channel: "zalo-botthang",
  conversation_id: `c${id}`,
  goal: "Khách quay lại hoặc nói không",
  status: "waiting",
  node: "quiet",
  state: {},
  wait_for: "clock",
  wake_at: "2026-10-23T05:00:00+00:00",
  deadline: null,
  turns: 0,
  proactive_sent: 0,
  end_reason: null,
  created_at: "2026-10-23T03:00:00+00:00",
  updated_at: "2026-10-23T03:00:00+00:00",
  closed_at: null,
  ...fields,
});

const LIST = {
  cases: [
    item(2),
    item(1, {
      kind: "reminder",
      status: "done",
      wait_for: null,
      wake_at: null,
      end_reason: "đã đến khám",
    }),
  ],
};

const EVENTS = [
  { seq: 1, at: "2026-10-23T03:00:00+00:00", kind: "opened", node: "quiet", detail: {} },
  {
    seq: 2,
    at: "2026-10-23T03:05:00+00:00",
    kind: "woken",
    node: "quiet",
    detail: { by: "admin" },
  },
];

type Reply = { status?: number; body: unknown };
type Call = { method: string; url: string };

/** A fake agent over the browser's fetch (an outside system); every call is written down. */
function fakeAgent(answers: Record<string, Reply> = {}): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    calls.push({ method, url });
    const reply = answers[`${method} ${url}`] ?? { body: LIST };
    return Promise.resolve(
      new Response(JSON.stringify(reply.body), { status: reply.status ?? 200 }),
    );
  });
  return calls;
}

const posts = (calls: Call[]) => calls.filter((c) => c.method === "POST");

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the cases of the agent", () => {
  it("lists_the_cases_with_their_kind_and_state_and_run_now_only_on_a_live_one", async () => {
    fakeAgent();
    render(<CasesPage />);

    const list = await screen.findByRole("list", { name: "Danh sách ca" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText(/#2 · Chăm sóc lại/)).toBeTruthy();
    expect(screen.getByText(/#1 · Nhắc lịch/)).toBeTruthy();
    expect(screen.getByText("Đang chờ")).toBeTruthy();
    expect(screen.getByText("Xong")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Chạy ngay ca #2" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Chạy ngay ca #1" })).toBeNull();
  });

  it("posts_the_wake_of_the_case_and_says_its_checks_still_run", async () => {
    const calls = fakeAgent({ "POST /agent/v1/admin/cases/2/wake": { body: item(2) } });
    render(<CasesPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Chạy ngay ca #2" }));

    await screen.findByText(/Các bước kiểm vẫn chạy/);
    expect(posts(calls).map((c) => c.url)).toEqual(["/agent/v1/admin/cases/2/wake"]);
  });

  it("says_in_words_when_the_case_was_closed_meanwhile", async () => {
    fakeAgent({
      "POST /agent/v1/admin/cases/2/wake": {
        status: 409,
        body: { error: { kind: "not_live", message: "the case is closed, or its plugin is off" } },
      },
    });
    render(<CasesPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Chạy ngay ca #2" }));

    await screen.findByText("Ca #2 đã đóng hoặc plugin của nó đang tắt.");
  });

  it("shows_the_log_of_a_case_on_demand_and_hides_it_again", async () => {
    fakeAgent({ "GET /agent/v1/admin/cases/2": { body: { ...item(2), events: EVENTS } } });
    render(<CasesPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Xem nhật ký ca #2" }));

    const log = await screen.findByRole("list", { name: "Nhật ký ca #2" });
    expect(within(log).getAllByRole("listitem")).toHaveLength(2);
    expect(within(log).getByText(/Đánh thức/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Ẩn nhật ký ca #2" }));
    await waitFor(() => expect(screen.queryByRole("list", { name: "Nhật ký ca #2" })).toBeNull());
  });
});
