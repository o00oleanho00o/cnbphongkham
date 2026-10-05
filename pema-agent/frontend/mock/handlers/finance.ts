// Mock of Finance PB02 (`/finance/*`). The rules are the backend's (`pema.clinic.finance.domain`,
// `pema.clinic.actions.finance|finance_cash`, itself a port of `prototype/finance_server.py`); the mock keeps every
// one a screen shows: the projection comes from the session (clinic for `finance.read`, personal rows for
// `finance.read_own`, and the owner may ask for either), money is whole VND and rates are basis points, the
// commission is `(base * rate + 5000) // 10000`, the revenue of a procedure is split by share with the remainder on
// the last performer, a rate and a basis are a snapshot of the entry, a closed month is frozen and immutable,
// a month closes only when it ended, has data, has no unpaid entry on the "Theo thực thu" basis and nothing
// pending, a receipt is idempotent on its key and never exceeds the open balance, a void needs a reason and is refused
// when money was received, and the owner alone reads the payment notifications.
import {
  PERFORMERS,
  entries,
  formatDots,
  invoiceOfOrder,
  invoices,
  nextInvoiceNumber,
  notifications,
  orderTotal,
  payments,
  periods,
  type EntryRecord,
  type FrozenRow,
  type InvoiceRecord,
  type PaymentRecord,
  type PeriodRecord,
} from "../data/finance";
import { clinicToday, patientById } from "../data/clinic";
import { rowsFor } from "../finance-rules";
import { orders } from "../data/orders";
import { services } from "../data/catalog";
import { USERS } from "../auth";
import {
  bodyOf,
  fail,
  isoFromNow,
  paginate,
  uid,
  type Ctx,
  type Permission,
  type Reply,
  type Router,
  type Schemas,
} from "../core";

type S = Schemas;

const MONTH_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/;
const FORBIDDEN = "Bạn không có quyền thực hiện thao tác này.";
const HISTORY_MONTHS = 12;

const M = {
  invalidMonth: "Tháng không hợp lệ",
  invalidDay: "Ngày thực hiện không hợp lệ",
  periodClosed: "Kỳ đã chốt",
  periodClosedEdit: "Kỳ đã chốt, không được sửa",
  needPeople: "Cần người thực hiện",
  duplicatePeople: "Trùng người thực hiện",
  invalidPerformer: "Người thực hiện không hợp lệ",
  shareTotal: "Tổng tỷ trọng doanh số phải là 100%",
  rateTotal: "Tổng tỷ lệ tiền thủ thuật không vượt 100%",
  noteRequired: "Ghi chú xác nhận hoàn tất là bắt buộc",
  invalidAmount: "Số tiền/tỷ lệ không hợp lệ",
  overAllocated: "Giá trị lượt vượt phần hóa đơn chưa phân bổ",
  wrongInvoice: "Hóa đơn không thuộc bệnh nhân này",
  entryVoid: "Lượt đã hủy",
  voidReason: "Cần lý do hủy",
  voidPaid: "Lượt đã thu tiền; cần quy trình hoàn/điều chỉnh riêng",
  onlyEnded: "Chỉ chốt tháng đã kết thúc",
  noData: "Kỳ không có dữ liệu",
  collectedOpen: "Còn lượt tính theo thực thu chưa thu đủ; chưa thể chốt để tránh mất tiền kỳ sau",
  pendingLeft: "Còn lượt chờ duyệt",
  closeBeforePay: "Cần chốt kỳ trước khi xác nhận chi",
  periodPaid: "Kỳ đã xác nhận chi",
  needReference: "Cần mã chứng từ chi",
  overpayment: "Số thu vượt công nợ",
  keyReused: "Mã giao dịch đã dùng cho nội dung khác",
  unknownService: "Không có thủ thuật",
  serviceOff: "Thủ thuật đã ngừng, không ghi thêm lượt",
  orderZero: "Đơn có giá trị 0 ₫, không cần hóa đơn.",
} as const;

const has = (ctx: Ctx, permission: Permission): boolean =>
  ctx.session?.permissions.includes(permission) ?? false;

function need(ctx: Ctx, ...permissions: Permission[]): void {
  if (!permissions.some((p) => has(ctx, p))) fail(403, "forbidden", FORBIDDEN);
}

