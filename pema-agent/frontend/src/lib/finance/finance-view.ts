// Pure rules of the finance screens (`/finance/*` and the invoice panel of `/cashier`; package U, step U6).
// The backend owns every rule (the projection by role, rate snapshots, rounding, closed months, idempotent receipts,
// no over-collection); this file words things for the screen and checks a form BEFORE it is sent with the same
// sentences the old web gave (`prototype/finance/finance.js`, `finance_server.py`), so a mistake is told in place and
// the BE answer stays the last word. Money is whole VND; shares and rates are basis points (10000 = 100 %).
import type { Schemas } from "@/lib/api";
import { ApiError } from "@/lib/api/client";
import {
  BASIS_LABEL,
  bpToPercentText,
  formatRate,
  formatVnd,
  percentTextToBp,
} from "@/lib/catalog/catalog-view";
import { clinicDateKey } from "@/lib/ops/format";

export { BASIS_LABEL, bpToPercentText, formatRate, formatVnd, percentTextToBp };

/** Basis points for a number box: a number input only holds a dot ("12.5"), never the comma of `bpToPercentText`. */
export function bpToInputText(bp: number): string {
  return String(bp / 100);
}

export type FinanceScope = Schemas["FinanceScope"];
export type PeriodStatus = Schemas["PeriodStatus"];
export type EntryStatus = Schemas["EntryStatus"];
export type FinanceOverview = Schemas["FinanceOverviewOut"];
export type FinanceSummary = Schemas["FinanceSummaryOut"];
export type FinanceEntries = Schemas["FinanceEntriesOut"];
export type FinanceRow = Schemas["FinanceRowOut"];
export type FinancePeriod = Schemas["FinancePeriodOut"];
export type PeriodRow = Schemas["PeriodRowOut"];
export type EntryCreateBody = Schemas["EntryCreate"];
export type InvoiceRow = Schemas["InvoiceOut"];
export type PaymentRow = Schemas["PaymentOut"];
export type NotificationRow = Schemas["NotificationOut"];
export type BillableOrder = Schemas["BillableOrderOut"];
export type PaymentMethod = Schemas["PaymentMethod"];
export type Doctor = Schemas["FinanceDoctorOut"];

// ------------------------------------------------------------------------------------------------- labels
/** Labels of the old web (`finance.js` `statuses`). */
export const STATUS_LABEL: Record<PeriodStatus | EntryStatus, string> = {
  open: "Đang đối soát",
  closed: "Đã chốt tháng",
  paid: "Đã chi",
  pending: "Chờ duyệt",
  approved: "Đã duyệt",
  void: "Đã hủy",
};

export type StatusTone = "neutral" | "info" | "success" | "warning";

export const STATUS_TONE: Record<PeriodStatus | EntryStatus, StatusTone> = {
  open: "neutral",
  closed: "info",
  paid: "success",
  pending: "warning",
  approved: "success",
  void: "neutral",
};

export const METHOD_LABEL: Record<PaymentMethod, string> = {
  cash: "Tiền mặt",
  transfer: "Chuyển khoản",
};

export const METHODS: readonly PaymentMethod[] = ["cash", "transfer"];

/** The method a `<select>` value stands for; the value always comes from `METHODS`, cash is only the fallback. */
export function asMethod(value: string): PaymentMethod {
  return METHODS.find((method) => method === value) ?? "cash";
}

/** The old finance page said these when the screen could not load or an action failed. */
export const NOT_CONNECTED = "Chưa kết nối dữ liệu tài chính";
export const EXPORT_FAILED = "Không xuất được bảng";
export const NO_ENTRIES = "Chưa có lượt thủ thuật trong kỳ này.";
export const NO_PAYMENTS = "Chưa có phiếu thu.";
export const NO_INVOICES = "Không có hóa đơn.";
export const MONTH_RULE =
  "Tỷ lệ lưu theo từng lượt. Đổi chính sách không tính lại lịch sử. Khoản theo thực thu được đóng băng khi chốt kỳ.";

export function financeErrorMessage(error: unknown): string {
  return error instanceof ApiError || error instanceof Error ? error.message : "Có lỗi xảy ra";
}

/** "Chưa kết nối dữ liệu tài chính: <reason>". */
export function notConnected(reason: string): string {
  return `${NOT_CONNECTED}: ${reason}`;
}

