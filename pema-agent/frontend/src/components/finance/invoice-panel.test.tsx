// @vitest-environment jsdom
// "Hóa đơn & thanh toán" of the cashier against a fake of the typed client: the invoices with the three filters, 12 per
// page, "Thu tiền" only for whoever may collect and only on an invoice with a balance, the dialog that takes the
// receipt (balance in the notice, amount to start from, the sentence for zero, the backend's "Số thu vượt công nợ"),
// the quick orders without an invoice ("Lập hóa đơn", "In tách đơn"), and what a role with no finance rights is told.
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Schemas } from "@/lib/api";
import type { Permission } from "@/lib/session/session-context";

import { InvoicePanel } from "./invoice-panel";
import { ok, pageOf, receipt, refused, renderFinance, invoice } from "./test-support";

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

const OPEN = invoice();
const PAID = invoice({
  id: "inv-2",
  number: "HD-2609-0002",
  patient_name: "Trần Minh Anh",
  amount_vnd: 1_200_000,
  received_vnd: 1_200_000,
  due_vnd: 0,
});
const ORDER_INVOICE = invoice({
  id: "inv-3",
  number: "HD-2609-0003",
  patient_name: "Lê Văn Bình",
  source: "order",
  order_id: "order-7",
  amount_vnd: 720_500,
  received_vnd: 0,
  due_vnd: 720_500,
});

const BILLABLE: Schemas["BillableOrderOut"][] = [
  {
    order_id: "order-9",
    patient_id: "patient-1",
    patient_code: "P004",
    patient_name: "Phạm Gia Hân",
    status: "draft",
    order_date: "2026-09-19",
    total_vnd: 731_500,
  },
];

const RECEPTION: Permission[] = ["finance.collect", "order.read", "order.write"];

function answers(
  invoices: Schemas["InvoiceOut"][] = [OPEN, PAID, ORDER_INVOICE],
  billable = BILLABLE,
) {
  api.get.mockReset().mockImplementation((path: string) => {
    if (path === "/api/v1/finance/invoices") return ok(pageOf(invoices));
    if (path === "/api/v1/finance/billable-orders") return ok(billable);
    return refused(404, "not_found", "?");
  });
}

const changed = vi.fn();

function renderPanel(permissions: Permission[] = RECEPTION) {
  return renderFinance(<InvoicePanel onChanged={changed} />, { permissions, role: "reception" });
}

beforeEach(() => {
  answers();
  changed.mockReset();
  api.post.mockReset().mockImplementation(() => ok(receipt(), 201));
});

afterEach(() => cleanup());

