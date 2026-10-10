// @vitest-environment jsdom
// Phiên chat của agent: the list with its search and channel filter, a chat opened with its messages, deleting it
// after a confirmation, and `?session=` opening one straight away.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { register, forget } from "@/lib/agent/sdk";

import { SessionsPage } from "./sessions-page";

const nav = vi.hoisted(() => ({ search: "" }));

vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(nav.search) }));

const row = (id: string, user: string, channel: string, count: number, compacted = false) => ({
  session_id: id,
  channel,
  user_id: user,
  message_count: count,
  created_at: "2026-10-10T08:00:00+00:00",
  updated_at: "2026-10-10T09:30:00+00:00",
  compacted,
});

const ZALO = "clinic:zalo-a:u-1:0";
const HTTP = "clinic:http:u-2:0";

const DETAIL = {
  ...row(ZALO, "u-1", "zalo-a", 2),
  summary: null,
  messages: [
    { role: "user", text: "Cho mình hỏi giá laser", tools: [], at: "2026-10-10T08:00:00+00:00" },
    {
      role: "assistant",
      text: "Dạ bên em có gói từ 1,5 triệu",
      tools: ["kb_search"],
      at: "2026-10-10T08:01:00+00:00",
    },
  ],
};

type Call = { method: string; url: string };

/** A fake agent over the browser's fetch (an outside system); every call is written down. */
function fakeAgent(): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    calls.push({ method, url });
    let body: unknown = {};
    if (url.startsWith("/agent/v1/admin/sessions?") || url === "/agent/v1/admin/sessions") {
      body = {
        items: [row(ZALO, "u-1", "zalo-a", 2), row(HTTP, "u-2", "http", 5, true)],
        has_more: false,
      };
    } else if (url === `/agent/v1/admin/sessions/${encodeURIComponent(ZALO)}`) {
      body = method === "DELETE" ? { deleted: ZALO } : DETAIL;
    } else if (url === "/agent/v1/admin/channels") {
      body = { channels: [{ name: "zalo-a" }, { name: "http" }] };
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
  forget("zalo");
});

describe("the sessions page", () => {
  it("lists_the_chats_with_their_channel_and_message_count", async () => {
    fakeAgent();
    render(<SessionsPage />);

    expect(await screen.findByText("u-1")).toBeTruthy();
    expect(screen.getByText("u-2")).toBeTruthy();
    expect(screen.getByText("(đã rút gọn)")).toBeTruthy();
    expect(screen.getByText(ZALO)).toBeTruthy();
  });

  it("asks_the_agent_for_what_is_typed_and_the_chosen_channel", async () => {
    const calls = fakeAgent();
    render(<SessionsPage />);
    await screen.findByText("u-1");

    fireEvent.change(screen.getByPlaceholderText(/Tìm theo người/), { target: { value: "u-2" } });
    fireEvent.change(await screen.findByRole("combobox", { name: "Lọc theo kênh" }), {
      target: { value: "http" },
    });

    await waitFor(() =>
      expect(calls.map((c) => c.url)).toContain("/agent/v1/admin/sessions?channel=http&q=u-2"),
    );
  });

  it("opens_a_chat_with_its_messages_and_the_tools_it_used", async () => {
    fakeAgent();
    render(<SessionsPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Xem phiên của u-1" }));

    expect(await screen.findByText("Cho mình hỏi giá laser")).toBeTruthy();
    expect(screen.getByText("Dạ bên em có gói từ 1,5 triệu")).toBeTruthy();
    expect(screen.getByText("kb_search")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Xem trace của phiên" }).getAttribute("href")).toBe(
      `/admin/agent/traces?session=${encodeURIComponent(ZALO)}`,
    );
  });

  it("opens_the_chat_named_in_the_address", async () => {
    fakeAgent();
    nav.search = `session=${encodeURIComponent(ZALO)}`;
    render(<SessionsPage />);

    expect(await screen.findByText("Cho mình hỏi giá laser")).toBeTruthy();
  });

  it("deletes_a_chat_only_after_the_confirmation", async () => {
    const calls = fakeAgent();
    render(<SessionsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Xem phiên của u-1" }));
    fireEvent.click(await screen.findByRole("button", { name: "Xóa phiên" }));

    const question = await screen.findByText("Xóa phiên chat này?");
    const dialog = question.closest<HTMLElement>('[role="dialog"]');
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    fireEvent.click(within(dialog as HTMLElement).getByRole("button", { name: "Xóa phiên" }));

    await waitFor(() =>
      expect(calls).toContainEqual({
        method: "DELETE",
        url: `/agent/v1/admin/sessions/${encodeURIComponent(ZALO)}`,
      }),
    );
  });

  it("names_the_people_a_plugin_knows_with_one_call_per_channel_and_keeps_the_id_for_the_rest", async () => {
    fakeAgent();
    const asked: { channel: string; ids: readonly string[] }[] = [];
    register("zalo", {
      personNames: (channel, ids) => {
        asked.push({ channel, ids });
        const known: Record<string, string> = channel === "zalo-a" ? { "u-1": "Nguyễn Mai" } : {};
        return Promise.resolve(known);
      },
    });
    render(<SessionsPage />);

    expect(await screen.findByText("Nguyễn Mai")).toBeTruthy();
    expect(screen.getByText("u-2")).toBeTruthy();
    expect(asked).toEqual([
      { channel: "zalo-a", ids: ["u-1"] },
      { channel: "http", ids: ["u-2"] },
    ]);
  });

  it("starts_from_the_search_in_the_address", async () => {
    const calls = fakeAgent();
    nav.search = "q=u-1";
    render(<SessionsPage />);

    await screen.findByText("u-1");
    expect(calls.map((c) => c.url)).toContain("/agent/v1/admin/sessions?q=u-1");
  });
});
