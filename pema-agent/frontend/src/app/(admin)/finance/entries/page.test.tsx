// @vitest-environment jsdom
// "Tiền thủ thuật" (`/finance/entries`) against a fake of the typed client: the table of the month with Duyệt and
// Hủy per row only while the month is open and the caller may write, the cancel dialog that needs a reason, the form
// that records a performed procedure (what is sent: basis points, the invoice, the performers; what is told before
// anything is sent), the buttons that end a month with their dialogs, and the export that fails with the old sentence.
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CLOSED,
  DOCTOR,
  PAID,
  entries,
  invoice,
  ok,
  pageOf,
  refused,
  renderFinance,
  row,
} from "@/components/finance/test-support";
import type { Schemas } from "@/lib/api";
import type { FinanceEntries } from "@/lib/finance/finance-view";

import FinanceEntriesPage from "./page";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
const nav = vi.hoisted(() => ({ search: "" }));
const reload = vi.hoisted(() => vi.fn());

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
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(nav.search) }));

const SERVICES = [
  { id: "svc-1", name: "Tái khám & đánh giá", price_vnd: 300_000, rate_bp: 1000, basis: "net" },
  { id: "svc-2", name: "Laser theo chỉ định", price_vnd: 2_500_000, rate_bp: 2000, basis: "net" },
] as Schemas["ServiceOut"][];

const PATIENT = {
  id: "patient-1",
  code: "P001",
  full_name: "Nguyễn Thu Hà",
} as Schemas["PatientOut"];

function answers(table: FinanceEntries = entries()) {
  api.get.mockReset().mockImplementation((path: string) => {
    if (path === "/api/v1/finance/entries") return ok(table);
    if (path === "/api/v1/services") return ok(SERVICES);
    if (path === "/api/v1/finance/invoices")
      return ok(pageOf([invoice({ patient_id: "patient-1" })]));
    if (path === "/api/v1/patients") return ok(pageOf([PATIENT]));
    return refused(404, "not_found", "?");
  });
}

function postedTo(path: string): { params?: { path?: Record<string, string> }; body?: unknown } {
  const call = api.post.mock.calls.find((c) => c[0] === path);
  return (call?.[1] ?? {}) as { params?: { path?: Record<string, string> }; body?: unknown };
}

beforeEach(() => {
  nav.search = "";
  reload.mockReset();
  answers();
  api.post.mockReset().mockImplementation(() => ok({}, 201));
});

afterEach(() => cleanup());

const shell = () => ({ reload });

describe("the table of a month", () => {
  it("shows_a_row_per_performer_with_revenue_base_times_rate_basis_fee_and_status", async () => {
    renderFinance(<FinanceEntriesPage />, { shell: shell() });

    expect(await screen.findByText("Bảng tiền thủ thuật • 2026-09")).toBeTruthy();
    for (const header of [
      "Ngày / Hồ sơ",
      "Thủ thuật / Bác sĩ",
      "Doanh số phân bổ",
      "Cơ sở × tỷ lệ",
      "Tiền thủ thuật",
      "Trạng thái",
    ]) {
      expect(screen.getByRole("columnheader", { name: header })).toBeTruthy();
    }
    expect(screen.getAllByText("300.000 ₫ × 10%")).toHaveLength(2);
    expect(screen.getAllByText("Giá sau giảm")).toHaveLength(2);
    expect(screen.getAllByText("30.000 ₫")).toHaveLength(2);
    expect(screen.getByText("Chờ duyệt")).toBeTruthy();
    expect(screen.getByText("Đã duyệt")).toBeTruthy();
    expect(screen.getByText("Đang đối soát")).toBeTruthy();
  });

  it("offers_approve_only_on_a_pending_row_and_cancel_on_every_live_row", async () => {
    renderFinance(<FinanceEntriesPage />, { shell: shell() });
    await screen.findByText("Bảng tiền thủ thuật • 2026-09");

    expect(screen.getAllByRole("button", { name: /^Duyệt / })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: /^Hủy / })).toHaveLength(2);
  });

  it("says_the_month_has_no_entry_when_the_table_is_empty", async () => {
    answers(entries({ rows: [] }));
    renderFinance(<FinanceEntriesPage />, { shell: shell() });

    expect(await screen.findByText("Chưa có lượt thủ thuật trong kỳ này.")).toBeTruthy();
  });

  it("gives_a_cancelled_row_its_reason_and_no_buttons", async () => {
    answers(entries({ rows: [row({ status: "void", note: "Nhập nhầm hồ sơ" })] }));
    renderFinance(<FinanceEntriesPage />, { shell: shell() });

    expect(await screen.findByText("Đã hủy")).toBeTruthy();
    expect(screen.getByText("Lý do: Nhập nhầm hồ sơ")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Hủy / })).toBeNull();
  });

  it("approves_an_entry_and_loads_the_month_again", async () => {
    const user = userEvent.setup();
    renderFinance(<FinanceEntriesPage />, { shell: shell() });

    await user.click(await screen.findByRole("button", { name: /^Duyệt / }));

    await waitFor(() => expect(reload).toHaveBeenCalled());
    expect(postedTo("/api/v1/finance/entries/{entry_id}/approve").params?.path).toEqual({
      entry_id: "entry-1",
    });
  });
});