describe("the invoices", () => {
  it("shows_the_columns_of_the_old_cashier_with_the_money_of_each_invoice", async () => {
    renderPanel();

    expect(await screen.findByText("Hóa đơn & thanh toán")).toBeTruthy();
    for (const header of [
      "Hóa đơn / bệnh nhân",
      "Dịch vụ / đơn nhanh",
      "Tổng tiền",
      "Đã thu",
      "Còn lại",
    ]) {
      expect(screen.getByRole("columnheader", { name: header })).toBeTruthy();
    }
    expect(screen.getByText("HD-2609-0001 · 2026-09-06")).toBeTruthy();
    expect(screen.getAllByText("Buổi chăm sóc / điều trị").length).toBeGreaterThan(0);
    expect(screen.getByText("Đơn sản phẩm")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "In tách đơn của Lê Văn Bình" }).getAttribute("href"),
    ).toBe("/orders/order-7");
  });

  it("offers_thu_tien_on_an_invoice_with_a_balance_and_a_badge_on_a_paid_one", async () => {
    renderPanel();
    await screen.findByText("Hóa đơn & thanh toán");

    expect(screen.getAllByRole("button", { name: /^Thu tiền / })).toHaveLength(2);
    expect(screen.getByText("Đã thanh toán", { selector: "span" })).toBeTruthy();
  });

  it("shows_the_totals_of_the_invoices_the_amount_received_and_the_amount_still_due", async () => {
    renderPanel();

    expect(await screen.findByText("Tổng hóa đơn")).toBeTruthy();
    expect(screen.getByText("1.350.000 ₫")).toBeTruthy();
    expect(screen.getByText("870.500 ₫")).toBeTruthy();
  });

  it("filters_to_the_invoices_that_are_still_due_or_already_paid", async () => {
    const user = userEvent.setup();
    renderPanel();
    await screen.findByText("Hóa đơn & thanh toán");

    await user.click(screen.getByRole("button", { name: "Còn phải thu" }));
    expect(screen.queryByText("Trần Minh Anh")).toBeNull();
    expect(screen.getByText("Nguyễn Thu Hà")).toBeTruthy();
    expect(screen.getByText("2 hóa đơn · Trang 1/1")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Đã thanh toán" }));
    expect(screen.getByText("Trần Minh Anh")).toBeTruthy();
    expect(screen.queryByText("Nguyễn Thu Hà")).toBeNull();
  });

  it("says_there_is_no_invoice_when_the_filter_keeps_none", async () => {
    const user = userEvent.setup();
    answers([PAID]);
    renderPanel();
    await screen.findByText("Hóa đơn & thanh toán");

    await user.click(screen.getByRole("button", { name: "Còn phải thu" }));

    expect(screen.getByText("Không có hóa đơn.")).toBeTruthy();
    expect(screen.getByText("0 hóa đơn · Trang 1/1")).toBeTruthy();
  });

  it("pages_twelve_at_a_time", async () => {
    const user = userEvent.setup();
    answers(
      Array.from({ length: 13 }, (_, i) =>
        invoice({ id: `inv-${i}`, number: `HD-${i}`, patient_name: `Khách ${i}` }),
      ),
      [],
    );
    renderPanel();

    expect(await screen.findByText("13 hóa đơn · Trang 1/2")).toBeTruthy();
    expect(screen.queryByText("Khách 12")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Sau →" }));

    expect(screen.getByText("13 hóa đơn · Trang 2/2")).toBeTruthy();
    expect(screen.getByText("Khách 12")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Sau →" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });
});

describe("taking a receipt", () => {
  async function openDialog(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByRole("button", { name: "Thu tiền Nguyễn Thu Hà" }));
    return screen.findByRole("dialog");
  }

  it("opens_with_the_balance_in_the_notice_and_the_balance_as_the_amount", async () => {
    const user = userEvent.setup();
    renderPanel();
    const dialog = await openDialog(user);

    expect(within(dialog).getByText("Thu tiền · Nguyễn Thu Hà")).toBeTruthy();
    expect(within(dialog).getByText("HD-2609-0001 · Còn lại 150.000 ₫")).toBeTruthy();
    expect((within(dialog).getByLabelText(/^Số tiền \(VND\)/) as HTMLInputElement).value).toBe(
      "150000",
    );
    expect(within(dialog).getByRole("option", { name: "Tiền mặt" })).toBeTruthy();
    expect(within(dialog).getByRole("option", { name: "Chuyển khoản" })).toBeTruthy();
  });

  it("sends_the_receipt_closes_and_tells_the_page_something_changed", async () => {
    const user = userEvent.setup();
    renderPanel();
    const dialog = await openDialog(user);

    await user.selectOptions(within(dialog).getByLabelText("Phương thức"), "transfer");
    await user.click(within(dialog).getByRole("button", { name: "Xác nhận thu tiền" }));

    await waitFor(() => expect(changed).toHaveBeenCalled());
    const [path, options] = api.post.mock.calls[0] as [string, { body: Record<string, unknown> }];
    expect(path).toBe("/api/v1/finance/payments");
    expect(options.body).toMatchObject({
      invoice_id: "inv-1",
      amount_vnd: 150_000,
      method: "transfer",
    });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(await screen.findByText("Đã ghi phiếu thu và cập nhật hóa đơn")).toBeTruthy();
  });

  it("tells_an_amount_of_zero_in_the_dialog_and_sends_nothing", async () => {
    const user = userEvent.setup();
    renderPanel();
    const dialog = await openDialog(user);

    const amount = within(dialog).getByLabelText(/^Số tiền \(VND\)/);
    await user.clear(amount);
    await user.type(amount, "0");
    await user.click(within(dialog).getByRole("button", { name: "Xác nhận thu tiền" }));

    expect((await within(dialog).findByRole("alert")).textContent).toContain(
      "Số tiền phải lớn hơn 0 và không vượt số còn lại.",
    );
    expect(api.post).not.toHaveBeenCalled();
  });

  it("keeps_the_dialog_and_shows_the_sentence_of_the_backend_for_an_amount_over_the_balance", async () => {
    const user = userEvent.setup();
    api.post.mockImplementation(() => refused(422, "validation_failed", "Số thu vượt công nợ"));
    renderPanel();
    const dialog = await openDialog(user);

    const amount = within(dialog).getByLabelText(/^Số tiền \(VND\)/);
    await user.clear(amount);
    await user.type(amount, "99999999");
    await user.click(within(dialog).getByRole("button", { name: "Xác nhận thu tiền" }));

    expect((await within(dialog).findByRole("alert")).textContent).toContain("Số thu vượt công nợ");
    expect(changed).not.toHaveBeenCalled();
  });
});

describe("quick orders without an invoice", () => {
  it("lists_them_and_raises_the_invoice_then_tells_the_page", async () => {
    const user = userEvent.setup();
    renderPanel();

    expect(await screen.findByText("Đơn sản phẩm chưa có hóa đơn")).toBeTruthy();
    expect(screen.getByText("P004 · 2026-09-19 · 731.500 ₫")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Lập hóa đơn cho đơn của Phạm Gia Hân" }));

    await waitFor(() => expect(changed).toHaveBeenCalled());
    expect(api.post.mock.calls[0]).toEqual([
      "/api/v1/finance/invoices/from-order",
      { body: { order_id: "order-9" } },
    ]);
  });
});

describe("who sees what", () => {
  it("lets_a_reader_of_finance_list_the_invoices_without_any_button_that_collects", async () => {
    renderPanel(["finance.read", "order.read"]);

    expect(await screen.findByText("Nguyễn Thu Hà")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Thu tiền / })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Lập hóa đơn/ })).toBeNull();
    expect(screen.getByText("Đã thanh toán", { selector: "span" })).toBeTruthy();
  });

  it("tells_a_role_with_no_finance_right_who_handles_invoices_and_asks_for_nothing", async () => {
    renderPanel(["order.read"]);

    expect(
      await screen.findByText(/Hóa đơn và thu tiền do lễ tân, kế toán hoặc chủ phòng khám/),
    ).toBeTruthy();
    expect(api.get).not.toHaveBeenCalled();
  });

  it("offers_a_retry_when_the_invoices_cannot_be_loaded", async () => {
    const user = userEvent.setup();
    api.get.mockImplementation(() => refused(500, "internal", "Lỗi máy chủ"));
    renderPanel();

    expect(await screen.findByText("Lỗi máy chủ")).toBeTruthy();
    answers();
    await user.click(screen.getByRole("button", { name: "Thử lại" }));

    expect(await screen.findByText("Nguyễn Thu Hà")).toBeTruthy();
  });
});
