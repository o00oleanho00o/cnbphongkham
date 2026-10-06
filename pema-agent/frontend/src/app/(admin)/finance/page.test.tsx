// @vitest-environment jsdom
// "Tổng quan" of finance (`/finance`) against a fake of the typed client: the hero with the state of the month, the
// four numbers of the clinic (performed revenue and collected cash apart), the personal view with three and no cash,
// the bars of the team, the reconciliation card and its link, the loading line and the failure to load with a retry.
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CLOSED,
  DOCTOR,
  OWNER,
  overview,
  refused,
  renderFinance,
  ok,
} from "@/components/finance/test-support";

import FinanceOverviewPage from "./page";

const api = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock("@/lib/api/client", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api/client")>();
  return { ...actual, http: { GET: (...args: unknown[]) => api.get(...args) } };
});

beforeEach(() => {
  api.get.mockReset().mockImplementation(() => ok(overview()));
});

afterEach(() => cleanup());

describe("the overview of the clinic", () => {
  it("shows_the_hero_the_four_numbers_and_the_reconciliation_card", async () => {
    renderFinance(<FinanceOverviewPage />);

    expect(await screen.findByText("Một màn hình, nắm rõ dòng tiền")).toBeTruthy();
    expect(screen.getByText("KẾ TOÁN • ĐỐI SOÁT")).toBeTruthy();
    expect(
      screen.getByText("Kỳ 2026-09 · Doanh số thực hiện và tiền đã thu được theo dõi riêng."),
    ).toBeTruthy();
    expect(screen.getByText("Đang đối soát")).toBeTruthy();
    expect(screen.getByText("Doanh số thực hiện")).toBeTruthy();
    expect(screen.getByText("13.200.000 ₫")).toBeTruthy();
    expect(screen.getByText("Thực thu trong tháng")).toBeTruthy();
    expect(screen.getByText("11.000.000 ₫")).toBeTruthy();
    expect(screen.getByText("Công nợ hiện tại")).toBeTruthy();
    expect(screen.getByText("Tất cả hóa đơn, không chỉ trong tháng")).toBeTruthy();
    expect(screen.getByText("Tiền thủ thuật đã duyệt")).toBeTruthy();
    expect(screen.getByText("Không phải lợi nhuận phòng khám")).toBeTruthy();
    expect(screen.getByText("Lượt chờ kế toán duyệt")).toBeTruthy();
    expect(screen.getByText(/Tỷ lệ lưu theo từng lượt\./)).toBeTruthy();
  });

  it("lists_every_doctor_with_the_count_of_entries_the_fee_and_the_revenue", async () => {
    renderFinance(<FinanceOverviewPage />);

    expect(await screen.findByText("Đóng góp của đội ngũ")).toBeTruthy();
    expect(screen.getByText("BS. Lê Minh Tâm")).toBeTruthy();
    expect(screen.getByText("3 lượt · Tiền thủ thuật 90.000 ₫")).toBeTruthy();
    expect(screen.getByText("900.000 ₫")).toBeTruthy();
    expect(screen.getByText("7.200.000 ₫")).toBeTruthy();
  });

  it("opens_the_table_of_the_same_month_from_the_reconciliation_card", async () => {
    renderFinance(<FinanceOverviewPage />, { shell: { month: "2026-09" } });

    const link = await screen.findByRole("link", { name: "Mở bảng tiền thủ thuật →" });

    expect(link.getAttribute("href")).toBe("/finance/entries?month=2026-09");
  });

  it("says_the_owner_looks_at_the_clinic_and_shows_the_state_of_a_closed_month", async () => {
    api.get.mockImplementation(() => ok(overview({ period: CLOSED })));
    renderFinance(<FinanceOverviewPage />, {
      permissions: OWNER,
      role: "owner",
      shell: { isOwner: true },
    });

    expect(await screen.findByText("CHỦ PHÒNG KHÁM • TỔNG QUAN ĐIỀU HÀNH")).toBeTruthy();
    expect(screen.getByText("Đã chốt tháng")).toBeTruthy();
  });
});

describe("the personal view", () => {
  it("gives_three_numbers_and_no_cash_or_debt", async () => {
    api.get.mockImplementation(() =>
      ok(
        overview({
          scope: "own",
          summary: { revenue_vnd: 1_500_000, fee_vnd: 225_000, pending_vnd: 0 },
          team: [
            {
              doctor_id: "doc-1",
              doctor_name: "BS. Đoàn Thị Mai",
              entry_count: 3,
              revenue_vnd: 1_500_000,
              fee_vnd: 225_000,
            },
          ],
        }),
      ),
    );
    renderFinance(<FinanceOverviewPage />, {
      permissions: DOCTOR,
      role: "doctor",
      shell: { scope: "own" },
    });

    expect(await screen.findByText("GÓC NHÌN CÁ NHÂN")).toBeTruthy();
    expect(screen.getByText("Công việc được ghi nhận, thu nhập rõ ràng")).toBeTruthy();
    expect(screen.getByText("Doanh số của tôi")).toBeTruthy();
    expect(screen.getByText("Tiền chờ duyệt", { selector: "span" })).toBeTruthy();
    expect(screen.queryByText("Thực thu trong tháng")).toBeNull();
    expect(screen.queryByText("Công nợ hiện tại")).toBeNull();
    expect(screen.getByText("Chi tiết của tôi")).toBeTruthy();
  });

  it("asks_the_personal_projection_of_the_month_from_the_backend", async () => {
    renderFinance(<FinanceOverviewPage />, { shell: { scope: "own", month: "2026-08" } });

    await waitFor(() => expect(api.get).toHaveBeenCalled());
    const options = api.get.mock.calls[0]?.[1] as { params: { query: Record<string, string> } };
    expect(api.get.mock.calls[0]?.[0]).toBe("/api/v1/finance/overview");
    expect(options.params.query).toEqual({ month: "2026-08", scope: "own" });
  });
});

describe("loading and failure", () => {
  it("shows_the_loading_line_before_the_first_answer", async () => {
    api.get.mockImplementation(() => new Promise(() => undefined));
    renderFinance(<FinanceOverviewPage />);

    expect(await screen.findByText("Đang tải dữ liệu…")).toBeTruthy();
  });

  it("says_it_is_not_connected_with_the_reason_and_loads_again_on_retry", async () => {
    const user = userEvent.setup();
    api.get.mockImplementation(() => refused(500, "internal", "Lỗi máy chủ"));
    renderFinance(<FinanceOverviewPage />);

    expect(await screen.findByText("Chưa kết nối dữ liệu tài chính: Lỗi máy chủ")).toBeTruthy();
    api.get.mockImplementation(() => ok(overview()));
    await user.click(screen.getByRole("button", { name: "Thử lại" }));

    expect(await screen.findByText("Một màn hình, nắm rõ dòng tiền")).toBeTruthy();
  });
});