describe("cancelling an entry", () => {
  it("needs_a_reason_before_it_can_be_confirmed_and_sends_it", async () => {
    const user = userEvent.setup();
    renderFinance(<FinanceEntriesPage />, { shell: shell() });
    await user.click((await screen.findAllByRole("button", { name: /^Hủy / }))[0] as HTMLElement);
    const dialog = await screen.findByRole("dialog");

    const confirm = within(dialog).getByRole("button", { name: "Hủy lượt" }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    await user.type(
      within(dialog).getByLabelText(/^Lý do hủy lượt chưa thu tiền/),
      "Nhập nhầm hồ sơ",
    );
    await user.click(confirm);

    await waitFor(() => expect(reload).toHaveBeenCalled());
    const sent = postedTo("/api/v1/finance/entries/{entry_id}/void");
    expect(sent.body).toEqual({ reason: "Nhập nhầm hồ sơ" });
    expect(sent.params?.path).toEqual({ entry_id: "entry-1" });
  });

  it("keeps_the_dialog_open_and_shows_the_sentence_of_the_backend_when_money_was_received", async () => {
    const user = userEvent.setup();
    api.post.mockImplementation(() =>
      refused(409, "invalid_state", "Lượt đã thu tiền; cần quy trình hoàn/điều chỉnh riêng"),
    );
    renderFinance(<FinanceEntriesPage />, { shell: shell() });
    await user.click((await screen.findAllByRole("button", { name: /^Hủy / }))[0] as HTMLElement);
    const dialog = await screen.findByRole("dialog");

    await user.type(within(dialog).getByLabelText(/^Lý do hủy/), "Hủy");
    await user.click(within(dialog).getByRole("button", { name: "Hủy lượt" }));

    expect((await within(dialog).findByRole("alert")).textContent).toContain(
      "Lượt đã thu tiền; cần quy trình hoàn/điều chỉnh riêng",
    );
    expect(reload).not.toHaveBeenCalled();
  });
});

describe("a month that is closed", () => {
  it("has_no_form_and_no_row_action_and_offers_to_confirm_the_payout", async () => {
    answers(entries({ period: CLOSED, month: "2026-08" }));
    renderFinance(<FinanceEntriesPage />, { shell: { ...shell(), month: "2026-08" } });

    expect(await screen.findByText("Bảng tiền thủ thuật • 2026-08")).toBeTruthy();
    expect(screen.getByText("Đã chốt tháng")).toBeTruthy();
    expect(screen.queryByText("+ Ghi nhận lượt thủ thuật đã hoàn tất")).toBeNull();
    expect(screen.queryByRole("button", { name: /^Duyệt / })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Hủy / })).toBeNull();
    expect(screen.queryByRole("button", { name: "Chốt tháng đã kết thúc" })).toBeNull();
    expect(screen.getByRole("button", { name: "Xác nhận đã chi" })).toBeTruthy();
  });

  it("has_nothing_left_to_do_once_it_is_paid", async () => {
    answers(entries({ period: PAID, month: "2026-07" }));
    renderFinance(<FinanceEntriesPage />, { shell: { ...shell(), month: "2026-07" } });

    expect(await screen.findByText("Đã chi")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Xác nhận đã chi" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Chốt tháng đã kết thúc" })).toBeNull();
  });

  it("asks_for_the_voucher_and_sends_it_to_confirm_the_payout", async () => {
    const user = userEvent.setup();
    answers(entries({ period: CLOSED, month: "2026-08" }));
    renderFinance(<FinanceEntriesPage />, { shell: { ...shell(), month: "2026-08" } });
    await user.click(await screen.findByRole("button", { name: "Xác nhận đã chi" }));
    const dialog = await screen.findByRole("dialog");

    await user.type(within(dialog).getByLabelText(/^Mã chứng từ chi/), "PC-0008");
    await user.click(within(dialog).getByRole("button", { name: "Xác nhận đã chi" }));

    await waitFor(() => expect(reload).toHaveBeenCalled());
    const sent = postedTo("/api/v1/finance/periods/{month}/pay");
    expect(sent.params?.path).toEqual({ month: "2026-08" });
    expect(sent.body).toEqual({ reference: "PC-0008" });
  });
});

