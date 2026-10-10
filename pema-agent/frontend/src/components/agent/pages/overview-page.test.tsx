// @vitest-environment jsdom
// Tổng quan agent: what runs, with the last error of what stopped, the usage of the last days, and a warning while no
// model is set.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OverviewPage } from "./overview-page";

const MODEL_SET = {
  provider: "openai-compatible",
  model: "deepseek-chat",
  base_url: null,
  api_key: "sk-…1234",
  api_key_broken: false,
};

const USAGE = {
  today: "2026-10-10",
  days: [
    { day: "2026-10-09", turns: 4, failed: 1, input_tokens: 4000, output_tokens: 200 },
    { day: "2026-10-10", turns: 3, failed: 0, input_tokens: 3000, output_tokens: 100 },
  ],
};

/** A fake agent over the browser's fetch (an outside system): path -> JSON answer; the model is set by default. */
function fakeAgent(answers: Record<string, unknown>) {
  const all: Record<string, unknown> = {
    "/agent/v1/admin/model": MODEL_SET,
    "/agent/v1/admin/usage?days=14": USAGE,
    ...answers,
  };
  vi.stubGlobal("fetch", (url: string) =>
    Promise.resolve(new Response(JSON.stringify(all[url] ?? {}))),
  );
}

const NOTHING_RUNS = {
  "/agent/v1/admin/channels": { channels: [] },
  "/agent/v1/admin/jobs": { jobs: [] },
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the agent overview", () => {
  it("shows_a_running_channel_and_a_job_that_stopped_with_its_error", async () => {
    fakeAgent({
      "/agent/v1/admin/channels": { channels: [{ name: "zalo-a", running: true, error: null }] },
      "/agent/v1/admin/jobs": {
        jobs: [{ name: "zalo:bridge", running: false, error: "Bridge chưa sẵn sàng" }],
      },
    });

    render(<OverviewPage />);

    expect(await screen.findByText("zalo-a")).toBeTruthy();
    expect(screen.getByText("Đang chạy")).toBeTruthy();
    expect(screen.getByText("Lỗi")).toBeTruthy();
    expect(screen.getByText("Bridge chưa sẵn sàng")).toBeTruthy();
  });

  it("says_no_channel_is_running_when_the_list_is_empty", async () => {
    fakeAgent({
      "/agent/v1/admin/channels": { channels: [] },
      "/agent/v1/admin/jobs": { jobs: [] },
    });

    render(<OverviewPage />);

    expect(await screen.findByText(/Chưa có kênh nào chạy/)).toBeTruthy();
  });

  it("warns_that_the_agent_answers_nothing_while_no_model_is_set", async () => {
    fakeAgent({
      ...NOTHING_RUNS,
      "/agent/v1/admin/model": { ...MODEL_SET, model: "", api_key: "" },
    });

    render(<OverviewPage />);

    expect(await screen.findByText(/Chưa cấu hình model AI/)).toBeTruthy();
    expect(screen.getByText(/Thiếu tên model, khóa API/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Nhập ở trang Model" }).getAttribute("href")).toBe(
      "/admin/agent/model",
    );
  });

  it("has_no_model_warning_once_the_model_is_set", async () => {
    fakeAgent(NOTHING_RUNS);

    render(<OverviewPage />);

    await screen.findByText(/Chưa có kênh nào chạy/);
    expect(screen.queryByText(/Chưa cấu hình model AI/)).toBeNull();
  });

  it("shows_the_turns_and_tokens_of_today_and_of_the_fortnight", async () => {
    fakeAgent(NOTHING_RUNS);

    render(<OverviewPage />);

    expect(await screen.findByText("Lượt trả lời hôm nay")).toBeTruthy();
    expect(screen.getByText("7 lượt trong 14 ngày, 1 không thành công")).toBeTruthy();
    expect(screen.getByText("3.100")).toBeTruthy();
    expect(screen.getByText("7.300 token trong 14 ngày")).toBeTruthy();
    expect(screen.getByRole("img", { name: /Số lượt trả lời mỗi ngày/ })).toBeTruthy();
  });
});