// Declarations (not arrows): only a function with an explicit `never` signature narrows the code after a call.
function invalid(message: string): never {
  return fail(422, "validation_failed", message);
}

function invalidState(message: string): never {
  return fail(409, "invalid_state", message);
}

// -------------------------------------------------------------------------------------------------- names
function nameOf(id: string): string {
  return (
    PERFORMERS.find((p) => p.id === id)?.name ?? USERS.find((u) => u.id === id)?.display_name ?? ""
  );
}

// ---------------------------------------------------------------------------------------------- months
function monthQuery(ctx: Ctx): string {
  const value = ctx.query.get("month");
  if (value === null || !MONTH_PATTERN.test(value)) return invalid(M.invalidMonth);
  return value;
}

function monthParam(ctx: Ctx): string {
  const value = ctx.params.month ?? "";
  if (!MONTH_PATTERN.test(value)) return invalid(M.invalidMonth);
  return value;
}

const monthOf = (day: string): string => day.slice(0, 7);

/** The last `count` months ending with the one `today` is in, newest first. */
function previousMonths(today: string, count: number): string[] {
  const [year = 0, mon = 1] = today.split("-").map(Number);
  return Array.from({ length: count }, (_, i) => {
    const index = year * 12 + (mon - 1) - i;
    return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
  });
}

// ------------------------------------------------------------------------------------------------ rules
function invoiceById(id: string): InvoiceRecord {
  const found = invoices.find((i) => i.id === id);
  if (!found) fail(404, "not_found", "Không tìm thấy dữ liệu trong phòng khám này. (hóa đơn)");
  return found;
}

const rowsOf = (list: EntryRecord[]): FrozenRow[] =>
  rowsFor(list, {
    invoice: invoiceById,
    patientCode: (patientId) => patientById(patientId)?.code ?? "",
    doctorName: nameOf,
  });

const entriesOfMonth = (month: string): EntryRecord[] =>
  entries.filter((e) => monthOf(e.entry_date) === month);

const periodOf = (month: string): PeriodRecord | undefined =>
  periods.find((p) => p.month === month);

function periodOut(month: string, period: PeriodRecord | undefined): S["FinancePeriodOut"] {
  if (!period) return { month, status: "open", closed_at: null, paid_at: null, reference: null };
  return {
    month,
    status: period.status,
    closed_at: period.closed_at,
    paid_at: period.paid_at,
    reference: period.reference,
  };
}

/** The commission rows of a month: the frozen table when it is closed, computed from the live entries otherwise. */
function monthRows(month: string): FrozenRow[] {
  const period = periodOf(month);
  return period ? period.rows : rowsOf(entriesOfMonth(month));
}

/** Why a month cannot be closed, in the order of the old `mutate('close')`; null when it may be. */
function closeBlocker(month: string, today: string, list: EntryRecord[]): string | null {
  if (month >= monthOf(today)) return M.onlyEnded;
  if (list.length === 0) return M.noData;
  const unpaidCollected = list.some((e) => {
    if (e.status === "void" || e.basis !== "collected") return false;
    const invoice = invoiceById(e.invoice_id);
    return invoice.received_vnd < invoice.amount_vnd;
  });
  if (unpaidCollected) return M.collectedOpen;
  if (list.some((e) => e.status === "pending")) return M.pendingLeft;
  return null;
}

// ------------------------------------------------------------------------------------------------ scope
function resolveScope(ctx: Ctx): S["FinanceScope"] {
  need(ctx, "finance.read", "finance.read_own");
  const clinic = has(ctx, "finance.read");
  const requested = ctx.query.get("scope");
  if (requested === null || requested === "") return clinic ? "clinic" : "own";
  if (requested === "clinic") {
    need(ctx, "finance.read");
    return "clinic";
  }
  if (requested === "own") {
    need(ctx, "finance.read_own");
    return "own";
  }
  return invalid("Phạm vi không hợp lệ");
}

const projected = (rows: FrozenRow[], scope: S["FinanceScope"], ctx: Ctx): FrozenRow[] =>
  scope === "clinic" ? rows : rows.filter((r) => r.doctor_id === ctx.session?.userId);

