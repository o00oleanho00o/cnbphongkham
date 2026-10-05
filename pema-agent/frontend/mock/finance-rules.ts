// The arithmetic of the commission table, shared by the finance mock data (which freezes the older months) and its
// handlers. Same rules as `pema.clinic.finance.domain`: the commission is `(base * rate + 5000) // 10000` (half up,
// on the dong), the revenue of a procedure is split by share with the remainder on the last performer so the rows add
// up to the net price, and the base is the net price, the list price or what the invoice has received so far.
import type { EntryRecord, FrozenRow, InvoiceRecord, PersonRecord } from "./data/finance";

export const money = (base: number, rateBp: number): number =>
  Math.floor((base * rateBp + 5000) / 10_000);

export function baseFor(entry: EntryRecord, invoice: InvoiceRecord): number {
  if (entry.basis === "net") return entry.net_vnd;
  if (entry.basis === "list") return entry.list_vnd;
  return Math.min(
    entry.net_vnd,
    Math.floor((entry.net_vnd * invoice.received_vnd) / Math.max(1, invoice.amount_vnd)),
  );
}

/** The revenue of each performer: net x share, the last one takes the remainder so the rows add up exactly. */
export function revenueSplit(net: number, people: PersonRecord[]): number[] {
  return people.reduce<{ revenue: number[]; allocated: number }>(
    (acc, person, index) => {
      const share =
        index === people.length - 1
          ? net - acc.allocated
          : Math.floor((net * person.share_bp) / 10_000);
      return { revenue: [...acc.revenue, share], allocated: acc.allocated + share };
    },
    { revenue: [], allocated: 0 },
  ).revenue;
}

/** What the table needs to know about the world around an entry. */
export type RowLookups = {
  invoice: (id: string) => InvoiceRecord;
  patientCode: (patientId: string) => string;
  doctorName: (doctorId: string) => string;
};

/** One row per performer of every entry, in the order of the entries. */
export function rowsFor(list: EntryRecord[], lookups: RowLookups): FrozenRow[] {
  return list.flatMap((entry) => {
    const base = baseFor(entry, lookups.invoice(entry.invoice_id));
    const revenue = revenueSplit(entry.net_vnd, entry.people);
    return entry.people.map((person, index) => ({
      entry_id: entry.id,
      date: entry.entry_date,
      patient_code: lookups.patientCode(entry.patient_id),
      service_name: entry.service_name,
      doctor_id: person.doctor_id,
      doctor_name: lookups.doctorName(person.doctor_id),
      status: entry.status,
      basis: entry.basis,
      base_vnd: base,
      rate_bp: person.rate_bp,
      share_bp: person.share_bp,
      revenue_vnd: revenue[index] ?? 0,
      fee_vnd: money(base, person.rate_bp),
      note: entry.status === "void" && entry.void_reason ? entry.void_reason : entry.note,
    }));
  });
}