describe("closing the month", () => {
  it("asks_the_old_question_and_closes_after_the_answer", async () => {
    const user = userEvent.setup();
    renderFinance(<FinanceEntriesPage />, { shell: shell() });

    await user.click(await screen.findByRole("button", { name: "Chốt tháng đã kết thúc" }));
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText("Chốt số liệu tháng 2026-09? Các lượt trong kỳ sẽ bị khóa."),
    ).toBeTruthy();
    await user.click(within(dialog).getByRole("button", { name: "Chốt tháng" }));

    await waitFor(() => expect(reload).toHaveBeenCalled());
    expect(postedTo("/api/v1/finance/periods/{month}/close").params?.path).toEqual({
      month: "2026-09",
    });
  });

  it("shows_why_the_backend_refuses_to_close_and_keeps_the_dialog", async () => {
    const user = userEvent.setup();
    api.post.mockImplementation(() => refused(409, "invalid_state", "Chỉ chốt tháng đã kết thúc"));
    renderFinance(<FinanceEntriesPage />, { shell: shell() });
    await user.click(await screen.findByRole("button", { name: "Chốt tháng đã kết thúc" }));
    const dialog = await screen.findByRole("dialog");

    await user.click(within(dialog).getByRole("button", { name: "Chốt tháng" }));

    expect((await within(dialog).findByRole("alert")).textContent).toContain(
      "Chỉ chốt tháng đã kết thúc",
    );
  });
});

describe("what a doctor sees", () => {
  it("is_the_own_rows_with_no_form_and_no_button_that_changes_anything", async () => {
    answers(entries({ scope: "own", can_write: false }));
    renderFinance(<FinanceEntriesPage />, {
      permissions: DOCTOR,
      role: "doctor",
      shell: { ...shell(), scope: "own", canWrite: false },
    });

    expect(await screen.findByText("Bảng tiền thủ thuật • 2026-09")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Xuất CSV cho Excel" })).toBeTruthy();
    expect(screen.queryByText("+ Ghi nhận lượt thủ thuật đã hoàn tất")).toBeNull();
    expect(screen.queryByRole("button", { name: /^Duyệt / })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Hủy / })).toBeNull();
    expect(screen.queryByRole("button", { name: "Chốt tháng đã kết thúc" })).toBeNull();
    expect(api.get).not.toHaveBeenCalledWith("/api/v1/services", expect.anything());
  });
});