function doctorsOf(scope: S["FinanceScope"], ctx: Ctx, rows: FrozenRow[]): S["FinanceDoctorOut"][] {
  if (scope === "own") {
    const me = ctx.session?.userId;
    return me ? [{ id: me, name: nameOf(me) }] : [];
  }
  const known = new Set(PERFORMERS.map((p) => p.id));
  const leavers = rows
    .filter((r) => !known.has(r.doctor_id))
    .map((r) => ({ id: r.doctor_id, name: r.doctor_name }));
  return [...PERFORMERS, ...leavers].filter(
    (d, i, all) => all.findIndex((x) => x.id === d.id) === i,
  );
}

// ---------------------------------------------------------------------------------------------- overview
const sum = (values: number[]): number => values.reduce((a, b) => a + b, 0);

function registerOverview(r: Router): void {
  r.get("/api/v1/finance/overview", null, (ctx): Reply => {
    const scope = resolveScope(ctx);
    const month = monthQuery(ctx);
    const rows = projected(monthRows(month), scope, ctx);
    const live = rows.filter((row) => row.status !== "void");
    const fee = sum(live.filter((row) => row.status === "approved").map((row) => row.fee_vnd));
    const pending = sum(live.filter((row) => row.status === "pending").map((row) => row.fee_vnd));
    const clinic = scope === "clinic";
    const revenue = clinic
      ? sum(
          entriesOfMonth(month)
            .filter((e) => e.status !== "void")
            .map((e) => e.net_vnd),
        )
      : sum(live.map((row) => row.revenue_vnd));
    const summary: S["FinanceSummaryOut"] = {
      revenue_vnd: revenue,
      fee_vnd: fee,
      pending_vnd: pending,
      collected_vnd: clinic
        ? sum(payments.filter((p) => monthOf(p.paid_on) === month).map((p) => p.amount_vnd))
        : null,
      debt_vnd: clinic ? sum(invoices.map((i) => i.amount_vnd - i.received_vnd)) : null,
    };
    const team = doctorsOf(scope, ctx, rows).map((doctor) => {
      const mine = live.filter((row) => row.doctor_id === doctor.id);
      return {
        doctor_id: doctor.id,
        doctor_name: doctor.name,
        entry_count: mine.length,
        revenue_vnd: sum(mine.map((row) => row.revenue_vnd)),
        fee_vnd: sum(mine.filter((row) => row.status === "approved").map((row) => row.fee_vnd)),
      };
    });
    const body: S["FinanceOverviewOut"] = {
      month,
      today: clinicToday(),
      scope,
      summary,
      period: periodOut(month, periodOf(month)),
      team,
      pending_entries: new Set(
        rows.filter((row) => row.status === "pending").map((row) => row.entry_id),
      ).size,
    };
    return { body };
  });
}

// ------------------------------------------------------------------------------------------------ entries
function entryOut(entry: EntryRecord): S["EntryOut"] {
  const invoice = invoiceById(entry.invoice_id);
  const patient = patientById(entry.patient_id);
  const rows = rowsOf([entry]);
  return {
    id: entry.id,
    entry_date: entry.entry_date,
    patient_id: entry.patient_id,
    patient_code: patient?.code ?? "",
    service_id: entry.service_id,
    service_name: entry.service_name,
    terms_version: entry.terms_version,
    basis: entry.basis,
    invoice_id: invoice.id,
    invoice_number: invoice.number,
    owns_invoice: entry.owns_invoice,
    list_vnd: entry.list_vnd,
    discount_vnd: entry.discount_vnd,
    net_vnd: entry.net_vnd,
    status: entry.status,
    note: entry.note,
    void_reason: entry.void_reason,
    people: rows.map((row) => ({
      doctor_id: row.doctor_id,
      doctor_name: row.doctor_name,
      share_bp: row.share_bp,
      rate_bp: row.rate_bp,
      revenue_vnd: row.revenue_vnd,
      fee_vnd: row.fee_vnd,
    })),
    version: entry.version,
  };
}

function entryOr404(ctx: Ctx): EntryRecord {
  const found = entries.find((e) => e.id === ctx.params.entry_id);
  if (!found)
    fail(404, "not_found", "Không tìm thấy dữ liệu trong phòng khám này. (lượt thủ thuật)");
  return found;
}

