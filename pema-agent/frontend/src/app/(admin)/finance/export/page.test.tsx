// @vitest-environment jsdom
// "Xuất CSV" (`/finance/export`): the month and the projection of the header, the name of the file, the download
// through a blob and the old sentence when the file cannot be made.
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderFinance } from "@/components/finance/test-support";

import FinanceExportPage from "./page";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("the export of a month", () => {
  it("says_which_month_and_which_projection_is_exported_and_the_name_of_the_file", () => {
    renderFinance(<FinanceExportPage />, { shell: { month: "2026-08", scope: "own" } });

    expect(screen.getByText("2026-08")).toBeTruthy();
    expect(screen.getByText("Cá nhân")).toBeTruthy();
    expect(screen.getByText("Pema-tien-thu-thuat-2026-08.csv")).toBeTruthy();
  });

  it("asks_the_file_with_the_session_and_saves_it_under_the_old_name", async () => {
    const user = userEvent.setup();
    const fetchSpy = vi.fn((..._args: [string, RequestInit]) =>
      Promise.resolve(new Response("Ngay,Ho so\r\n", { status: 200 })),
    );
    vi.stubGlobal("fetch", fetchSpy);
    const created = vi.fn(() => "blob:finance");
    URL.createObjectURL = created;
    URL.revokeObjectURL = vi.fn();
    const names: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      names.push(this.download);
    });
    renderFinance(<FinanceExportPage />, { shell: { month: "2026-09", scope: "clinic" } });

    await user.click(screen.getByRole("button", { name: "Tải CSV cho Excel" }));

    await waitFor(() => expect(names).toEqual(["Pema-tien-thu-thuat-2026-09.csv"]));
    expect(fetchSpy.mock.calls[0]?.[0]).toBe("/api/v1/finance/export?month=2026-09&scope=clinic");
    expect(fetchSpy.mock.calls[0]?.[1].credentials).toBe("include");
    expect(created).toHaveBeenCalled();
  });

  it("says_the_old_sentence_when_the_file_cannot_be_made", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("offline"))),
    );
    renderFinance(<FinanceExportPage />);

    await user.click(screen.getByRole("button", { name: "Tải CSV cho Excel" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Không xuất được bảng");
  });
});