// ------------------------------------------------------------------------------------------ month and scope
const MONTH_FORMAT = /^\d{4}-(0[1-9]|1[0-2])$/;

export function isMonth(value: string | null | undefined): value is string {
  return value !== null && value !== undefined && MONTH_FORMAT.test(value);
}

/** `YYYY-MM` of the clinic's today. */
export function currentMonth(now: Date = new Date()): string {
  return clinicDateKey(now).slice(0, 7);
}

/** The month of the address, or the current one when the address has none or a broken one. */
export function monthFromParam(raw: string | null, now: Date = new Date()): string {
  return isMonth(raw) ? raw : currentMonth(now);
}

/**
 * Which projection the screen asks for. A doctor (`finance.read_own` only) is always personal; the accountant
 * (`finance.read` only) is always the clinic; the owner holds both and may flip with `?scope=own`.
 */
export function scopeFor(
  permissions: { canRead: boolean; canReadOwn: boolean },
  requested: string | null,
): FinanceScope {
  if (!permissions.canRead) return "own";
  if (!permissions.canReadOwn) return "clinic";
  return requested === "own" ? "own" : "clinic";
}

export const SCOPE_LABEL: Record<FinanceScope, string> = {
  clinic: "Toàn phòng khám",
  own: "Cá nhân",
};

/** `/finance/entries?month=2026-09&scope=own`: the clinic scope is the default and stays out of the address. */
export function financeHref(path: string, month: string, scope: FinanceScope): string {
  const params = new URLSearchParams({ month });
  if (scope === "own") params.set("scope", "own");
  return `${path}?${params.toString()}`;
}

export type FinanceTabId = "overview" | "entries" | "rates" | "payments" | "periods" | "export";

type FinanceTab = { id: FinanceTabId; href: string; label: string; clinicOnly: boolean };

/** The four tabs of the old web, then the two screens this app adds (the month's close and the export). */
export const FINANCE_TABS: readonly FinanceTab[] = [
  { id: "overview", href: "/finance", label: "Tổng quan", clinicOnly: false },
  { id: "entries", href: "/finance/entries", label: "Tiền thủ thuật", clinicOnly: false },
  { id: "rates", href: "/finance/rates", label: "Chính sách tỷ lệ", clinicOnly: true },
  { id: "payments", href: "/finance/payments", label: "Phiếu thu & thông báo", clinicOnly: true },
  { id: "periods", href: "/finance/periods", label: "Chốt kỳ", clinicOnly: true },
  { id: "export", href: "/finance/export", label: "Xuất CSV", clinicOnly: false },
];

/** A doctor (and the owner looking at the personal projection) sees "Tổng quan", "Tiền thủ thuật" and "Xuất CSV". */
export function visibleTabs(scope: FinanceScope): FinanceTab[] {
  return FINANCE_TABS.filter((tab) => scope === "clinic" || !tab.clinicOnly);
}

/** The tab that holds a path (`/finance/entries` is "Tiền thủ thuật", `/finance` only itself). */
export function tabOfPath(pathname: string): FinanceTabId {
  return (
    FINANCE_TABS.filter((tab) => tab.href !== "/finance").find(
      (tab) => pathname === tab.href || pathname.startsWith(`${tab.href}/`),
    )?.id ?? "overview"
  );
}

// ------------------------------------------------------------------------------------------------ overview
export type TileSpec = { label: string; value: string; note: string; tone?: "success" | "warning" };

/** The numbers of the overview: four for the clinic, three of the personal view (no cash, no debt). */
export function overviewTiles(summary: FinanceSummary, scope: FinanceScope): TileSpec[] {
  const fee: TileSpec = {
    label: "Tiền thủ thuật đã duyệt",
    value: formatVnd(summary.fee_vnd),
    note: "Không phải lợi nhuận phòng khám",
    tone: "success",
  };
  if (scope === "own") {
    return [
      {
        label: "Doanh số của tôi",
        value: formatVnd(summary.revenue_vnd),
        note: "Theo ngày hoàn tất thủ thuật",
      },
      {
        label: "Tiền chờ duyệt",
        value: formatVnd(summary.pending_vnd),
        note: "Chưa tính vào khoản đã duyệt",
        tone: "warning",
      },
      fee,
    ];
  }
  return [
    {
      label: "Doanh số thực hiện",
      value: formatVnd(summary.revenue_vnd),
      note: "Theo ngày hoàn tất thủ thuật",
    },
    {
      label: "Thực thu trong tháng",
      value: formatVnd(summary.collected_vnd ?? 0),
      note: "Theo ngày phiếu thu",
    },
    {
      label: "Công nợ hiện tại",
      value: formatVnd(summary.debt_vnd ?? 0),
      note: "Tất cả hóa đơn, không chỉ trong tháng",
      tone: "warning",
    },
    fee,
  ];
}

