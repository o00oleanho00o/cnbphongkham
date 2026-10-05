// Fictional finance data for the PB02 screens (`/finance/*` and the invoice panel of the cashier). Same shape as
// `prototype/finance_server.py` `seed()`: the four sample services and four performers, 24 procedures with one
// invoice and one receipt each over the previous and the current month. The previous month stays OPEN (all its
// entries approved) so the close flow can be tried; the current month holds some pending entries and one entry on
// the "Theo thực thu" basis whose invoice is half paid. Dates follow the real clock like the other mock data.
// Patients, doctors, amounts and voucher codes are synthetic.
import { USERS } from "../auth";
import {
  DOCTOR_AN,
  DOCTOR_MAI,
  DOCTOR_NAMES,
  DOCTOR_TAM,
  clinicToday,
  patientById,
  patientRef,
} from "./clinic";
import { orders } from "./orders";
import { services } from "./catalog";
import { DAY, isoFromNow, uuid, type Schemas } from "../core";
import { rowsFor } from "../finance-rules";

type S = Schemas;

export type PersonRecord = { doctor_id: string; share_bp: number; rate_bp: number };

export type EntryRecord = {
  id: string;
  patient_id: string;
  service_id: string;
  service_name: string;
  terms_version: number;
  basis: S["ServiceBasis"];
  entry_date: string;
  invoice_id: string;
  owns_invoice: boolean;
  list_vnd: number;
  discount_vnd: number;
  net_vnd: number;
  status: S["EntryStatus"];
  note: string;
  void_reason: string | null;
  people: PersonRecord[];
  version: number;
};

export type InvoiceRecord = {
  id: string;
  number: string;
  patient_id: string;
  source: S["InvoiceSource"];
  order_id: string | null;
  invoice_date: string;
  amount_vnd: number;
  received_vnd: number;
};

export type PaymentRecord = {
  id: string;
  key: string;
  invoice_id: string;
  patient_id: string;
  amount_vnd: number;
  method: S["PaymentMethod"];
  paid_on: string;
  created_at: string;
};

export type NotificationRecord = {
  id: string;
  payment_id: string;
  invoice_id: string;
  title: string;
  body: string;
  amount_vnd: number;
  created_at: string;
  read: boolean;
};

/** A closed month keeps its commission table: reads of it never look at the live rates, shares or receipts. */
export type FrozenRow = S["FinanceRowOut"];
export type PeriodRecord = {
  month: string;
  status: "closed" | "paid";
  closed_at: string;
  paid_at: string | null;
  reference: string | null;
  rows: FrozenRow[];
};

const OWNER_ID = USERS.find((u) => u.role === "owner")?.id ?? uuid(1, 1);

/** Who can be named as a performer: the owner, the doctors of the sample clinic (BS. Mai has no account here). */
export const PERFORMERS: { id: string; name: string }[] = [
  { id: DOCTOR_TAM, name: DOCTOR_NAMES[DOCTOR_TAM] ?? "" },
  { id: DOCTOR_MAI, name: DOCTOR_NAMES[DOCTOR_MAI] ?? "" },
  { id: DOCTOR_AN, name: DOCTOR_NAMES[DOCTOR_AN] ?? "" },
  { id: OWNER_ID, name: USERS.find((u) => u.id === OWNER_ID)?.display_name ?? "" },
];

export const SEED_SIZE = 24;

const month = (day: string): string => day.slice(0, 7);

/** `YYYY-MM` of the month before the one `day` is in. */
export function previousMonthOf(day: string): string {
  const [year, mon] = day.split("-").map(Number);
  const y = mon === 1 ? (year ?? 0) - 1 : (year ?? 0);
  const m = mon === 1 ? 12 : (mon ?? 1) - 1;
  return `${y}-${String(m).padStart(2, "0")}`;
}

/** An invoice number the way the backend writes it: `FIN-HD-<yymm>-<running number>`. */
let invoiceCounter = 0;
export function nextInvoiceNumber(day: string): string {
  invoiceCounter += 1;
  return `HD-${day.slice(2, 4)}${day.slice(5, 7)}-${String(invoiceCounter).padStart(4, "0")}`;
}

export const entries: EntryRecord[] = [];
export const invoices: InvoiceRecord[] = [];
export const payments: PaymentRecord[] = [];
export const notifications: NotificationRecord[] = [];
export const periods: PeriodRecord[] = [];

