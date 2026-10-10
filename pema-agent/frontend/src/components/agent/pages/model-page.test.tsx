// @vitest-environment jsdom
// Model của agent: only the fields the person changed go to the agent, the key is never shown back, a preset fills the
// form, and the model field offers the provider's list.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ModelPage } from "./model-page";

const SHOWN = {
  provider: "openai-compatible",
  model: "deepseek-chat",
  base_url: null,
  reasoning: null,
  dialect: null,
  api_key: "sk-…1234",
  api_key_broken: false,
  sources: { provider: "profile", model: "profile", api_key: "db" },
};

type Call = { method: string; url: string; body: unknown };

/** A fake agent over the browser's fetch (an outside system); every call is written down. */
function fakeAgent(listing: { status: number; body: unknown } = LISTED): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const body = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : undefined;
    calls.push({ method: init?.method ?? "GET", url, body });
    if (url === "/agent/v1/admin/model/list") {
      return Promise.resolve(
        new Response(JSON.stringify(listing.body), { status: listing.status }),
      );
    }
    const saved = { ...SHOWN, ...(body as object | undefined) };
    return Promise.resolve(new Response(JSON.stringify(saved)));
  });
  return calls;
}

const LISTED = {
  status: 200,
  body: { ok: true, models: ["deepseek-v4-flash", "deepseek-v4-pro"] },
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the model page", () => {
  it("saves_only_the_fields_that_changed", async () => {
    const calls = fakeAgent();
    render(<ModelPage />);
    const model = await screen.findByLabelText(/^Model/);

    fireEvent.change(model, { target: { value: "deepseek-reasoner" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));

    expect(await screen.findByText(/Đã lưu/)).toBeTruthy();
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ model: "deepseek-reasoner" });
  });

  it("shows_the_stored_key_masked_and_leaves_the_key_field_empty", async () => {
    fakeAgent();
    render(<ModelPage />);

    expect(await screen.findByText("Đã có khóa: sk-…1234")).toBeTruthy();
    expect((screen.getByLabelText(/^Khóa mới/) as HTMLInputElement).value).toBe("");
  });

  it("fills_the_form_from_a_preset_without_saving", async () => {
    const calls = fakeAgent();
    render(<ModelPage />);
    await screen.findByLabelText(/^Model/);

    fireEvent.click(screen.getByRole("button", { name: "Anthropic" }));

    expect((screen.getByLabelText(/^Model/) as HTMLInputElement).value).toBe("claude-sonnet-5-5");
    expect((screen.getByLabelText(/^Nhà cung cấp/) as HTMLSelectElement).value).toBe("anthropic");
    expect((screen.getByLabelText(/^Địa chỉ API/) as HTMLInputElement).value).toBe("");
    expect(screen.getByText(/Đã điền mẫu Anthropic/)).toBeTruthy();
    expect(calls.filter((c) => c.method !== "GET")).toEqual([]);
  });

  it("saves_the_preset_with_the_pasted_key", async () => {
    const calls = fakeAgent();
    render(<ModelPage />);
    await screen.findByLabelText(/^Model/);
    fireEvent.click(screen.getByRole("button", { name: "DeepSeek" }));
    fireEvent.change(screen.getByLabelText(/^Khóa mới/), { target: { value: "sk-new-key" } });

    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));

    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({
      model: "deepseek-v4-pro",
      base_url: "https://api.deepseek.com",
      dialect: "deepseek",
      api_key: "sk-new-key",
    });
  });

  it("offers_the_providers_models_asked_with_what_is_typed", async () => {
    const calls = fakeAgent();
    const { container } = render(<ModelPage />);
    await screen.findByLabelText(/^Model/);
    fireEvent.change(screen.getByLabelText(/^Khóa mới/), { target: { value: "sk-typed" } });

    fireEvent.click(screen.getByRole("button", { name: "Lấy danh sách model từ nhà cung cấp" }));

    expect(await screen.findByText(/Có 2 model/)).toBeTruthy();
    const options = [...container.querySelectorAll("datalist option")].map((o) =>
      o.getAttribute("value"),
    );
    expect(options).toEqual(["deepseek-v4-flash", "deepseek-v4-pro"]);
    expect(calls.find((c) => c.url === "/agent/v1/admin/model/list")?.body).toEqual({
      provider: "openai-compatible",
      base_url: "",
      api_key: "sk-typed",
    });
  });

  it("says_the_model_can_still_be_typed_when_the_provider_refuses_the_list", async () => {
    fakeAgent({ status: 502, body: { ok: false, models: [], error_kind: "auth" } });
    render(<ModelPage />);
    await screen.findByLabelText(/^Model/);

    fireEvent.click(screen.getByRole("button", { name: "Lấy danh sách model từ nhà cung cấp" }));

    expect(
      await screen.findByText("Khóa API sai hoặc hết hạn. Vẫn gõ tên model tay được."),
    ).toBeTruthy();
  });
});
