// The finance routes of the mock behave like backend `pema/clinic/actions/finance.py` and `finance_cash.py`: the
// projection comes from the session (a doctor never sees cash, invoices or the clinic rows), rounding is
// `(base * rate + 5000) // 10000` with the remainder of the revenue on the last performer, a closed month is
// frozen and immutable, a month closes only in the old order of blockers, a receipt is idempotent on its key and
// never exceeds the balance, and only the owner reads the notifications. The rules themselves are tested on the real
// backend (`backend/apps/api/tests/clinic/test_finance_*.py`).
import type { Server } from "node:http";
import type { AddressInfo } from "node:net";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { clinicToday, patientRef } from "./data/clinic";
import { previousMonthOf } from "./data/finance";
import { orders } from "./data/orders";
import { startMockServer } from "./server";

let server: Server;
let base: string;

beforeAll(async () => {
  server = await startMockServer(0);
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});

afterAll(() => {
  server.close();
});

async function signIn(email: string): Promise<string> {
  const res = await fetch(`${base}/api/v1/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email, password: "demo1234" }),
  });
  expect(res.status).toBe(200);
  return res.headers.get("set-cookie")?.split(";")[0] ?? "";
}

function call(cookie: string, method: string, path: string, body?: unknown): Promise<Response> {
  return fetch(`${base}${path}`, {
    method,
    headers: { "content-type": "application/json", ...(cookie ? { cookie } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

async function json<T>(res: Response): Promise<T> {
  return (await res.json()) as T;
}

type Err = { error: { code: string; message: string } };
type Row = {
  entry_id: string;
  doctor_id: string;
  status: string;
  base_vnd: number;
  rate_bp: number;
  revenue_vnd: number;
  fee_vnd: number;
  basis: string;
  note: string;
};
type Entries = {
  rows: Row[];
  can_write: boolean;
  scope: string;
  period: { status: string };
  doctors: { id: string; name: string }[];
};
type Overview = {
  scope: string;
  summary: {
    revenue_vnd: number;
    fee_vnd: number;
    pending_vnd: number;
    collected_vnd: number | null;
    debt_vnd: number | null;
  };
  team: { doctor_id: string; entry_count: number }[];
  pending_entries: number;
  period: { status: string };
};
type Entry = {
  id: string;
  status: string;
  invoice_id: string;
  net_vnd: number;
  people: { doctor_id: string; revenue_vnd: number; fee_vnd: number }[];
};
type Invoice = {
  id: string;
  source: string;
  order_id: string | null;
  amount_vnd: number;
  received_vnd: number;
  due_vnd: number;
};
type Payment = { id: string; replayed: boolean; amount_vnd: number };
type PeriodRow = {
  month: string;
  status: string;
  entry_count: number;
  closable: boolean;
  blocker: string | null;
};
type Service = { id: string; version: number; rate_bp: number | null; basis: string | null };

const BYTE_ORDER_MARK = String.fromCharCode(0xfeff);
const TODAY = clinicToday();
const THIS_MONTH = TODAY.slice(0, 7);
const PREV_MONTH = previousMonthOf(TODAY);
const PREV_DAY = `${PREV_MONTH}-20`;

async function service(cookie: string, at = 0): Promise<Service & { name: string }> {
  const list = await json<(Service & { name: string })[]>(
    await call(cookie, "GET", "/api/v1/services"),
  );
  const found = list[at];
  if (!found) throw new Error("no sample service");
  return found;
}

async function performers(cookie: string): Promise<{ id: string; name: string }[]> {
  const res = await call(cookie, "GET", "/api/v1/finance/performers");
  return res.ok ? json(res) : [];
}

type Draft = {
  list_vnd?: number;
  discount_vnd?: number;
  entry_date?: string;
  note?: string;
  invoice_id?: string | null;
  people?: { doctor_id: string; share_bp: number; rate_bp: number }[];
  patient?: number;
};

async function createEntry(cookie: string, over: Draft = {}): Promise<Response> {
  const [first] = await performers(cookie);
  const svc = await service(cookie);
  return call(cookie, "POST", "/api/v1/finance/entries", {
    patient_id: patientRef(over.patient ?? 1).id,
    service_id: svc.id,
    entry_date: over.entry_date ?? TODAY,
    list_vnd: over.list_vnd ?? 300_000,
    discount_vnd: over.discount_vnd ?? 0,
    invoice_id: over.invoice_id ?? null,
    note: over.note ?? "Đã thực hiện (mẫu)",
    people: over.people ?? [{ doctor_id: first?.id ?? "", share_bp: 10_000, rate_bp: 1000 }],
  });
}

describe("the projection comes from the session (mock)", () => {
  it("gives_a_doctor_only_own_rows_and_no_cash", async () => {
    const doctor = await signIn("doctor@pema.test");

    const overview = await json<Overview>(
      await call(doctor, "GET", `/api/v1/finance/overview?month=${THIS_MONTH}`),
    );
    const entries = await json<Entries>(
      await call(doctor, "GET", `/api/v1/finance/entries?month=${THIS_MONTH}`),
    );

    expect(overview.scope).toBe("own");
    expect(overview.summary.collected_vnd).toBeNull();
    expect(overview.summary.debt_vnd).toBeNull();
    expect(overview.team).toHaveLength(1);
    expect(entries.can_write).toBe(false);
    expect(new Set(entries.rows.map((r) => r.doctor_id)).size).toBeLessThanOrEqual(1);
    expect(entries.doctors).toHaveLength(1);
  });

  it("keeps_a_doctor_out_of_the_clinic_scope_the_invoices_the_receipts_and_the_periods", async () => {
    const doctor = await signIn("doctor@pema.test");

    for (const path of [
      `/api/v1/finance/overview?month=${THIS_MONTH}&scope=clinic`,
      "/api/v1/finance/invoices",
      `/api/v1/finance/payments?month=${THIS_MONTH}`,
      "/api/v1/finance/periods",
      "/api/v1/finance/notifications",
      "/api/v1/finance/performers",
    ]) {
      expect((await call(doctor, "GET", path)).status, path).toBe(403);
    }
  });

  it("gives_the_manager_the_clinic_numbers_and_the_owner_alone_the_notifications", async () => {
    const manager = await signIn("manager@pema.test");

    const overview = await json<Overview>(
      await call(manager, "GET", `/api/v1/finance/overview?month=${THIS_MONTH}`),
    );

    expect(overview.scope).toBe("clinic");
    expect(overview.summary.collected_vnd).toBeGreaterThan(0);
    expect(overview.summary.debt_vnd).toBeGreaterThan(0);
    expect((await call(manager, "GET", "/api/v1/finance/notifications")).status).toBe(403);
    expect((await call(manager, "GET", "/api/v1/finance/entries?month=2026-13")).status).toBe(422);
  });

  it("lets_the_owner_flip_between_the_clinic_and_the_personal_projection", async () => {
    const owner = await signIn("owner@pema.test");

    const clinic = await json<Overview>(
      await call(owner, "GET", `/api/v1/finance/overview?month=${THIS_MONTH}`),
    );
    const own = await json<Overview>(
      await call(owner, "GET", `/api/v1/finance/overview?month=${THIS_MONTH}&scope=own`),
    );

    expect(clinic.scope).toBe("clinic");
    expect(own.scope).toBe("own");
    expect(own.summary.collected_vnd).toBeNull();
    expect(own.summary.revenue_vnd).toBeLessThanOrEqual(clinic.summary.revenue_vnd);
    expect((await call(owner, "GET", "/api/v1/finance/notifications")).status).toBe(200);
  });

  it("lets_reception_collect_but_not_read_the_numbers", async () => {
    const reception = await signIn("reception@pema.test");

    expect((await call(reception, "GET", "/api/v1/finance/invoices?due_only=true")).status).toBe(
      200,
    );
    expect((await call(reception, "GET", "/api/v1/finance/billable-orders")).status).toBe(200);
    expect(
      (await call(reception, "GET", `/api/v1/finance/overview?month=${THIS_MONTH}`)).status,
    ).toBe(403);
    expect(
      (await call(reception, "GET", `/api/v1/finance/payments?month=${THIS_MONTH}`)).status,
    ).toBe(403);
    expect(
      (await call(await signIn("cs@pema.test"), "GET", "/api/v1/finance/invoices")).status,
    ).toBe(403);
  });
});

describe("recording an entry (mock)", () => {
  it("splits_the_revenue_with_the_remainder_on_the_last_performer_and_rounds_the_fee_half_up", async () => {
    const manager = await signIn("manager@pema.test");
    const [a, b] = await performers(manager);

    const res = await createEntry(manager, {
      list_vnd: 333_333,
      discount_vnd: 3,
      people: [
        { doctor_id: a?.id ?? "", share_bp: 3333, rate_bp: 1000 },
        { doctor_id: b?.id ?? "", share_bp: 6667, rate_bp: 1500 },
      ],
    });
    const entry = await json<Entry>(res);

    expect(res.status).toBe(201);
    expect(entry.status).toBe("pending");
    expect(entry.net_vnd).toBe(333_330);
    expect(entry.people[0]?.revenue_vnd).toBe(Math.floor((333_330 * 3333) / 10_000));
    expect(entry.people.reduce((sum, p) => sum + p.revenue_vnd, 0)).toBe(333_330);
    expect(entry.people[0]?.fee_vnd).toBe(Math.floor((333_330 * 1000 + 5000) / 10_000));
    expect(entry.people[1]?.fee_vnd).toBe(Math.floor((333_330 * 1500 + 5000) / 10_000));
  });

  it("refuses_a_bad_form_with_the_sentences_of_the_old_web", async () => {
    const manager = await signIn("manager@pema.test");
    const [a, b] = await performers(manager);
    const person = (id: string | undefined, share: number, rate: number) => ({
      doctor_id: id ?? "",
      share_bp: share,
      rate_bp: rate,
    });
    const refused = async (over: Draft, message: string) => {
      const res = await createEntry(manager, over);
      expect(res.status, message).toBe(422);
      expect((await json<Err>(res)).error.message).toBe(message);
    };

    await refused({ people: [person(a?.id, 5000, 1000)] }, "Tổng tỷ trọng doanh số phải là 100%");
    await refused(
      { people: [person(a?.id, 5000, 6000), person(b?.id, 5000, 6000)] },
      "Tổng tỷ lệ tiền thủ thuật không vượt 100%",
    );
    await refused(
      { people: [person(a?.id, 5000, 1000), person(a?.id, 5000, 1000)] },
      "Trùng người thực hiện",
    );
    await refused({ note: "   " }, "Ghi chú xác nhận hoàn tất là bắt buộc");
    await refused({ entry_date: "2999-01-01" }, "Ngày thực hiện không hợp lệ");
    await refused({ discount_vnd: 400_000 }, "Số tiền/tỷ lệ không hợp lệ");
    await refused(
      { people: [person("00000000-0000-4000-8001-0000000000ff", 10_000, 1000)] },
      "Người thực hiện không hợp lệ",
    );
  });

  it("is_for_the_manager_and_the_owner_only", async () => {
    expect((await createEntry(await signIn("doctor@pema.test"))).status).toBe(403);
    expect((await createEntry(await signIn("reception@pema.test"))).status).toBe(403);
  });

  it("attaches_to_an_invoice_of_the_same_patient_and_never_over_allocates_it", async () => {
    const manager = await signIn("manager@pema.test");
    const invoices = await json<{ items: (Invoice & { patient_code: string })[] }>(
      await call(manager, "GET", "/api/v1/finance/invoices?limit=200"),
    );
    const target = invoices.items.find(
      (i) => i.patient_code === "P001" && i.amount_vnd === 300_000 && i.source === "finance",
    );
    expect(target).toBeDefined();

    const foreign = await createEntry(manager, { invoice_id: target?.id, patient: 9 });
    const over = await createEntry(manager, { invoice_id: target?.id, patient: 1 });

    expect(foreign.status).toBe(422);
    expect((await json<Err>(foreign)).error.message).toBe("Hóa đơn không thuộc bệnh nhân này");
    expect(over.status).toBe(422);
    expect((await json<Err>(over)).error.message).toBe(
      "Giá trị lượt vượt phần hóa đơn chưa phân bổ",
    );
  });
});

describe("approving and voiding (mock)", () => {
  it("approves_a_pending_entry_and_counts_its_fee_as_approved", async () => {
    const manager = await signIn("manager@pema.test");
    const before = await json<Overview>(
      await call(manager, "GET", `/api/v1/finance/overview?month=${THIS_MONTH}`),
    );
    const entry = await json<Entry>(await createEntry(manager, { list_vnd: 1_000_000 }));
    const pending = await json<Overview>(
      await call(manager, "GET", `/api/v1/finance/overview?month=${THIS_MONTH}`),
    );

    const res = await call(manager, "POST", `/api/v1/finance/entries/${entry.id}/approve`);
    const after = await json<Overview>(
      await call(manager, "GET", `/api/v1/finance/overview?month=${THIS_MONTH}`),
    );

    expect(res.status).toBe(200);
    expect((await json<Entry>(res)).status).toBe("approved");
    expect(pending.summary.pending_vnd - before.summary.pending_vnd).toBe(100_000);
    expect(after.summary.fee_vnd - before.summary.fee_vnd).toBe(100_000);
    expect(after.summary.pending_vnd).toBe(before.summary.pending_vnd);
  });

  it("needs_a_reason_to_void_and_zeroes_the_invoice_the_entry_raised", async () => {
    const manager = await signIn("manager@pema.test");
    const entry = await json<Entry>(await createEntry(manager));

    const noReason = await call(manager, "POST", `/api/v1/finance/entries/${entry.id}/void`, {
      reason: "  ",
    });
    const voided = await call(manager, "POST", `/api/v1/finance/entries/${entry.id}/void`, {
      reason: "Nhập nhầm hồ sơ (mẫu)",
    });
    const invoice = (
      await json<{ items: Invoice[] }>(
        await call(manager, "GET", "/api/v1/finance/invoices?limit=200"),
      )
    ).items.find((i) => i.id === entry.invoice_id);
    const again = await call(manager, "POST", `/api/v1/finance/entries/${entry.id}/approve`);

    expect(noReason.status).toBe(422);
    expect((await json<Err>(noReason)).error.message).toBe("Cần lý do hủy");
    expect((await json<Entry>(voided)).status).toBe("void");
    expect(invoice?.amount_vnd).toBe(0);
    expect(again.status).toBe(409);
    expect((await json<Err>(again)).error.message).toBe("Lượt đã hủy");
  });

  it("refuses_to_void_an_entry_whose_invoice_has_money_received", async () => {
    const manager = await signIn("manager@pema.test");
    const entry = await json<Entry>(await createEntry(manager));
    expect(
      (
        await call(manager, "POST", "/api/v1/finance/payments", {
          id: `void-paid-${entry.id}`,
          invoice_id: entry.invoice_id,
          amount_vnd: 1000,
          method: "cash",
        })
      ).status,
    ).toBe(201);

    const res = await call(manager, "POST", `/api/v1/finance/entries/${entry.id}/void`, {
      reason: "Hủy (mẫu)",
    });

    expect(res.status).toBe(409);
    expect((await json<Err>(res)).error.message).toBe(
      "Lượt đã thu tiền; cần quy trình hoàn/điều chỉnh riêng",
    );
  });
});

describe("closing a month (mock)", () => {
  it("lists_twelve_months_and_explains_why_the_current_one_cannot_close", async () => {
    const manager = await signIn("manager@pema.test");

    const list = await json<{ items: PeriodRow[] }>(
      await call(manager, "GET", "/api/v1/finance/periods"),
    );
    const current = list.items.find((p) => p.month === THIS_MONTH);

    expect(list.items).toHaveLength(12);
    expect(list.items[0]?.month).toBe(THIS_MONTH);
    expect(current?.closable).toBe(false);
    expect(current?.blocker).toBe("Chỉ chốt tháng đã kết thúc");
    const empty = list.items.find((p) => p.entry_count === 0);
    expect(empty?.blocker).toBe("Kỳ không có dữ liệu");
    expect(list.items.slice(2, 4).map((p) => p.status)).toEqual(["closed", "paid"]);
    const closeNow = await call(manager, "POST", `/api/v1/finance/periods/${THIS_MONTH}/close`);
    expect(closeNow.status).toBe(409);
  });

  it("freezes_a_closed_month_and_keeps_the_blockers_in_the_old_order", async () => {
    const manager = await signIn("manager@pema.test");
    const svc = await service(manager);
    const blockerOf = async () =>
      (
        await json<{ items: PeriodRow[] }>(await call(manager, "GET", "/api/v1/finance/periods"))
      ).items.find((p) => p.month === PREV_MONTH);
    expect((await blockerOf())?.closable).toBe(true);

    // an entry on the "Theo thực thu" basis whose invoice is not paid in full, and it is pending
    await call(manager, "PATCH", `/api/v1/services/${svc.id}`, {
      version: svc.version,
      basis: "collected",
    });
    const entry = await json<Entry>(await createEntry(manager, { entry_date: PREV_DAY }));
    expect((await blockerOf())?.blocker).toBe(
      "Còn lượt tính theo thực thu chưa thu đủ; chưa thể chốt để tránh mất tiền kỳ sau",
    );
    const refusedClose = await call(manager, "POST", `/api/v1/finance/periods/${PREV_MONTH}/close`);
    expect(refusedClose.status).toBe(409);

    // paid in full: the pending entry is what is left, then approving makes the month closable
    await call(manager, "POST", "/api/v1/finance/payments", {
      id: `close-flow-${entry.id}`,
      invoice_id: entry.invoice_id,
      amount_vnd: entry.net_vnd,
      method: "transfer",
    });
    expect((await blockerOf())?.blocker).toBe("Còn lượt chờ duyệt");
    await call(manager, "POST", `/api/v1/finance/entries/${entry.id}/approve`);
    expect((await blockerOf())?.closable).toBe(true);

    const closed = await call(manager, "POST", `/api/v1/finance/periods/${PREV_MONTH}/close`);
    const frozen = await json<Entries>(
      await call(manager, "GET", `/api/v1/finance/entries?month=${PREV_MONTH}`),
    );
    expect(closed.status).toBe(200);
    expect(frozen.period.status).toBe("closed");

    // immutable: no new entry, no approve, no void, no second close, rows keep their snapshot
    const created = await createEntry(manager, { entry_date: PREV_DAY });
    const approve = await call(manager, "POST", `/api/v1/finance/entries/${entry.id}/approve`);
    const voided = await call(manager, "POST", `/api/v1/finance/entries/${entry.id}/void`, {
      reason: "x",
    });
    const twice = await call(manager, "POST", `/api/v1/finance/periods/${PREV_MONTH}/close`);
    expect((await json<Err>(created)).error.message).toBe("Kỳ đã chốt");
    expect((await json<Err>(approve)).error.message).toBe("Kỳ đã chốt, không được sửa");
    expect(voided.status).toBe(409);
    expect((await json<Err>(twice)).error.message).toBe("Kỳ đã chốt");
    await call(manager, "PATCH", `/api/v1/services/${svc.id}`, {
      version: svc.version + 1,
      rate_bp: 5000,
    });
    const still = await json<Entries>(
      await call(manager, "GET", `/api/v1/finance/entries?month=${PREV_MONTH}`),
    );
    expect(still.rows).toEqual(frozen.rows);
    expect(still.can_write).toBe(true);
  });

  it("confirms_the_payout_only_for_a_closed_month_with_a_voucher_and_only_once", async () => {
    const manager = await signIn("manager@pema.test");

    const beforeClose = await call(manager, "POST", "/api/v1/finance/periods/2020-01/pay", {
      reference: "PC-1",
    });
    const noVoucher = await call(manager, "POST", `/api/v1/finance/periods/${PREV_MONTH}/pay`, {
      reference: "  ",
    });
    const paid = await call(manager, "POST", `/api/v1/finance/periods/${PREV_MONTH}/pay`, {
      reference: "PC-0001 (mẫu)",
    });
    const twice = await call(manager, "POST", `/api/v1/finance/periods/${PREV_MONTH}/pay`, {
      reference: "PC-0002",
    });

    expect((await json<Err>(beforeClose)).error.message).toBe("Cần chốt kỳ trước khi xác nhận chi");
    expect((await json<Err>(noVoucher)).error.message).toBe("Cần mã chứng từ chi");
    expect(paid.status).toBe(200);
    expect(await json<{ status: string; reference: string }>(paid)).toMatchObject({
      status: "paid",
      reference: "PC-0001 (mẫu)",
    });
    expect((await json<Err>(twice)).error.message).toBe("Kỳ đã xác nhận chi");
  });
});

describe("receipts (mock)", () => {
  async function openInvoice(cookie: string): Promise<Invoice> {
    const list = await json<{ items: Invoice[] }>(
      await call(cookie, "GET", "/api/v1/finance/invoices?due_only=true&limit=200"),
    );
    const found = list.items.find((i) => i.due_vnd >= 1000);
    if (!found) throw new Error("no open invoice");
    return found;
  }

  it("takes_a_receipt_once_per_key_and_replays_the_first_one_on_a_retry", async () => {
    const reception = await signIn("reception@pema.test");
    const invoice = await openInvoice(reception);
    const body = { id: "retry-key-1", invoice_id: invoice.id, amount_vnd: 500, method: "cash" };

    const first = await call(reception, "POST", "/api/v1/finance/payments", body);
    const retry = await call(reception, "POST", "/api/v1/finance/payments", body);
    const other = await call(reception, "POST", "/api/v1/finance/payments", {
      ...body,
      amount_vnd: 600,
    });
    const after = (
      await json<{ items: Invoice[] }>(
        await call(reception, "GET", "/api/v1/finance/invoices?limit=200"),
      )
    ).items.find((i) => i.id === invoice.id);

    expect(first.status).toBe(201);
    expect(retry.status).toBe(200);
    expect((await json<Payment>(retry)).replayed).toBe(true);
    expect(other.status).toBe(409);
    const refused = await json<Err>(other);
    expect(refused.error.code).toBe("duplicate_request");
    expect(refused.error.message).toBe("Mã giao dịch đã dùng cho nội dung khác");
    expect(after?.received_vnd).toBe(invoice.received_vnd + 500);
  });

  it("refuses_more_than_the_open_balance", async () => {
    const reception = await signIn("reception@pema.test");
    const invoice = await openInvoice(reception);

    const res = await call(reception, "POST", "/api/v1/finance/payments", {
      id: "over-key-1",
      invoice_id: invoice.id,
      amount_vnd: invoice.due_vnd + 1,
      method: "transfer",
    });

    expect(res.status).toBe(422);
    expect((await json<Err>(res)).error.message).toBe("Số thu vượt công nợ");
  });

  it("tells_the_owner_about_each_receipt_and_lets_them_mark_it_read", async () => {
    const owner = await signIn("owner@pema.test");
    const reception = await signIn("reception@pema.test");
    const invoice = await openInvoice(reception);
    await call(reception, "POST", "/api/v1/finance/payments", {
      id: "note-key-1",
      invoice_id: invoice.id,
      amount_vnd: 700,
      method: "transfer",
    });

    const list = await json<{ id: string; read: boolean; body: string; amount_vnd: number }[]>(
      await call(owner, "GET", "/api/v1/finance/notifications"),
    );
    const marked = await call(owner, "POST", `/api/v1/finance/notifications/${list[0]?.id}/read`);

    expect(list[0]).toMatchObject({ read: false, amount_vnd: 700 });
    expect(list[0]?.body).toContain("Chuyển khoản");
    expect((await json<{ read: boolean }>(marked)).read).toBe(true);
  });

  it("lists_the_receipts_of_a_month_newest_first_for_whoever_reads_finance", async () => {
    const manager = await signIn("manager@pema.test");

    const page = await json<{ items: { paid_on: string }[]; total: number }>(
      await call(manager, "GET", `/api/v1/finance/payments?month=${THIS_MONTH}`),
    );

    expect(page.total).toBeGreaterThan(0);
    expect(page.items.map((p) => p.paid_on)).toEqual(
      page.items
        .map((p) => p.paid_on)
        .toSorted()
        .toReversed(),
    );
  });
});

describe("invoices of quick orders (mock)", () => {
  it("raises_the_invoice_of_an_order_once_and_a_receipt_locks_the_order", async () => {
    const reception = await signIn("reception@pema.test");
    const billable = await json<{ order_id: string; total_vnd: number }[]>(
      await call(reception, "GET", "/api/v1/finance/billable-orders"),
    );
    const target = billable.find((b) => b.order_id === orders[0]?.id);
    expect(target).toBeDefined();

    const first = await json<Invoice>(
      await call(reception, "POST", "/api/v1/finance/invoices/from-order", {
        order_id: target?.order_id,
      }),
    );
    const again = await json<Invoice>(
      await call(reception, "POST", "/api/v1/finance/invoices/from-order", {
        order_id: target?.order_id,
      }),
    );
    const stillBillable = await json<{ order_id: string }[]>(
      await call(reception, "GET", "/api/v1/finance/billable-orders"),
    );
    await call(reception, "POST", "/api/v1/finance/payments", {
      id: `order-key-${first.id}`,
      invoice_id: first.id,
      amount_vnd: first.amount_vnd,
      method: "cash",
    });
    const order = await json<{ invoice_id: string; paid: boolean; editable: boolean }>(
      await call(reception, "GET", `/api/v1/orders/${target?.order_id}`),
    );

    expect(first).toMatchObject({ source: "order", order_id: target?.order_id });
    expect(first.amount_vnd).toBe(target?.total_vnd);
    expect(again.id).toBe(first.id);
    expect(stillBillable.some((b) => b.order_id === target?.order_id)).toBe(false);
    expect(order).toMatchObject({ invoice_id: first.id, paid: true, editable: false });
  });
});

describe("export (mock)", () => {
  it("serves_a_csv_with_a_byte_order_mark_the_old_header_and_a_guard_against_formulas", async () => {
    const manager = await signIn("manager@pema.test");
    const svc = await service(manager, 1);
    await call(manager, "PATCH", `/api/v1/services/${svc.id}`, {
      version: svc.version,
      name: "=SUM(A1)",
    });
    const [first] = await performers(manager);
    await call(manager, "POST", "/api/v1/finance/entries", {
      patient_id: patientRef(2).id,
      service_id: svc.id,
      entry_date: TODAY,
      list_vnd: 500_000,
      discount_vnd: 0,
      note: "Công thức (mẫu)",
      people: [{ doctor_id: first?.id ?? "", share_bp: 10_000, rate_bp: 1500 }],
    });

    const res = await call(manager, "GET", `/api/v1/finance/export?month=${THIS_MONTH}`);
    const bytes = new Uint8Array(await res.arrayBuffer());
    const text = new TextDecoder("utf-8", { ignoreBOM: true }).decode(bytes);

    expect(res.headers.get("content-type")).toContain("text/csv");
    expect(res.headers.get("content-disposition")).toContain(
      `Pema-tien-thu-thuat-${THIS_MONTH}.csv`,
    );
    expect(text.startsWith(BYTE_ORDER_MARK)).toBe(true);
    expect(text.split("\r\n")[0]).toBe(
      `${BYTE_ORDER_MARK}Ngay,Ho so,Thu thuat,Bac si,Doanh so,Co so,Ty le %,Tien thu thuat,Trang thai`,
    );
    expect(text).toContain("'=SUM(A1)");
  });

  it("exports_only_the_rows_of_a_doctor_to_that_doctor", async () => {
    const doctor = await signIn("doctor@pema.test");
    const mine = await json<Entries>(
      await call(doctor, "GET", `/api/v1/finance/entries?month=${THIS_MONTH}`),
    );

    const text = await (
      await call(doctor, "GET", `/api/v1/finance/export?month=${THIS_MONTH}`)
    ).text();

    expect(text.trim().split("\r\n")).toHaveLength(mine.rows.length + 1);
  });
});