describe("recording a performed procedure", () => {
  async function openForm(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByText("+ Ghi nhận lượt thủ thuật đã hoàn tất"));
  }

  async function choosePatient(user: ReturnType<typeof userEvent.setup>) {
    await screen.findByRole("option", { name: "Nguyễn Thu Hà · P001" });
    await user.selectOptions(screen.getByLabelText(/^Hồ sơ/), "patient-1");
  }

  it("is_closed_until_opened_and_opens_by_itself_with_form_open_in_the_address", async () => {
    nav.search = "form=open";
    renderFinance(<FinanceEntriesPage />, { shell: shell() });

    expect(await screen.findByLabelText(/^Ghi chú hoàn tất/)).toBeTruthy();
    expect(
      (
        screen
          .getByText("+ Ghi nhận lượt thủ thuật đã hoàn tất")
          .closest("details") as HTMLDetailsElement
      ).open,
    ).toBe(true);
  });

  it("starts_with_the_price_and_the_rate_of_the_service_and_follows_another_choice", async () => {
    const user = userEvent.setup();
    renderFinance(<FinanceEntriesPage />, { shell: shell() });
    await openForm(user);

    expect((screen.getByLabelText(/^Giá niêm yết/) as HTMLInputElement).value).toBe("300000");
    expect((screen.getAllByLabelText("Tỷ lệ tiền thủ thuật %")[0] as HTMLInputElement).value).toBe(
      "10",
    );
    await user.selectOptions(screen.getByLabelText("Thủ thuật"), "svc-2");

    expect((screen.getByLabelText(/^Giá niêm yết/) as HTMLInputElement).value).toBe("2500000");
    expect((screen.getAllByLabelText("Tỷ lệ tiền thủ thuật %")[0] as HTMLInputElement).value).toBe(
      "20",
    );
  });

  it("sends_the_shares_and_rates_as_basis_points_and_an_empty_invoice_as_null", async () => {
    const user = userEvent.setup();
    renderFinance(<FinanceEntriesPage />, { shell: shell() });
    await openForm(user);
    await choosePatient(user);

    await user.type(screen.getByLabelText(/^Ghi chú hoàn tất/), "Đã thực hiện");
    await user.click(screen.getByRole("button", { name: "Ghi nhận • Chờ duyệt" }));

    await waitFor(() => expect(reload).toHaveBeenCalled());
    expect(postedTo("/api/v1/finance/entries").body).toEqual({
      patient_id: "patient-1",
      service_id: "svc-1",
      entry_date: "2026-09-20",
      list_vnd: 300_000,
      discount_vnd: 0,
      invoice_id: null,
      note: "Đã thực hiện",
      people: [{ doctor_id: "doc-1", share_bp: 10_000, rate_bp: 1000 }],
    });
  });

  it("attaches_one_of_the_invoices_of_the_chosen_patient", async () => {
    const user = userEvent.setup();
    renderFinance(<FinanceEntriesPage />, { shell: shell() });
    await openForm(user);
    await choosePatient(user);

    await user.selectOptions(screen.getByLabelText("Gắn hóa đơn đã có"), "inv-1");
    await user.type(screen.getByLabelText(/^Ghi chú hoàn tất/), "Xong");
    await user.click(screen.getByRole("button", { name: "Ghi nhận • Chờ duyệt" }));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect((postedTo("/api/v1/finance/entries").body as { invoice_id: string }).invoice_id).toBe(
      "inv-1",
    );
  });

  it("tells_a_missing_note_in_place_and_sends_nothing", async () => {
    const user = userEvent.setup();
    renderFinance(<FinanceEntriesPage />, { shell: shell() });
    await openForm(user);
    await choosePatient(user);

    await user.click(screen.getByRole("button", { name: "Ghi nhận • Chờ duyệt" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Ghi chú xác nhận hoàn tất là bắt buộc",
    );
    expect(api.post).not.toHaveBeenCalled();
  });

  it("tells_that_the_shares_must_add_up_to_a_hundred_percent", async () => {
    const user = userEvent.setup();
    renderFinance(<FinanceEntriesPage />, { shell: shell() });
    await openForm(user);
    await choosePatient(user);

    await user.type(screen.getByLabelText(/^Ghi chú hoàn tất/), "Xong");
    const share = screen.getAllByLabelText("Tỷ trọng doanh số %")[0] as HTMLInputElement;
    await user.clear(share);
    await user.type(share, "50");
    await user.click(screen.getByRole("button", { name: "Ghi nhận • Chờ duyệt" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Tổng tỷ trọng doanh số phải là 100%",
    );
    expect(api.post).not.toHaveBeenCalled();
  });

  it("names_the_main_performer_and_an_optional_one_and_never_the_doctor_of_the_patient", async () => {
    const user = userEvent.setup();
    renderFinance(<FinanceEntriesPage />, { shell: shell() });
    await openForm(user);

    expect(screen.getByLabelText("Bác sĩ chính")).toBeTruthy();
    const second = screen.getByLabelText("Người phối hợp (tùy chọn)") as HTMLSelectElement;
    expect(second.value).toBe("");
    expect(within(second).getByRole("option", { name: "Không có" })).toBeTruthy();
    expect(screen.getByText("Ai thực hiện và được ghi nhận?")).toBeTruthy();
  });

  it("shows_the_sentence_of_the_backend_when_it_refuses_the_entry", async () => {
    const user = userEvent.setup();
    api.post.mockImplementation(() => refused(409, "invalid_state", "Kỳ đã chốt"));
    renderFinance(<FinanceEntriesPage />, { shell: shell() });
    await openForm(user);
    await choosePatient(user);
    await user.type(screen.getByLabelText(/^Ghi chú hoàn tất/), "Xong");

    await user.click(screen.getByRole("button", { name: "Ghi nhận • Chờ duyệt" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Kỳ đã chốt");
  });
});

describe("the export", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("says_the_old_sentence_when_the_file_cannot_be_made", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response("{}", { status: 500 }))),
    );
    renderFinance(<FinanceEntriesPage />, { shell: shell() });

    await user.click(await screen.findByRole("button", { name: "Xuất CSV cho Excel" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Không xuất được bảng");
  });

  it("asks_the_export_of_the_month_in_the_projection_of_the_page", async () => {
    const user = userEvent.setup();
    const fetchSpy = vi.fn(() => Promise.resolve(new Response("x", { status: 500 })));
    vi.stubGlobal("fetch", fetchSpy);
    renderFinance(<FinanceEntriesPage />, {
      shell: { ...shell(), month: "2026-08", scope: "own" },
    });

    await user.click(await screen.findByRole("button", { name: "Xuất CSV cho Excel" }));

    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
    expect((fetchSpy.mock.calls[0] as unknown as [string])[0]).toBe(
      "/api/v1/finance/export?month=2026-08&scope=own",
    );
  });
});
