// @vitest-environment jsdom
// Model của agent: only the fields the person changed go to the agent, and the key is never shown back.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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
function fakeAgent(): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const body = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : undefined;
    calls.push({ method: init?.method ?? "GET", url, body });
    const saved = { ...SHOWN, ...(body as object | undefined) };
    return Promise.resolve(new Response(JSON.stringify(saved)));
  });
  return calls;
}

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
});