const isInt = (value: unknown, low: number, high: number): boolean =>
  typeof value === "number" && Number.isInteger(value) && value >= low && value <= high;

function checkPeople(people: S["EntryPersonIn"][]): void {
  if (people.length < 1 || people.length > 4) invalid(M.needPeople);
  if (new Set(people.map((p) => p.doctor_id)).size !== people.length) invalid(M.duplicatePeople);
  if (people.some((p) => !isInt(p.share_bp, 1, 10_000) || !isInt(p.rate_bp, 0, 10_000))) {
    invalid(M.invalidAmount);
  }
  if (sum(people.map((p) => p.share_bp)) !== 10_000) invalid(M.shareTotal);
  if (sum(people.map((p) => p.rate_bp)) > 10_000) invalid(M.rateTotal);
}

function registerEntries(r: Router): void {
  r.get("/api/v1/finance/entries", null, (ctx): Reply => {
    const scope = resolveScope(ctx);
    const month = monthQuery(ctx);
    const period = periodOf(month);
    const all = monthRows(month);
    const body: S["FinanceEntriesOut"] = {
      month,
      today: clinicToday(),
      scope,
      period: periodOut(month, period),
      rows: projected(all, scope, ctx),
      doctors: doctorsOf(scope, ctx, all),
      can_write: has(ctx, "finance.write") && scope === "clinic",
    };
    return { body };
  });

  r.get("/api/v1/finance/performers", "finance.write", (): Reply => ({ body: PERFORMERS }));

  r.post("/api/v1/finance/entries", "finance.write", (ctx): Reply => {
    const input = bodyOf<S["EntryCreate"]>(ctx);
    const today = clinicToday();
    if (!isInt(input.list_vnd, 1, 10 ** 12) || !isInt(input.discount_vnd ?? 0, 0, input.list_vnd)) {
      invalid(M.invalidAmount);
    }
    const discount = input.discount_vnd ?? 0;
    checkPeople(input.people ?? []);
    const note = (input.note ?? "").trim();
    if (note === "") invalid(M.noteRequired);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(input.entry_date) || input.entry_date > today) {
      invalid(M.invalidDay);
    }
    const month = monthOf(input.entry_date);
    if (periodOf(month)) invalidState(M.periodClosed);
    const service = services.find((s) => s.id === input.service_id);
    if (!service) invalid(M.unknownService);
    if (service && !service.active) invalid(M.serviceOff);
    const terms = service?.history.find((h) => h.version_no === service.terms_version);
    const patient = patientById(input.patient_id);
    if (!service || !terms) return invalid(M.unknownService);
    if (!patient)
      fail(404, "not_found", "Không tìm thấy dữ liệu trong phòng khám này. (bệnh nhân)");
    if (input.people.some((p) => !PERFORMERS.some((x) => x.id === p.doctor_id))) {
      invalid(M.invalidPerformer);
    }
    const net = input.list_vnd - discount;
    const owns = input.invoice_id == null;
    const linked = owns ? undefined : invoices.find((i) => i.id === input.invoice_id);
    if (!owns && (!linked || linked.patient_id !== patient.id)) invalid(M.wrongInvoice);
    if (linked) {
      const allocated = sum(
        entries
          .filter((e) => e.invoice_id === linked.id && e.status !== "void")
          .map((e) => e.net_vnd),
      );
      if (allocated + net > linked.amount_vnd) invalid(M.overAllocated);
    }
    const invoice: InvoiceRecord = linked ?? {
      id: uid("inv"),
      number: nextInvoiceNumber(input.entry_date),
      patient_id: patient.id,
      source: "finance",
      order_id: null,
      invoice_date: input.entry_date,
      amount_vnd: net,
      received_vnd: 0,
    };
    if (!linked) invoices.push(invoice);
    const created: EntryRecord = {
      id: uid("entry"),
      patient_id: patient.id,
      service_id: service.id,
      service_name: service.name,
      terms_version: terms.version_no,
      basis: terms.basis,
      entry_date: input.entry_date,
      invoice_id: invoice.id,
      owns_invoice: owns,
      list_vnd: input.list_vnd,
      discount_vnd: discount,
      net_vnd: net,
      status: "pending",
      note,
      void_reason: null,
      people: input.people.map((p) => ({
        doctor_id: p.doctor_id,
        share_bp: p.share_bp,
        rate_bp: p.rate_bp,
      })),
      version: 1,
    };
    entries.push(created);
    return { status: 201, body: entryOut(created) };
  });

  r.post("/api/v1/finance/entries/{entry_id}/approve", "finance.write", (ctx): Reply => {
    const entry = entryOr404(ctx);
    if (periodOf(monthOf(entry.entry_date))) invalidState(M.periodClosedEdit);
    if (entry.status === "void") invalidState(M.entryVoid);
    if (entry.status !== "approved") {
      entry.status = "approved";
      entry.version += 1;
    }
    return { body: entryOut(entry) };
  });

  r.post("/api/v1/finance/entries/{entry_id}/void", "finance.write", (ctx): Reply => {
    const entry = entryOr404(ctx);
    const input = bodyOf<S["EntryVoid"]>(ctx);
    if (periodOf(monthOf(entry.entry_date))) invalidState(M.periodClosedEdit);
    if (entry.status === "void") invalidState(M.entryVoid);
    const reason = (input.reason ?? "").trim();
    if (reason === "") invalid(M.voidReason);
    const invoice = invoiceById(entry.invoice_id);
    if (invoice.received_vnd !== 0) invalidState(M.voidPaid);
    const others = entries.some(
      (e) => e.invoice_id === invoice.id && e.id !== entry.id && e.status !== "void",
    );
    if (entry.owns_invoice && !others) invoice.amount_vnd = 0;
    entry.status = "void";
    entry.void_reason = reason;
    entry.version += 1;
    return { body: entryOut(entry) };
  });
}

