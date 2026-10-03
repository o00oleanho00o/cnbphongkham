// @vitest-environment jsdom
// "Hỏi Pema" against a fake of the typed client: a question goes out as `?q=` (cleaned), the answer is the passages
// with a link to their article, an empty answer says the guide has nothing, a failure keeps the question.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SessionProvider } from "@/lib/session/session-context";

import AskPage from "./page";

const api = vi.hoisted(() => ({ post: vi.fn() }));

// The HTTP client is the unmanaged dependency: a hand-written fake of the one route the page calls.
vi.mock("@/lib/api/client", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api/client")>();
  return { ...actual, http: { POST: (...args: unknown[]) => api.post(...args) } };
});

const HIT = {
  article_id: "guide-cskh-viec-hom-nay",
  article_title: "CSKH chủ động: xử lý việc hôm nay",
  heading: "Cách thực hiện",
  passage: "1. Mở **Hôm nay**. Lọc theo trạng thái.",
  score: 2.1,
};

const ok = (hits: unknown[]) =>
  Promise.resolve({ data: { hits }, response: new Response(null, { status: 200 }) });

function renderAsk() {
  return render(
    <SessionProvider
      user={{
        id: "00000000-0000-4000-8000-000000000004",
        clinic_id: "clinic",
        clinic_name: "Phòng khám Pema (dữ liệu mẫu)",
        display_name: "Mai Anh",
        role: "cs_staff",
      }}
      permissions={["kb.read"]}
      onLoggedOut={() => undefined}
    >
      <AskPage />
    </SessionProvider>,
  );
}

const questionSent = (): string | undefined =>
  (api.post.mock.calls.at(-1)?.[1] as { body: { question: string } } | undefined)?.body.question;

beforeEach(() => {
  api.post.mockReset().mockImplementation(() => ok([HIT]));
});

afterEach(cleanup);

describe("ask page", () => {
  it("offers_suggested_questions_before_the_first_question", () => {
    renderAsk();
    expect(screen.getByRole("button", { name: "Làm sao xử lý việc CSKH hôm nay?" })).toBeTruthy();
  });

  it("sends_the_cleaned_question_and_shows_the_passage_with_a_link_to_its_article", async () => {
    renderAsk();
    await userEvent.type(screen.getByLabelText("Câu hỏi"), "  dời   lịch  {Enter}");
    const link = await screen.findByRole("link", { name: "CSKH chủ động: xử lý việc hôm nay" });
    expect(link.getAttribute("href")).toBe("/guide?a=guide-cskh-viec-hom-nay");
    expect(questionSent()).toBe("dời lịch");
    expect(screen.getByText("Hôm nay").tagName).toBe("STRONG");
  });

  it("the_ask_button_stays_off_for_a_blank_question", async () => {
    renderAsk();
    await userEvent.type(screen.getByLabelText("Câu hỏi"), "   ");
    expect((screen.getByRole("button", { name: "Hỏi" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("a_question_the_guide_cannot_answer_says_so", async () => {
    api.post.mockReset().mockImplementation(() => ok([]));
    renderAsk();
    await userEvent.type(screen.getByLabelText("Câu hỏi"), "zzz{Enter}");
    expect(await screen.findByText(/Chưa thấy nội dung này trong hướng dẫn/)).toBeTruthy();
  });

  it("a_failed_request_keeps_the_question_and_says_why", async () => {
    api.post.mockReset().mockImplementation(() => Promise.reject(new Error("offline")));
    renderAsk();
    await userEvent.type(screen.getByLabelText("Câu hỏi"), "dời lịch{Enter}");
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText("dời lịch")).toBeTruthy();
  });

  it("a_suggested_question_is_asked_with_one_tap", async () => {
    renderAsk();
    await userEvent.click(screen.getByRole("button", { name: "Làm sao xử lý việc CSKH hôm nay?" }));
    await waitFor(() => expect(questionSent()).toBe("Làm sao xử lý việc CSKH hôm nay?"));
  });
});
