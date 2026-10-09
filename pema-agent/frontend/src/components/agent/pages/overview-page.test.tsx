// @vitest-environment jsdom
// Tổng quan agent: what runs, with the last error of what stopped.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OverviewPage } from "./overview-page";

/** A fake agent over the browser's fetch (an outside system): path -> JSON answer. */
function fakeAgent(answers: Record<string, unknown>) {
  vi.stubGlobal("fetch", (url: string) =>
    Promise.resolve(new Response(JSON.stringify(answers[url] ?? {}))),
  );
}

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
});