/** The small line over the hero title: the personal view, the accountant, or the owner. */
export function heroOver(scope: FinanceScope, isOwner: boolean): string {
  if (scope === "own") return "GÓC NHÌN CÁ NHÂN";
  return isOwner ? "CHỦ PHÒNG KHÁM • TỔNG QUAN ĐIỀU HÀNH" : "KẾ TOÁN • ĐỐI SOÁT";
}

export function heroTitle(scope: FinanceScope): string {
  return scope === "own"
    ? "Công việc được ghi nhận, thu nhập rõ ràng"
    : "Một màn hình, nắm rõ dòng tiền";
}

export function heroLine(month: string): string {
  return `Kỳ ${month} · Doanh số thực hiện và tiền đã thu được theo dõi riêng.`;
}

/** Width of a doctor's bar in "Đóng góp của đội ngũ": the share of the month's revenue, 0 to 100. */
export function barPercent(revenue: number, total: number): number {
  return Math.min(100, Math.round((revenue / Math.max(total, 1)) * 1000) / 10);
}

// ------------------------------------------------------------------------------------------------ entries
/** "300.000 ₫ × 10%": the base the rate is applied to and the rate of that row. */
export function baseLine(row: Pick<FinanceRow, "base_vnd" | "rate_bp">): string {
  return `${formatVnd(row.base_vnd)} × ${formatRate(row.rate_bp)}`;
}

/** Approve and void exist only while the month is open, for whoever may write, on a row that is not void. */
export function canAct(period: FinancePeriod, canWrite: boolean, status: EntryStatus): boolean {
  return canWrite && period.status === "open" && status !== "void";
}

export type PeriodAction = "close" | "pay";

/**
 * The button under the table: close an open month (`finance_period.close`: the accountant, with owner and manager as
 * override), confirm the payout of a closed one (`finance.write`), nothing for a paid one. `canClose` follows
 * `canWrite` when a caller does not tell them apart.
 */
export function periodAction(
  status: PeriodStatus,
  canWrite: boolean,
  canClose: boolean = canWrite,
): PeriodAction | null {
  if (status === "open") return canClose ? "close" : null;
  if (status === "closed") return canWrite ? "pay" : null;
  return null;
}

export const PERIOD_ACTION_LABEL: Record<PeriodAction, string> = {
  close: "Chốt tháng đã kết thúc",
  pay: "Xác nhận đã chi",
};

/** The old `confirm()` text of the close. */
export function closeQuestion(month: string): string {
  return `Chốt số liệu tháng ${month}? Các lượt trong kỳ sẽ bị khóa.`;
}

// ---------------------------------------------------------------------------------------------- entry form
export type PersonForm = { doctorId: string; share: string; rate: string };

/** Text of the form to record a performed procedure, as typed. */
export type EntryForm = {
  patientId: string;
  serviceId: string;
  date: string;
  list: string;
  discount: string;
  invoiceId: string;
  note: string;
  people: [PersonForm, PersonForm];
};

type ServiceDefaults = { id: string; price_vnd: number; rate_bp?: number | null };

/**
 * A fresh form. The price and the main performer's rate come from the service; the first performer of the list is
 * only a starting choice and is never taken from the doctor in charge of the patient (PB02).
 */
export function emptyEntryForm(
  today: string,
  service: ServiceDefaults | undefined,
  firstDoctorId: string,
): EntryForm {
  return {
    patientId: "",
    serviceId: service?.id ?? "",
    date: today,
    list: String(service?.price_vnd ?? ""),
    discount: "0",
    invoiceId: "",
    note: "",
    people: [
      {
        doctorId: firstDoctorId,
        share: "100",
        rate: bpToInputText(service?.rate_bp ?? 0),
      },
      { doctorId: "", share: "0", rate: "0" },
    ],
  };
}