// ------------------------------------------------------------------------------------------------ periods
function registerPeriods(r: Router): void {
  r.get("/api/v1/finance/periods", "finance.read", (): Reply => {
    const today = clinicToday();
    const items = previousMonths(today, HISTORY_MONTHS).map((month): S["PeriodRowOut"] => {
      const list = entriesOfMonth(month);
      const period = periodOf(month);
      const blocker = period ? null : closeBlocker(month, today, list);
      return {
        month,
        status: period?.status ?? "open",
        entry_count: list.length,
        pending_count: list.filter((e) => e.status === "pending").length,
        closable: period === undefined && blocker === null,
        blocker,
        closed_at: period?.closed_at ?? null,
        paid_at: period?.paid_at ?? null,
        reference: period?.reference ?? null,
      };
    });
    return { body: { today, items } satisfies S["PeriodListOut"] };
  });

  r.post("/api/v1/finance/periods/{month}/close", "finance.write", (ctx): Reply => {
    const month = monthParam(ctx);
    if (periodOf(month)) invalidState(M.periodClosed);
    const list = entriesOfMonth(month);
    const blocker = closeBlocker(month, clinicToday(), list);
    if (blocker !== null) invalidState(blocker);
    const period: PeriodRecord = {
      month,
      status: "closed",
      closed_at: isoFromNow(0),
      paid_at: null,
      reference: null,
      rows: rowsOf(list),
    };
    periods.push(period);
    return { body: periodOut(month, period) };
  });

  r.post("/api/v1/finance/periods/{month}/pay", "finance.write", (ctx): Reply => {
    const month = monthParam(ctx);
    const reference = (bodyOf<S["PeriodPay"]>(ctx).reference ?? "").trim();
    if (reference === "") invalid(M.needReference);
    const period = periodOf(month);
    if (!period) invalidState(M.closeBeforePay);
    if (period?.status === "paid") invalidState(M.periodPaid);
    if (!period) return invalidState(M.closeBeforePay);
    period.status = "paid";
    period.reference = reference;
    period.paid_at = isoFromNow(0);
    return { body: periodOut(month, period) };
  });
}

// ------------------------------------------------------------------------------------------------- export
/** Excel reads the accents of a UTF-8 CSV only when it starts with a byte order mark. */
const BYTE_ORDER_MARK = String.fromCharCode(0xfeff);

const CSV_HEADER = [
  "Ngay",
  "Ho so",
  "Thu thuat",
  "Bac si",
  "Doanh so",
  "Co so",
  "Ty le %",
  "Tien thu thuat",
  "Trang thai",
];

