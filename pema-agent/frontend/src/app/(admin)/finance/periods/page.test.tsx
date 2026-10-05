// @vitest-environment jsdom
// "Chốt kỳ" (`/finance/periods`) against a fake of the typed client: the months with their state, the sentence
// that says why an open month cannot be closed, "Chốt tháng" only on a month that can close and
// "Xác nhận đã chi" only on a closed one (both only for whoever may write), the dialogs and what they send.
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ok, refused, renderFinance } from "@/components/finance/test-support";
import type { Schemas } from "@/lib/api";

import FinancePeriodsPage from "./page";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));

vi.mock("@/lib/api/client", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    http: {
      GET: (...args: unknown[]) => api.get(...args),
      POST: (...args: unknown[]) => api.post(...args),
    },
  };
});

function period(over: Partial<Schemas["PeriodRowOut"]> = {}): Schemas["PeriodRowOut"] {
  return {
    month: "2026-08",
    status: "open",
    entry_count: 12,
    pending_count: 0,
    closable: true,
    blocker: null,
    ...over,
  };
}

const LIST: Schemas["PeriodListOut"] = {
  today: "2026-09-20",
  items: [
    period({
      month: "2026-09",
      entry_count: 12,
      pending_count: 4,
      closable: false,
      blocker: "Chỉ chốt tháng đã kết thúc",
    }),
    period(),
    period({
      month: "2026-07",
      status: "closed",
      closable: false,
      closed_at: "2026-08-02T09:00:00+07:00",
    }),
    period({
      month: "2026-06",
      status: "paid",
      closable: false,
      closed_at: "2026-07-02T09:00:00+07:00",
      paid_at: "2026-07-05T09:00:00+07:00",
      reference: "PC-0006",
    }),
    period({ month: "2026-05", entry_count: 0, closable: false, blocker: "Kỳ không có dữ liệu" }),
  ],
};

beforeEach(() => {
  api.get.mockReset().mockImplementation(() => ok(LIST));
  api.post.mockReset().mockImplementation(() => ok({ month: "2026-08", status: "closed" }));
});

afterEach(() => cleanup());

describe("the months", () => {
  it("shows_the_state_the_counts_and_the_next_step_of_each_month", async () => {
    renderFinance(<FinancePeriodsPage />);

    expect(await screen.findByText("Chốt kỳ")).toBeTruthy();
    expect(screen.getByText("Chỉ chốt tháng đã kết thúc")).toBeTruthy();
    expect(screen.getByText("Kỳ không có dữ liệu")).toBeTruthy();
    expect(screen.getByText("Sẵn sàng chốt")).toBeTruthy();
    expect(screen.getByText("Đã chốt 02/08/2026")).toBeTruthy();
    expect(screen.getByText("Đã chi 05/07/2026 · Chứng từ PC-0006")).toBeTruthy();
    const links = screen.getAllByRole("link", { name: /^Mở bảng tiền thủ thuật tháng/ });
    expect(links[1]?.getAttribute("href")).toBe("/finance/entries?month=2026-08");
  });

  it("offers_to_close_only_a_month_that_can_close_and_to_confirm_the_payout_only_of_a_closed_one", async () => {
    renderFinance(<FinancePeriodsPage />);
    await screen.findByText("Chốt kỳ");

    expect(screen.getAllByRole("button", { name: /^Chốt tháng / })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Chốt tháng 2026-08" })).toBeTruthy();
    expect(screen.getAllByRole("button", { name: /^Xác nhận đã chi/ })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Xác nhận đã chi tháng 2026-07" })).toBeTruthy();
  });

  it("gives_a_reader_the_list_without_any_button_that_changes_a_month", async () => {
    renderFinance(<FinancePeriodsPage />, { shell: { canWrite: false } });
    await screen.findByText("Chốt kỳ");

    expect(screen.queryByRole("button", { name: /^Chốt tháng / })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Xác nhận đã chi/ })).toBeNull();
    expect(screen.getAllByRole("link", { name: /^Mở bảng/ }).length).toBeGreaterThan(0);
  });
});

describe("closing and confirming the payout", () => {
  it("closes_the_month_after_the_question_and_loads_the_list_again", async () => {
    const user = userEvent.setup();
    const reload = vi.fn();
    renderFinance(<FinancePeriodsPage />, { shell: { reload } });

    await user.click(await screen.findByRole("button", { name: "Chốt tháng 2026-08" }));
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText("Chốt số liệu tháng 2026-08? Các lượt trong kỳ sẽ bị khóa."),
    ).toBeTruthy();
    await user.click(within(dialog).getByRole("button", { name: "Chốt tháng" }));

    await waitFor(() => expect(reload).toHaveBeenCalled());
    const [path, options] = api.post.mock.calls[0] as [string, { params: unknown }];
    expect(path).toBe("/api/v1/finance/periods/{month}/close");
    expect(options.params).toEqual({ path: { month: "2026-08" } });
  });

  it("sends_the_voucher_of_the_payout", async () => {
    const user = userEvent.setup();
    renderFinance(<FinancePeriodsPage />);

    await user.click(await screen.findByRole("button", { name: "Xác nhận đã chi tháng 2026-07" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/^Mã chứng từ chi/), "PC-0007");
    await user.click(within(dialog).getByRole("button", { name: "Xác nhận đã chi" }));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const [path, options] = api.post.mock.calls[0] as [string, { params: unknown; body: unknown }];
    expect(path).toBe("/api/v1/finance/periods/{month}/pay");
    expect(options.params).toEqual({ path: { month: "2026-07" } });
    expect(options.body).toEqual({ reference: "PC-0007" });
  });

  it("keeps_the_dialog_and_shows_the_sentence_of_the_backend_when_it_refuses", async () => {
    const user = userEvent.setup();
    api.post.mockImplementation(() => refused(409, "invalid_state", "Còn lượt chờ duyệt"));
    renderFinance(<FinancePeriodsPage />);
    await user.click(await screen.findByRole("button", { name: "Chốt tháng 2026-08" }));
    const dialog = await screen.findByRole("dialog");

    await user.click(within(dialog).getByRole("button", { name: "Chốt tháng" }));

    expect((await within(dialog).findByRole("alert")).textContent).toContain("Còn lượt chờ duyệt");
  });
});
