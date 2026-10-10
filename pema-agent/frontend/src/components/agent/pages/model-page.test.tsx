// @vitest-environment jsdom
// Model của agent: the list of models grouped by provider with the one in use, using / testing / removing one, adding
// one from a preset (the chosen preset stays coloured, a second key of the same provider gets its own label), changing
// one by sending only what changed, and the model field offering the provider's list.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ModelPage } from "./model-page";

const entry = (id: string, label: string, model: string, host: string, extra = {}) => ({
  id: id.repeat(32),
  label,
  provider: "openai-compatible",
  model,
  base_url: host ? `https://${host}` : null,
  reasoning: null,
  dialect: null,
  api_key: "sk-…1234",
  has_key: true,
  api_key_broken: false,
  active: false,
  ...extra,
});

const ENTRIES = [
  entry("a", "DeepSeek công ty", "deepseek-v4-pro", "api.deepseek.com", { active: true }),
  entry("b", "DeepSeek dự phòng", "deepseek-v4-flash", "api.deepseek.com"),
  entry("c", "OpenAI chăm sóc", "gpt-5-mini", "api.openai.com", { api_key: "", has_key: false }),
];

const SHOWN = {
  provider: "openai-compatible",
  model: "deepseek-v4-pro",
  base_url: "https://api.deepseek.com",
  api_key: "sk-…1234",
  api_key_broken: false,
  sources: { model: "db", api_key: "db" },
  stored: true,
  entry_id: "a".repeat(32),
};

type Reply = { status?: number; body: unknown };
type Call = { method: string; url: string; body: unknown };

const LISTED: Reply = { body: { ok: true, models: ["deepseek-v4-flash", "deepseek-v4-pro"] } };

/** A fake agent over the browser's fetch (an outside system); every call is written down. */
function fakeAgent(answers: Record<string, Reply> = {}, shown: object = SHOWN): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const body = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : undefined;
    const method = init?.method ?? "GET";
    calls.push({ method, url, body });
    const known = answers[`${method} ${url}`];
    const reply = known ?? defaultReply(method, url, shown);
    return Promise.resolve(
      new Response(JSON.stringify(reply.body), { status: reply.status ?? 200 }),
    );
  });
  return calls;
}

function defaultReply(method: string, url: string, shown: object): Reply {
  if (url === "/agent/v1/admin/model") return { body: shown };
  if (url === "/agent/v1/admin/model/entries" && method === "GET") {
    return { body: { entries: ENTRIES } };
  }
  if (url === "/agent/v1/admin/model/list") return LISTED;
  if (url.endsWith("/test"))
    return { body: { ok: true, model: "deepseek-v4-pro", latency_ms: 350 } };
  return { body: {} };
}

