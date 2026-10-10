// @vitest-environment jsdom
// Trace của agent: one row per turn with its outcome, the filters (channel, failed only, one chat), and the steps of a
// turn with their time and errors.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TracesPage } from "./traces-page";

const nav = vi.hoisted(() => ({ search: "" }));

vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(nav.search) }));

const TURN = "00000000-0000-4000-8a00-000000000001";
const FAILED = "00000000-0000-4000-8a00-000000000002";

const turn = (id: string, stop: string, errorKind: string | null) => ({
  turn_id: id,
  session_id: "clinic:zalo-a:u-1:0",
  channel: "zalo-a",
  user_id: "u-1",
  model: "deepseek-v4-pro",
  started_at: "2026-10-10T08:00:00+00:00",
  duration_ms: 4200,
  stop,
  steps: 2,
  error_kind: errorKind,
  input_tokens: 1000,
  output_tokens: 80,
});

const DETAIL = {
  ...turn(TURN, "completed", null),
  compactions: 0,
  cache_read_tokens: 640,
  cache_write_tokens: 0,
  reasoning_tokens: 0,
  events: [
    {
      kind: "tool_call",
      step: 1,
      name: "kb_search",
      duration_ms: 350,
      is_error: true,
      detail: { size: 12 },
    },
  ],
};

type Call = { method: string; url: string };

/** A fake agent over the browser's fetch (an outside system); every call is written down. */
function fakeAgent(): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    calls.push({ method: init?.method ?? "GET", url });
    let body: unknown = {};
    if (url.startsWith("/agent/v1/admin/traces?") || url === "/agent/v1/admin/traces") {
      body = {
        items: [turn(TURN, "completed", null), turn(FAILED, "error", "auth")],
        has_more: false,
      };
    } else if (url === `/agent/v1/admin/traces/${TURN}`) {
      body = DETAIL;
    } else if (url === "/agent/v1/admin/channels") {
      body = { channels: [{ name: "zalo-a" }] };
    }
    return Promise.resolve(new Response(JSON.stringify(body)));
  });
  return calls;
}

beforeEach(() => {
  nav.search = "";
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the trace page", () => {
  it("lists_each_turn_with_its_outcome_and_the_reason_it_failed", async () => {
    fakeAgent();
    render(<TracesPage />);

    expect(await screen.findByText("Xong")).toBeTruthy();
    expect(screen.getByText("Lỗi")).toBeTruthy();
    expect(screen.getByText("Khóa API sai hoặc hết hạn")).toBeTruthy();
    expect(screen.getAllByText("1.080")).toHaveLength(2);
  });

  it("asks_only_for_failed_turns_when_the_box_is_ticked", async () => {
    const calls = fakeAgent();
    render(<TracesPage />);
    await screen.findByText("Xong");

    fireEvent.click(screen.getByRole("checkbox", { name: "Chỉ lượt không thành công" }));

    await waitFor(() =>
      expect(calls.map((c) => c.url)).toContain("/agent/v1/admin/traces?errors_only=true"),
    );
  });

  it("limits_the_list_to_the_chat_named_in_the_address", async () => {
    const calls = fakeAgent();
    nav.search = `session=${encodeURIComponent("clinic:zalo-a:u-1:0")}`;
    render(<TracesPage />);

    expect(await screen.findByText(/Chỉ các lượt của phiên/)).toBeTruthy();
    expect(calls.map((c) => c.url)).toContain(
      `/agent/v1/admin/traces?session_id=${encodeURIComponent("clinic:zalo-a:u-1:0")}`,
    );
    expect(screen.getByRole("link", { name: "Bỏ lọc" }).getAttribute("href")).toBe(
      "/admin/agent/traces",
    );
  });

  it("opens_the_steps_of_a_turn_with_their_time_and_errors", async () => {
    fakeAgent();
    render(<TracesPage />);
    const buttons = await screen.findAllByRole("button", { name: /Xem các bước của lượt/ });

    fireEvent.click(buttons[0] as HTMLElement);

    expect(await screen.findByText("Gọi tool")).toBeTruthy();
    expect(screen.getByText("kb_search")).toBeTruthy();
    expect(screen.getByText("350 ms")).toBeTruthy();
    expect(screen.getByText("size: 12")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Xem phiên chat" }).getAttribute("href")).toBe(
      `/admin/agent/sessions?session=${encodeURIComponent("clinic:zalo-a:u-1:0")}`,
    );
  });
});