/** Choosing another service changes the price and the main performer's rate, like the old form. */
export function withService(form: EntryForm, service: ServiceDefaults): EntryForm {
  const [main, other] = form.people;
  return {
    ...form,
    serviceId: service.id,
    list: String(service.price_vnd),
    people: [{ ...main, rate: bpToInputText(service.rate_bp ?? 0) }, other],
  };
}

export function patchPerson(form: EntryForm, index: 0 | 1, patch: Partial<PersonForm>): EntryForm {
  const [first, second] = form.people;
  return {
    ...form,
    people: index === 0 ? [{ ...first, ...patch }, second] : [first, { ...second, ...patch }],
  };
}

export const ENTRY_PROBLEMS = {
  patient: "Chọn hồ sơ bệnh nhân",
  service: "Không có thủ thuật",
  day: "Ngày thực hiện không hợp lệ",
  amount: "Số tiền/tỷ lệ không hợp lệ",
  people: "Cần người thực hiện",
  duplicate: "Trùng người thực hiện",
  shares: "Tổng tỷ trọng doanh số phải là 100%",
  rates: "Tổng tỷ lệ tiền thủ thuật không vượt 100%",
  note: "Ghi chú xác nhận hoàn tất là bắt buộc",
} as const;

export type ParsedEntry = { ok: true; body: EntryCreateBody } | { ok: false; problem: string };

const DIGITS = /^\d{1,12}$/;

/** Whole VND typed in a box, or null when it is not a non-negative integer. */
export function vndFromText(text: string): number | null {
  const clean = text.trim();
  return DIGITS.test(clean) ? Number(clean) : null;
}

const sumOf = (values: readonly number[]): number => values.reduce((a, b) => a + b, 0);

function parsePeople(form: EntryForm): { people: EntryCreateBody["people"] } | { problem: string } {
  const chosen = form.people.filter((person) => person.doctorId !== "");
  const people = chosen.map((person) => ({
    doctor_id: person.doctorId,
    share_bp: percentTextToBp(person.share),
    rate_bp: percentTextToBp(person.rate),
  }));
  const valid = people.flatMap((p) =>
    p.share_bp !== null && p.share_bp >= 1 && p.rate_bp !== null
      ? [{ doctor_id: p.doctor_id, share_bp: p.share_bp, rate_bp: p.rate_bp }]
      : [],
  );
  if (people.length === 0) return { problem: ENTRY_PROBLEMS.people };
  if (valid.length !== people.length) return { problem: ENTRY_PROBLEMS.amount };
  if (new Set(valid.map((p) => p.doctor_id)).size !== valid.length) {
    return { problem: ENTRY_PROBLEMS.duplicate };
  }
  if (sumOf(valid.map((p) => p.share_bp)) !== 10_000) return { problem: ENTRY_PROBLEMS.shares };
  if (sumOf(valid.map((p) => p.rate_bp)) > 10_000) return { problem: ENTRY_PROBLEMS.rates };
  return { people: valid };
}

/** The form as the body of `POST /finance/entries`, or the old web's sentence about what is wrong. */
export function parseEntryForm(form: EntryForm, today: string): ParsedEntry {
  if (form.patientId === "") return { ok: false, problem: ENTRY_PROBLEMS.patient };
  if (form.serviceId === "") return { ok: false, problem: ENTRY_PROBLEMS.service };
  if (!/^\d{4}-\d{2}-\d{2}$/.test(form.date) || form.date > today) {
    return { ok: false, problem: ENTRY_PROBLEMS.day };
  }
  const list = vndFromText(form.list);
  const discount = vndFromText(form.discount);
  if (list === null || list < 1 || discount === null || discount > list) {
    return { ok: false, problem: ENTRY_PROBLEMS.amount };
  }
  const parsed = parsePeople(form);
  if ("problem" in parsed) return { ok: false, problem: parsed.problem };
  const note = form.note.trim();
  if (note === "") return { ok: false, problem: ENTRY_PROBLEMS.note };
  return {
    ok: true,
    body: {
      patient_id: form.patientId,
      service_id: form.serviceId,
      entry_date: form.date,
      list_vnd: list,
      discount_vnd: discount,
      invoice_id: form.invoiceId === "" ? null : form.invoiceId,
      note,
      people: parsed.people,
    },
  };
}