/** A cell Excel cannot read as a formula: text that starts with `=`, `+`, `-`, `@`, tab or CR gets an apostrophe. */
function csvSafe(value: string | number): string {
  const text = String(value);
  return /^[=+\-@\t\r]/.test(text) ? `'${text}` : text;
}

function csvCell(value: string | number): string {
  const text = csvSafe(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function registerExport(r: Router): void {
  r.get("/api/v1/finance/export", null, (ctx): Reply => {
    const scope = resolveScope(ctx);
    const month = monthQuery(ctx);
    const lines = projected(monthRows(month), scope, ctx).map((row) =>
      [
        row.date,
        row.patient_code,
        row.service_name,
        row.doctor_name,
        row.revenue_vnd,
        row.base_vnd,
        row.rate_bp / 100,
        row.fee_vnd,
        row.status,
      ]
        .map(csvCell)
        .join(","),
    );
    const text = `${BYTE_ORDER_MARK}${[CSV_HEADER.join(","), ...lines].join("\r\n")}\r\n`;
    return {
      raw: Buffer.from(text, "utf8"),
      headers: {
        "content-type": "text/csv; charset=utf-8",
        "content-disposition": `attachment; filename="Pema-tien-thu-thuat-${month}.csv"`,
        "cache-control": "no-store",
      },
    };
  });
}

// ------------------------------------------------------------------------------------------------ cash
function invoiceOut(invoice: InvoiceRecord): S["InvoiceOut"] {
  const patient = patientById(invoice.patient_id);
  return {
    id: invoice.id,
    number: invoice.number,
    patient_id: invoice.patient_id,
    patient_code: patient?.code ?? "",
    patient_name: patient?.full_name ?? "",
    source: invoice.source,
    order_id: invoice.order_id,
    invoice_date: invoice.invoice_date,
    amount_vnd: invoice.amount_vnd,
    received_vnd: invoice.received_vnd,
    due_vnd: invoice.amount_vnd - invoice.received_vnd,
  };
}

function paymentOut(payment: PaymentRecord, replayed: boolean): S["PaymentOut"] {
  const invoice = invoiceById(payment.invoice_id);
  return {
    id: payment.id,
    key: payment.key,
    invoice_id: payment.invoice_id,
    invoice_number: invoice.number,
    patient_code: patientById(payment.patient_id)?.code ?? "",
    amount_vnd: payment.amount_vnd,
    method: payment.method,
    paid_on: payment.paid_on,
    created_at: payment.created_at,
    replayed,
  };
}

const METHOD_LABEL: Record<S["PaymentMethod"], string> = {
  cash: "Tiền mặt",
  transfer: "Chuyển khoản",
};

function notificationOut(n: (typeof notifications)[number]): S["NotificationOut"] {
  return { ...n };
}

function registerCash(r: Router): void {
  r.get("/api/v1/finance/invoices", null, (ctx): Reply => {
    need(ctx, "finance.read", "finance.collect");
    const dueOnly = ctx.query.get("due_only") === "true";
    const patientId = ctx.query.get("patient_id");
    const rows = invoices
      .filter((i) => !dueOnly || i.received_vnd < i.amount_vnd)
      .filter((i) => patientId === null || i.patient_id === patientId)
      .toSorted((a, b) => b.invoice_date.localeCompare(a.invoice_date));
    return { body: paginate(rows.map(invoiceOut), ctx.query) };
  });

  r.get("/api/v1/finance/billable-orders", null, (ctx): Reply => {
    need(ctx, "finance.read", "finance.collect");
    const body: S["BillableOrderOut"][] = orders
      .filter((o) => invoiceOfOrder(o.id) === undefined && orderTotal(o) > 0)
      .toSorted((a, b) => b.created_at.localeCompare(a.created_at))
      .map((o) => {
        const patient = patientById(o.patient_id);
        return {
          order_id: o.id,
          patient_id: o.patient_id,
          patient_code: patient?.code ?? "",
          patient_name: patient?.full_name ?? "",
          status: o.status,
          order_date: o.order_date,
          total_vnd: orderTotal(o),
        };
      });
    return { body };
  });

  r.post("/api/v1/finance/invoices/from-order", "finance.collect", (ctx): Reply => {
    const input = bodyOf<S["InvoiceFromOrder"]>(ctx);
    const order = orders.find((o) => o.id === input.order_id);
    if (!order) fail(404, "not_found", "Không tìm thấy dữ liệu trong phòng khám này. (đơn)");
    const existing = invoiceOfOrder(order.id);
    if (existing) return { status: 201, body: invoiceOut(existing) };
    if (orderTotal(order) <= 0) invalid(M.orderZero);
    const created: InvoiceRecord = {
      id: uid("inv"),
      number: nextInvoiceNumber(order.order_date),
      patient_id: order.patient_id,
      source: "order",
      order_id: order.id,
      invoice_date: order.order_date,
      amount_vnd: orderTotal(order),
      received_vnd: 0,
    };
    invoices.push(created);
    return { status: 201, body: invoiceOut(created) };
  });

  r.get("/api/v1/finance/payments", "finance.read", (ctx): Reply => {
    const month = monthQuery(ctx);
    const rows = payments
      .filter((p) => monthOf(p.paid_on) === month)
      .toSorted(
        (a, b) => b.paid_on.localeCompare(a.paid_on) || b.created_at.localeCompare(a.created_at),
      );
    return {
      body: paginate(
        rows.map((p) => paymentOut(p, false)),
        ctx.query,
      ),
    };
  });

  r.post("/api/v1/finance/payments", "finance.collect", (ctx): Reply => {
    const input = bodyOf<S["PaymentCreate"]>(ctx);
    const key = input.id;
    if (typeof key !== "string" || key.length < 3 || key.length > 160) {
      invalid("Cần mã chống thu trùng");
    }
    const earlier = payments.find((p) => p.key === key);
    if (earlier) {
      const same =
        earlier.invoice_id === input.invoice_id &&
        earlier.amount_vnd === input.amount_vnd &&
        earlier.method === input.method;
      if (!same) fail(409, "duplicate_request", M.keyReused);
      return { status: 200, body: paymentOut(earlier, true) };
    }
    const invoice = invoiceById(input.invoice_id);
    if (!isInt(input.amount_vnd, 1, 10 ** 12)) invalid(M.invalidAmount);
    if (input.method !== "cash" && input.method !== "transfer") invalid("Phương thức không hợp lệ");
    if (input.amount_vnd > invoice.amount_vnd - invoice.received_vnd) invalid(M.overpayment);
    invoice.received_vnd += input.amount_vnd;
    const created: PaymentRecord = {
      id: uid("pay"),
      key,
      invoice_id: invoice.id,
      patient_id: invoice.patient_id,
      amount_vnd: input.amount_vnd,
      method: input.method,
      paid_on: clinicToday(),
      created_at: isoFromNow(0),
    };
    payments.push(created);
    const patient = patientById(invoice.patient_id);
    notifications.unshift({
      id: uid("note"),
      payment_id: created.id,
      invoice_id: invoice.id,
      title: "Đã nhận thanh toán",
      body: `${patient?.code ?? ""} · ${formatDots(created.amount_vnd)} đ · ${METHOD_LABEL[created.method]}`,
      amount_vnd: created.amount_vnd,
      created_at: created.created_at,
      read: false,
    });
    const order = invoice.order_id ? orders.find((o) => o.id === invoice.order_id) : undefined;
    if (order) {
      order.received_vnd = invoice.received_vnd;
      order.paid = invoice.received_vnd >= invoice.amount_vnd;
    }
    return { status: 201, body: paymentOut(created, false) };
  });

  r.get("/api/v1/finance/notifications", "finance.notifications", (): Reply => ({
    body: notifications
      .toSorted((a, b) => b.created_at.localeCompare(a.created_at))
      .slice(0, 100)
      .map(notificationOut),
  }));

  r.post(
    "/api/v1/finance/notifications/{notification_id}/read",
    "finance.notifications",
    (ctx): Reply => {
      const found = notifications.find((n) => n.id === ctx.params.notification_id);
      if (!found)
        fail(404, "not_found", "Không tìm thấy dữ liệu trong phòng khám này. (thông báo)");
      found.read = true;
      return { body: notificationOut(found) };
    },
  );
}

export function register(r: Router): void {
  registerOverview(r);
  registerEntries(r);
  registerPeriods(r);
  registerExport(r);
  registerCash(r);
}
