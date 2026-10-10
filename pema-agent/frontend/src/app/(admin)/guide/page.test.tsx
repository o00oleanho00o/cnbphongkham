// @vitest-environment jsdom
// "Hướng dẫn" against a fake of the typed client: the index lists the articles, a topic chip and the search box
// narrow it, an article opens on `?a=<id>` and its Markdown is shown as text (an injected tag stays text).
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SessionProvider } from "@/lib/session/session-context";

import GuidePage from "./page";

const nav = vi.hoisted(() => ({ search: "", pushed: [] as string[] }));
const api = vi.hoisted(() => ({ get: vi.fn() }));

// Next's router is a framework boundary: the page only reads `?a=` and pushes a new url.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: (url: string) => nav.pushed.push(url) }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));
// The HTTP client is the unmanaged dependency: a hand-written fake of the two routes the page calls.
vi.mock("@/lib/api/client", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api/client")>();
  return { ...actual, http: { GET: (...args: unknown[]) => api.get(...args) } };
});

const summary = (id: string, title: string, topic: string, text: string) => ({
  id,
  title,
  topic,
  tags: ["guide", topic],
  summary: text,
  status: "san_sang",
  updated_at: "2026-09-20T09:00:00+07:00",
});

const LIST = [
  summary("a", "Bắt đầu theo vai trò", "Tất cả", "Biết nơi bắt đầu"),
  summary("b", "CSKH chủ động", "CSKH", "Đúng người, đúng việc"),
  summary("c", "Hồ sơ và Patient 360", "Bác sĩ", "Đọc bối cảnh"),
];

const BODY = "## Cách thực hiện\n\n1. Mở **Hôm nay**.\n\n<script>alert(1)</script>";

function reply(data: unknown) {
  return Promise.resolve({ data, response: new Response(null, { status: 200 }) });
}

function renderGuide(
  permissions: Parameters<typeof SessionProvider>[0]["permissions"] = ["kb.read"],
) {
  return render(
    <SessionProvider
      user={{
        id: "00000000-0000-4000-8000-000000000004",
        clinic_id: "clinic",
        clinic_name: "Phòng khám Pema (dữ liệu mẫu)",
        display_name: "Mai Anh",
        role: "cs_staff",
      }}
      permissions={permissions}
      onLoggedOut={() => undefined}
    >
      <GuidePage />
    </SessionProvider>,
  );
}

beforeEach(() => {
  nav.search = "";
  nav.pushed = [];
  api.get.mockReset().mockImplementation((path: string) => {
    if (path === "/api/v1/guide/articles") return reply(LIST);
    return reply({ ...LIST[1], body: BODY });
  });
});

afterEach(cleanup);

describe("guide page", () => {
  it("lists_every_article_with_its_topic", async () => {
    renderGuide();
    expect(await screen.findByText("Hồ sơ và Patient 360")).toBeTruthy();
    expect(screen.getByText("CSKH chủ động")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Bác sĩ/, pressed: false })).toBeTruthy();
  });

  it("a_search_without_diacritics_narrows_the_index", async () => {
    renderGuide();
    await screen.findByText("Hồ sơ và Patient 360");
    await userEvent.type(screen.getByLabelText("Tìm chủ đề hoặc vai trò"), "ho so");
    expect(screen.queryByText("CSKH chủ động")).toBeNull();
    expect(screen.getByText("Hồ sơ và Patient 360")).toBeTruthy();
  });

  it("a_search_with_no_match_says_so", async () => {
    renderGuide();
    await screen.findByText("Hồ sơ và Patient 360");
    await userEvent.type(screen.getByLabelText("Tìm chủ đề hoặc vai trò"), "zzz");
    expect(screen.getByText(/Không tìm thấy/)).toBeTruthy();
  });

  it("choosing_an_article_opens_it_on_the_address", async () => {
    renderGuide();
    await userEvent.click(await screen.findByText("CSKH chủ động"));
    expect(nav.pushed).toEqual(["/guide?a=b"]);
  });

  it("an_open_article_shows_its_markdown_and_keeps_injected_markup_as_text", async () => {
    nav.search = "a=b";
    renderGuide();
    expect(await screen.findByRole("heading", { name: "Cách thực hiện" })).toBeTruthy();
    expect(screen.getByText("Hôm nay").tagName).toBe("STRONG");
    expect(screen.getByText("<script>alert(1)</script>")).toBeTruthy();
    await waitFor(() => {
      expect(document.querySelector("script")).toBeNull();
    });
  });

  it("an_empty_guide_explains_how_to_add_articles", async () => {
    api.get.mockReset().mockImplementation(() => reply([]));
    renderGuide();
    expect(await screen.findByText("Chưa có bài hướng dẫn nào")).toBeTruthy();
  });
});