/** One line of the "Gắn hóa đơn đã có" select: "P001 · HD-2609-0001 · 300.000 ₫". */
export function invoiceChoiceLabel(invoice: InvoiceRow): string {
  return `${invoice.patient_code} · ${invoice.number} · ${formatVnd(invoice.amount_vnd)}`;
}

// ------------------------------------------------------------------------------------------------- rates
/** Text of the rate form of one service. */
export type RateForm = { basis: Schemas["ServiceBasis"]; rate: string };

export const RATE_PROBLEM = "Tỷ lệ tiền thủ thuật từ 0 đến 100%, tối đa hai chữ số thập phân.";

export function rateFormOf(service: {
  rate_bp?: number | null;
  basis?: Schemas["ServiceBasis"] | null;
}): RateForm {
  return { basis: service.basis ?? "net", rate: bpToInputText(service.rate_bp ?? 0) };
}

export function rateChanged(
  service: { rate_bp?: number | null; basis?: Schemas["ServiceBasis"] | null },
  form: RateForm,
): boolean {
  return (
    percentTextToBp(form.rate) !== (service.rate_bp ?? 0) || form.basis !== (service.basis ?? "net")
  );
}

// ---------------------------------------------------------------------------------------------- receipts
export const PAYMENT_PROBLEM = "Số tiền phải lớn hơn 0 và không vượt số còn lại.";
export const OVERPAYMENT = "Số thu vượt công nợ";

/** The amount typed in the receipt form, or null when it is not a whole number above zero. */
export function paymentAmount(text: string): number | null {
  const value = vndFromText(text);
  return value === null || value < 1 ? null : value;
}

/** "HD-2609-0001 · Còn lại 150.000 ₫" (the notice of the "Thu tiền" dialog). */
export function dueLine(invoice: Pick<InvoiceRow, "number" | "due_vnd">): string {
  return `${invoice.number} · Còn lại ${formatVnd(invoice.due_vnd)}`;
}

/** "Hóa đơn còn nợ" option: "P001 · 150.000 ₫ · HD-2609-0001". */
export function dueChoiceLabel(invoice: InvoiceRow): string {
  return `${invoice.patient_code} · ${formatVnd(invoice.due_vnd)} · ${invoice.number}`;
}

export type InvoiceFilter = "all" | "due" | "paid";

export const INVOICE_FILTERS: readonly { id: InvoiceFilter; label: string }[] = [
  { id: "all", label: "Tất cả" },
  { id: "due", label: "Còn phải thu" },
  { id: "paid", label: "Đã thanh toán" },
];

export function matchesFilter(invoice: InvoiceRow, filter: InvoiceFilter): boolean {
  if (filter === "due") return invoice.due_vnd > 0;
  if (filter === "paid") return invoice.due_vnd <= 0 && invoice.amount_vnd > 0;
  return true;
}

export type InvoiceTotals = { count: number; received: number; due: number };

export function invoiceTotals(invoices: readonly InvoiceRow[]): InvoiceTotals {
  return {
    count: invoices.length,
    received: sumOf(invoices.map((i) => i.received_vnd)),
    due: sumOf(invoices.map((i) => Math.max(0, i.due_vnd))),
  };
}

/** "Buổi chăm sóc / điều trị" for a procedure invoice, "Đơn sản phẩm" for the invoice of a quick order. */
export function invoiceKind(invoice: Pick<InvoiceRow, "source">): string {
  return invoice.source === "order" ? "Đơn sản phẩm" : "Buổi chăm sóc / điều trị";
}

/** "HD-2609-0001 · 2026-09-06". */
export function invoiceLine(invoice: Pick<InvoiceRow, "number" | "invoice_date">): string {
  return `${invoice.number} · ${invoice.invoice_date}`;
}

/** The notification time as the old page showed it: "2026-09-12 10:30". */
export function notificationTime(iso: string): string {
  return iso.slice(0, 16).replace("T", " ");
}

// ------------------------------------------------------------------------------------------------ export
export function csvFileName(month: string): string {
  return `Pema-tien-thu-thuat-${month}.csv`;
}