const mutations = (calls: Call[]) => calls.filter((c) => c.method !== "GET");

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the list of models", () => {
  it("groups_the_models_by_provider_with_counts_and_marks_the_one_in_use", async () => {
    fakeAgent();
    render(<ModelPage />);

    const deepseek = await screen.findByRole("region", { name: "Model DeepSeek" });
    const openai = screen.getByRole("region", { name: "Model OpenAI" });
    expect(within(deepseek).getAllByRole("listitem")).toHaveLength(2);
    expect(within(openai).getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getByText("2 DeepSeek · 1 OpenAI")).toBeTruthy();
    expect(within(deepseek).getByText("Đang dùng")).toBeTruthy();
    expect(within(openai).getByText("Chưa có khóa")).toBeTruthy();
    expect(screen.getByText("(từ danh sách: DeepSeek công ty)")).toBeTruthy();
  });

  it("uses_the_chosen_model_and_reloads_the_list", async () => {
    const calls = fakeAgent();
    render(<ModelPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Dùng DeepSeek dự phòng" }));

    expect(await screen.findByText(/Đang dùng DeepSeek dự phòng/)).toBeTruthy();
    expect(mutations(calls)).toEqual([
      {
        method: "POST",
        url: `/agent/v1/admin/model/entries/${"b".repeat(32)}/use`,
        body: undefined,
      },
    ]);
  });

  it("tests_one_model_of_the_list_and_says_the_outcome", async () => {
    fakeAgent({
      [`POST /agent/v1/admin/model/entries/${"c".repeat(32)}/test`]: {
        status: 502,
        body: { ok: false, model: "gpt-5-mini", error_kind: "auth" },
      },
    });
    render(<ModelPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Gọi thử OpenAI chăm sóc" }));

    expect(await screen.findByText("Khóa API sai hoặc hết hạn")).toBeTruthy();
  });

  it("removes_a_model_only_after_the_confirmation", async () => {
    const calls = fakeAgent();
    render(<ModelPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Xóa DeepSeek dự phòng" }));

    const question = await screen.findByText("Xóa DeepSeek dự phòng?");
    const dialog = question.closest<HTMLElement>('[role="dialog"]');
    expect(mutations(calls)).toEqual([]);
    fireEvent.click(within(dialog as HTMLElement).getByRole("button", { name: "Xóa model" }));

    await waitFor(() =>
      expect(mutations(calls)).toEqual([
        {
          method: "DELETE",
          url: `/agent/v1/admin/model/entries/${"b".repeat(32)}`,
          body: undefined,
        },
      ]),
    );
  });

  it("says_the_list_is_empty_and_the_agent_follows_its_profile_when_nothing_was_stored", async () => {
    fakeAgent(
      { "GET /agent/v1/admin/model/entries": { body: { entries: [] } } },
      { ...SHOWN, stored: false, entry_id: null, api_key: "" },
    );
    render(<ModelPage />);

    expect(await screen.findByText(/Chưa có model nào trong danh sách/)).toBeTruthy();
    expect(screen.getByText("(theo cấu hình của profile)")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Về cấu hình profile" })).toBeNull();
  });
});

describe("adding a model", () => {
  async function openForm() {
    render(<ModelPage />);
    fireEvent.click(await screen.findByRole("button", { name: "+ Thêm model" }));
    await screen.findByRole("heading", { name: "Model mới" });
  }

  it("colours_the_chosen_preset_and_gives_a_second_key_of_the_provider_its_own_label", async () => {
    fakeAgent();
    await openForm();
    const deepseek = screen.getByRole("button", { name: "DeepSeek" });
    const openai = screen.getByRole("button", { name: "OpenAI" });
    const idleClass = openai.className;

    fireEvent.click(deepseek);

    expect(deepseek.getAttribute("aria-pressed")).toBe("true");
    expect(openai.getAttribute("aria-pressed")).toBe("false");
    expect(deepseek.className).not.toBe(idleClass);
    expect((screen.getByLabelText(/^Tên trong danh sách/) as HTMLInputElement).value).toBe(
      "DeepSeek 3",
    );
    expect((screen.getByLabelText(/^Model/) as HTMLInputElement).value).toBe("deepseek-v4-pro");
  });

  it("sends_the_preset_with_the_pasted_key_and_leaves_out_the_empty_fields", async () => {
    const calls = fakeAgent();
    await openForm();
    fireEvent.click(screen.getByRole("button", { name: "Anthropic" }));
    fireEvent.change(screen.getByLabelText(/^Khóa API/), { target: { value: "sk-new-key" } });

    fireEvent.click(screen.getByRole("button", { name: "Thêm vào danh sách" }));

    await waitFor(() => expect(mutations(calls)).toHaveLength(1));
    expect(mutations(calls)[0]).toEqual({
      method: "POST",
      url: "/agent/v1/admin/model/entries",
      body: {
        label: "Anthropic",
        provider: "anthropic",
        model: "claude-sonnet-5-5",
        api_key: "sk-new-key",
      },
    });
    expect(await screen.findByText("Đã thêm Anthropic vào danh sách.")).toBeTruthy();
  });

  it("keeps_a_label_the_person_typed_when_a_preset_is_chosen_after", async () => {
    fakeAgent();
    await openForm();
    fireEvent.change(screen.getByLabelText(/^Tên trong danh sách/), {
      target: { value: "Của tôi" },
    });

    fireEvent.click(screen.getByRole("button", { name: "DeepSeek" }));

    expect((screen.getByLabelText(/^Tên trong danh sách/) as HTMLInputElement).value).toBe(
      "Của tôi",
    );
  });

  it("offers_the_providers_models_asked_with_what_is_typed_and_no_empty_fields", async () => {
    const calls = fakeAgent();
    await openForm();
    fireEvent.change(screen.getByLabelText(/^Khóa API/), { target: { value: "sk-typed" } });

    fireEvent.click(screen.getByRole("button", { name: "Lấy danh sách model từ nhà cung cấp" }));

    expect(await screen.findByText(/Có 2 model/)).toBeTruthy();
    const options = [...document.querySelectorAll("datalist option")].map((o) =>
      o.getAttribute("value"),
    );
    expect(options).toEqual(["deepseek-v4-flash", "deepseek-v4-pro"]);
    expect(calls.find((c) => c.url === "/agent/v1/admin/model/list")?.body).toEqual({
      provider: "openai-compatible",
      api_key: "sk-typed",
    });
  });

  it("says_the_model_can_still_be_typed_when_the_provider_refuses_the_list", async () => {
    fakeAgent({
      "POST /agent/v1/admin/model/list": {
        status: 502,
        body: { ok: false, models: [], error_kind: "auth" },
      },
    });
    await openForm();

    fireEvent.click(screen.getByRole("button", { name: "Lấy danh sách model từ nhà cung cấp" }));

    expect(
      await screen.findByText("Khóa API sai hoặc hết hạn. Vẫn gõ tên model tay được."),
    ).toBeTruthy();
  });

  it("closes_the_form_without_sending_anything_on_cancel", async () => {
    const calls = fakeAgent();
    await openForm();

    fireEvent.click(screen.getByRole("button", { name: "Hủy" }));

    expect(await screen.findByRole("heading", { name: "Danh sách model" })).toBeTruthy();
    expect(mutations(calls)).toEqual([]);
  });
});

describe("changing a model", () => {
  async function openEdit() {
    render(<ModelPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Sửa DeepSeek dự phòng" }));
    await screen.findByRole("heading", { name: "Sửa DeepSeek dự phòng" });
  }

  it("sends_only_the_fields_that_changed_and_never_shows_the_key", async () => {
    const calls = fakeAgent();
    await openEdit();
    expect((screen.getByLabelText(/^Khóa API/) as HTMLInputElement).value).toBe("");

    fireEvent.change(screen.getByLabelText(/^Model$/), { target: { value: "deepseek-reasoner" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu thay đổi" }));

    await waitFor(() => expect(mutations(calls)).toHaveLength(1));
    expect(mutations(calls)[0]).toEqual({
      method: "PATCH",
      url: `/agent/v1/admin/model/entries/${"b".repeat(32)}`,
      body: { model: "deepseek-reasoner" },
    });
  });

  it("asks_for_the_list_with_the_stored_key_of_that_model", async () => {
    const calls = fakeAgent();
    await openEdit();

    fireEvent.click(screen.getByRole("button", { name: "Lấy danh sách model từ nhà cung cấp" }));

    await screen.findByText(/Có 2 model/);
    expect(calls.find((c) => c.url === "/agent/v1/admin/model/list")?.body).toEqual({
      provider: "openai-compatible",
      base_url: "https://api.deepseek.com",
      entry_id: "b".repeat(32),
    });
  });
});