function seed(): void {
  const today = clinicToday();
  const prev = previousMonthOf(today);
  Array.from({ length: SEED_SIZE }, (_, i) => i).forEach((i) => {
    const service = services[i % services.length];
    const terms = service?.history.find((h) => h.version_no === service.terms_version);
    if (!service || !terms) return;
    const stamp = `${i < 12 ? prev : month(today)}-${String((i % 12) + 1).padStart(2, "0")}`;
    const day = stamp > today ? today : stamp;
    const discount = i % 4 === 2 ? 100_000 : 0;
    const net = terms.price_vnd - discount;
    const received = i % 3 === 0 ? Math.floor(net / 2) : net;
    const patient = patientRef((i % 10) + 1);
    const invoice: InvoiceRecord = {
      id: uuid(100 + i, 51),
      number: nextInvoiceNumber(day),
      patient_id: patient.id,
      source: "finance",
      order_id: null,
      invoice_date: day,
      amount_vnd: net,
      received_vnd: received,
    };
    invoices.push(invoice);
    const performer = PERFORMERS[i % PERFORMERS.length];
    entries.push({
      id: uuid(100 + i, 52),
      patient_id: patient.id,
      service_id: service.id,
      service_name: service.name,
      terms_version: terms.version_no,
      basis: i === 13 ? "collected" : terms.basis,
      entry_date: day,
      invoice_id: invoice.id,
      owns_invoice: true,
      list_vnd: terms.price_vnd,
      discount_vnd: discount,
      net_vnd: net,
      status: i >= 12 && i % 3 === 0 ? "pending" : "approved",
      note: "Lượt hoàn tất minh họa",
      void_reason: null,
      people: [
        { doctor_id: performer?.id ?? DOCTOR_TAM, share_bp: 10_000, rate_bp: terms.rate_bp },
      ],
      version: 1,
    });
    payments.push({
      id: uuid(100 + i, 53),
      key: `SEED-${i}`,
      invoice_id: invoice.id,
      patient_id: patient.id,
      amount_vnd: received,
      method: i % 2 === 0 ? "cash" : "transfer",
      paid_on: day,
      created_at: isoFromNow(-(SEED_SIZE - i) * DAY),
    });
  });
  const lastTwo = payments.slice(-2);
  lastTwo.forEach((payment, index) => {
    const patient = patientById(payment.patient_id);
    notifications.push({
      id: uuid(200 + index, 54),
      payment_id: payment.id,
      invoice_id: payment.invoice_id,
      title: "Đã nhận thanh toán",
      body: `${patient?.code ?? ""} · ${formatDots(payment.amount_vnd)} đ · ${payment.method === "cash" ? "Tiền mặt" : "Chuyển khoản"}`,
      amount_vnd: payment.amount_vnd,
      created_at: isoFromNow(-(index + 1) * DAY),
      read: index === 1,
    });
  });
}

/** Two closed months and a paid one before them, so the states of a frozen table can be looked at. */
function seedOlderMonths(): void {
  const today = clinicToday();
  const lookups = {
    invoice: (id: string) => invoices.find((i) => i.id === id) as InvoiceRecord,
    patientCode: (patientId: string) => patientById(patientId)?.code ?? "",
    doctorName: (doctorId: string) => PERFORMERS.find((p) => p.id === doctorId)?.name ?? "",
  };
  const older: { ago: number; status: "closed" | "paid" }[] = [
    { ago: 2, status: "closed" },
    { ago: 3, status: "paid" },
  ];
  older.forEach(({ ago, status }, k) => {
    const month = Array.from({ length: ago }).reduce<string>(
      (m) => previousMonthOf(`${m}-01`),
      today.slice(0, 7),
    );
    const mine = Array.from({ length: 3 }, (_, j): EntryRecord | null => {
      const service = services[(j + k) % services.length];
      const terms = service?.history.find((h) => h.version_no === service.terms_version);
      if (!service || !terms) return null;
      const day = `${month}-${String(8 + j * 4).padStart(2, "0")}`;
      const patient = patientRef(((j + 3 * k) % 10) + 1);
      const invoice: InvoiceRecord = {
        id: uuid(300 + k * 10 + j, 51),
        number: nextInvoiceNumber(day),
        patient_id: patient.id,
        source: "finance",
        order_id: null,
        invoice_date: day,
        amount_vnd: terms.price_vnd,
        received_vnd: terms.price_vnd,
      };
      invoices.push(invoice);
      payments.push({
        id: uuid(300 + k * 10 + j, 53),
        key: `SEED-OLD-${k}-${j}`,
        invoice_id: invoice.id,
        patient_id: patient.id,
        amount_vnd: terms.price_vnd,
        method: j % 2 === 0 ? "transfer" : "cash",
        paid_on: day,
        created_at: isoFromNow(-(ago * 30 - j) * DAY),
      });
      return {
        id: uuid(300 + k * 10 + j, 52),
        patient_id: patient.id,
        service_id: service.id,
        service_name: service.name,
        terms_version: terms.version_no,
        basis: terms.basis,
        entry_date: day,
        invoice_id: invoice.id,
        owns_invoice: true,
        list_vnd: terms.price_vnd,
        discount_vnd: 0,
        net_vnd: terms.price_vnd,
        status: "approved",
        note: "Lượt hoàn tất minh họa",
        void_reason: null,
        people: [
          {
            doctor_id: PERFORMERS[(j + k) % PERFORMERS.length]?.id ?? DOCTOR_TAM,
            share_bp: 10_000,
            rate_bp: terms.rate_bp,
          },
        ],
        version: 1,
      };
    }).filter((e): e is EntryRecord => e !== null);
    entries.push(...mine);
    periods.push({
      month,
      status,
      closed_at: isoFromNow(-(ago * 30 - 20) * DAY),
      paid_at: status === "paid" ? isoFromNow(-(ago * 30 - 24) * DAY) : null,
      reference: status === "paid" ? "PC-0001 (mẫu)" : null,
      rows: rowsFor(mine, lookups),
    });
  });
}

/** `1.200.000`, the way the backend writes an amount in a notification. */
export function formatDots(amount: number): string {
  return String(amount).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

/** The total of a quick order: every line counts, also "Không in" (it is still billed). */
export function orderTotal(order: (typeof orders)[number]): number {
  return order.items.reduce((sum, x) => sum + x.quantity * x.unit_price_vnd, 0);
}

/** The invoice raised for a quick order, once. */
export function invoiceOfOrder(orderId: string): InvoiceRecord | undefined {
  return invoices.find((i) => i.order_id === orderId);
}

/** A draft order that is edited keeps its invoice in step while nothing is received (backend `sync_order_invoice`). */
export function syncOrderInvoice(order: (typeof orders)[number]): void {
  const invoice = invoiceOfOrder(order.id);
  if (invoice && invoice.received_vnd === 0) invoice.amount_vnd = orderTotal(order);
}

seed();
seedOlderMonths();
