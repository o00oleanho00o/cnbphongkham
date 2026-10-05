// @vitest-environment jsdom
// "Phiếu thu & thông báo" (`/finance/payments`) against a fake of the typed client: the form over the open invoices
// (amount defaults to the balance, what is sent: the idempotency key, the invoice, the amount, the method), the
// sentences "Số thu vượt công nợ" and "Chưa có phiếu thu.", the notifications that only the owner reads (and the line the
// accountant gets instead), "Đã đọc", and the quick orders without an invoice with "Lập hóa đơn".
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ACCOUNTANT,
  OWNER,
  invoice,
  ok,
  pageOf,
  receipt,
  refused,
  renderFinance,
} from "@/components/finance/test-support";
import type { Schemas } from "@/lib/api";

import FinancePaymentsPage from "./page";

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

const NOTES: Schemas["NotificationOut"][] = [
  {
    id: "note-1",
    payment_id: "pay-1",
    invoice_id: "inv-1",
    title: "Đã nhận thanh toán",
    body: "P012 · 1.200.000 đ · Chuyển khoản",
    amount_vnd: 1_200_000,
    created_at: "2026-09-12T10:30:00+07:00",
    read: false,
  },
  {
    id: "note-2",
    payment_id: "pay-2",
    invoice_id: "inv-2",
    title: "Đã nhận thanh toán",
    body: "P011 · 2.400.000 đ · Tiền mặt",
    amount_vnd: 2_400_000,
    created_at: "2026-09-11T15:05:00+07:00",
    read: true,
  },
];

const BILLABLE: Schemas["BillableOrderOut"][] = [
  {
    order_id: "order-1",
    patient_id: "patient-1",
    patient_code: "P001",
    patient_name: "Nguyễn Thu Hà",
    status: "approved",
    order_date: "2026-09-19",
    total_vnd: 720_500,
  },
];

type Data = {
  due?: Schemas["InvoiceOut"][];
  payments?: Schemas["PaymentOut"][];
  notes?: Schemas["NotificationOut"][];
  billable?: Schemas["BillableOrderOut"][];
};

function answers({
  due = [invoice()],
  payments = [receipt()],
  notes = NOTES,
  billable = [],
}: Data = {}) {
  api.get.mockReset().mockImplementation((path: string) => {
    if (path === "/api/v1/finance/invoices") return ok(pageOf(due));
    if (path === "/api/v1/finance/payments") return ok(pageOf(payments));
    if (path === "/api/v1/finance/notifications") return ok(notes);
    if (path === "/api/v1/finance/billable-orders") return ok(billable);
    return refused(404, "not_found", "?");
  });
}

function sentBody(path: string): Record<string, unknown> {
  const call = api.post.mock.calls.find((c) => c[0] === path);
  return (call?.[1] as { body: Record<string, unknown> }).body;
}

beforeEach(() => {
  answers();
  api.post.mockReset().mockImplementation(() => ok(receipt(), 201));
});

afterEach(() => cleanup());

describe("collecting from the finance screen", () => {
  it("defaults_the_amount_to_the_balance_of_the_first_open_invoice", async () => {
    renderFinance(<FinancePaymentsPage />);

    expect(await screen.findByText("Thu tiền khách hàng")).toBeTruthy();
    expect(screen.getByRole("option", { name: "P001 · 150.000 ₫ · HD-2609-0001" })).toBeTruthy();
    expect((screen.getByLabelText(/^Số thu/) as HTMLInputElement).value).toBe("150000");
    expect((screen.getByLabelText("Phương thức") as HTMLSelectElement).value).toBe("cash");
  });

  it("sends_the_invoice_the_amount_the_method_and_an_idempotency_key", async () => {
    const user = userEvent.setup();
    renderFinance(<FinancePaymentsPage />);
    await screen.findByText("Thu tiền khách hàng");

    const amount = screen.getByLabelText(/^Số thu/);
    await user.clear(amount);
    await user.type(amount, "100000");
    await user.selectOptions(screen.getByLabelText("Phương thức"), "transfer");
    await user.click(screen.getByRole("button", { name: "Xác nhận thu" }));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const body = sentBody("/api/v1/finance/payments");
    expect(body).toMatchObject({ invoice_id: "inv-1", amount_vnd: 100_000, method: "transfer" });
    expect(String(body.id).length).toBeGreaterThanOrEqual(3);
  });

  it("uses_a_new_key_for_the_next_receipt_after_a_success_and_the_same_key_after_a_failure", async () => {
    const user = userEvent.setup();
    api.post.mockImplementationOnce(() => refused(500, "internal", "Lỗi máy chủ"));
    renderFinance(<FinancePaymentsPage />);
    await screen.findByText("Thu tiền khách hàng");

    await user.click(screen.getByRole("button", { name: "Xác nhận thu" }));
    await screen.findByText("Lỗi máy chủ");
    await user.click(screen.getByRole("button", { name: "Xác nhận thu" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
    await screen.findByText("Đã ghi phiếu thu và cập nhật hóa đơn");
    await user.click(screen.getByRole("button", { name: "Xác nhận thu" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(3));

    const keys = api.post.mock.calls.map((c) => (c[1] as { body: { id: string } }).body.id);
    expect(keys[0]).toBe(keys[1]);
    expect(keys[2]).not.toBe(keys[1]);
  });

  it("shows_the_sentence_of_the_backend_for_an_amount_over_the_balance", async () => {
    const user = userEvent.setup();
    api.post.mockImplementation(() => refused(422, "validation_failed", "Số thu vượt công nợ"));
    renderFinance(<FinancePaymentsPage />);
    await screen.findByText("Thu tiền khách hàng");

    const amount = screen.getByLabelText(/^Số thu/);
    await user.clear(amount);
    await user.type(amount, "99999999");
    await user.click(screen.getByRole("button", { name: "Xác nhận thu" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Số thu vượt công nợ");
  });

  it("tells_an_amount_of_zero_before_anything_is_sent", async () => {
    const user = userEvent.setup();
    renderFinance(<FinancePaymentsPage />);
    await screen.findByText("Thu tiền khách hàng");

    const amount = screen.getByLabelText(/^Số thu/);
    await user.clear(amount);
    await user.type(amount, "0");
    await user.click(screen.getByRole("button", { name: "Xác nhận thu" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Số tiền phải lớn hơn 0 và không vượt số còn lại.",
    );
    expect(api.post).not.toHaveBeenCalled();
  });

  it("disables_the_button_when_no_invoice_is_open", async () => {
    answers({ due: [], payments: [] });
    renderFinance(<FinancePaymentsPage />);

    await screen.findByText("Thu tiền khách hàng");

    expect(
      (screen.getByRole("button", { name: "Xác nhận thu" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(screen.getByText("Chưa có phiếu thu.")).toBeTruthy();
  });

  it("lists_the_receipts_of_the_month_with_date_method_and_amount", async () => {
    renderFinance(<FinancePaymentsPage />);

    expect(await screen.findByText("Giao dịch trong kỳ")).toBeTruthy();
    expect(screen.getByText("2026-09-12 · Tiền mặt · HD-2609-0001")).toBeTruthy();
    expect(screen.getAllByText("150.000 ₫").length).toBeGreaterThan(0);
  });

  it("gives_a_role_that_may_not_collect_a_line_instead_of_the_form", async () => {
    renderFinance(<FinancePaymentsPage />, { shell: { canCollect: false } });

    expect(await screen.findByText("Vai trò của bạn không được ghi phiếu thu.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Xác nhận thu" })).toBeNull();
  });
});

describe("the notifications of the owner", () => {
  it("shows_title_body_and_time_with_a_button_only_on_an_unread_one", async () => {
    renderFinance(<FinancePaymentsPage />, { permissions: OWNER, role: "owner" });

    expect(await screen.findByText("Thông báo của chủ phòng khám")).toBeTruthy();
    expect(screen.getByText("P012 · 1.200.000 đ · Chuyển khoản")).toBeTruthy();
    expect(screen.getByText("2026-09-12 10:30")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: /^Đã đọc/ })).toHaveLength(1);
    expect(screen.getByText("Đã đọc", { selector: "span" })).toBeTruthy();
  });

  it("marks_a_notification_read", async () => {
    const user = userEvent.setup();
    renderFinance(<FinancePaymentsPage />, { permissions: OWNER, role: "owner" });

    await user.click(await screen.findByRole("button", { name: /^Đã đọc/ }));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const [path, options] = api.post.mock.calls[0] as [string, { params: unknown }];
    expect(path).toBe("/api/v1/finance/notifications/{notification_id}/read");
    expect(options.params).toEqual({ path: { notification_id: "note-1" } });
  });

  it("tells_the_accountant_that_the_inbox_of_the_owner_is_not_hers_and_never_asks_for_it", async () => {
    renderFinance(<FinancePaymentsPage />, { permissions: ACCOUNTANT });

    expect(await screen.findByText("Kế toán không đọc inbox của chủ.")).toBeTruthy();
    expect(api.get).not.toHaveBeenCalledWith("/api/v1/finance/notifications", expect.anything());
  });

  it("says_what_will_appear_when_there_is_no_notification_yet", async () => {
    answers({ notes: [] });
    renderFinance(<FinancePaymentsPage />, { permissions: OWNER, role: "owner" });

    expect(await screen.findByText("Thanh toán thành công sẽ xuất hiện tại đây.")).toBeTruthy();
  });
});

describe("quick orders without an invoice", () => {
  it("lists_them_and_raises_the_invoice_of_one", async () => {
    const user = userEvent.setup();
    answers({ billable: BILLABLE });
    renderFinance(<FinancePaymentsPage />);

    expect(await screen.findByText("Đơn sản phẩm chưa có hóa đơn")).toBeTruthy();
    expect(screen.getByText("P001 · 2026-09-19 · 720.500 ₫")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Lập hóa đơn cho đơn của Nguyễn Thu Hà" }));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(sentBody("/api/v1/finance/invoices/from-order")).toEqual({ order_id: "order-1" });
    expect(
      screen.getByRole("link", { name: "In tách đơn của Nguyễn Thu Hà" }).getAttribute("href"),
    ).toBe("/orders/order-1");
  });

  it("is_not_shown_when_every_order_has_its_invoice", async () => {
    renderFinance(<FinancePaymentsPage />);
    await screen.findByText("Thu tiền khách hàng");

    expect(screen.queryByText("Đơn sản phẩm chưa có hóa đơn")).toBeNull();
  });
});
