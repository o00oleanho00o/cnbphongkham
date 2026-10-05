// Shared by the tests of the finance screens: fixtures in the shape of the API, the answers of the typed client
// and a render that puts a page inside the session, the toasts and the finance shell's context. Not a test file and
// not part of the app: only the `*.test.tsx` files of the finance screens import it.
import { render } from "@testing-library/react";
import type { ReactElement } from "react";

import { ToastProvider } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import type {
  FinanceEntries,
  FinanceOverview,
  FinancePeriod,
  FinanceRow,
  InvoiceRow,
  PaymentRow,
} from "@/lib/finance/finance-view";
import { SessionProvider, type Permission } from "@/lib/session/session-context";

import { FinanceContext, type FinanceContextValue } from "./finance-context";

export const ok = <T,>(data: T, status = 200) =>
  Promise.resolve({ data, response: new Response(null, { status }) });

export const refused = (status: number, code: string, message: string) =>
  Promise.resolve({
    error: { error: { code, message } },
    response: new Response(null, { status }),
  });

export const pageOf = <T,>(items: T[], total = items.length) => ({
  items,
  total,
  limit: 50,
  offset: 0,
});

export const OPEN: FinancePeriod = { month: "2026-09", status: "open" };
export const CLOSED: FinancePeriod = {
  month: "2026-08",
  status: "closed",
  closed_at: "2026-09-02T09:00:00+07:00",
};
export const PAID: FinancePeriod = {
  month: "2026-07",
  status: "paid",
  closed_at: "2026-08-02T09:00:00+07:00",
  paid_at: "2026-08-05T09:00:00+07:00",
  reference: "PC-0007",
};

export function row(over: Partial<FinanceRow> = {}): FinanceRow {
  return {
    entry_id: "entry-1",
    date: "2026-09-01",
    patient_code: "P001",
    service_name: "Tái khám & đánh giá",
    doctor_id: "doc-1",
    doctor_name: "BS. Lê Minh Tâm",
    status: "pending",
    basis: "net",
    base_vnd: 300_000,
    rate_bp: 1000,
    share_bp: 10_000,
    revenue_vnd: 300_000,
    fee_vnd: 30_000,
    note: "Lượt hoàn tất minh họa",
    ...over,
  };
}

export function entries(over: Partial<FinanceEntries> = {}): FinanceEntries {
  return {
    month: "2026-09",
    today: "2026-09-20",
    scope: "clinic",
    period: OPEN,
    rows: [row(), row({ entry_id: "entry-2", status: "approved", patient_code: "P002" })],
    doctors: [
      { id: "doc-1", name: "BS. Lê Minh Tâm" },
      { id: "doc-2", name: "BS. Trương Hoài An" },
    ],
    can_write: true,
    ...over,
  };
}

export function overview(over: Partial<FinanceOverview> = {}): FinanceOverview {
  return {
    month: "2026-09",
    today: "2026-09-20",
    scope: "clinic",
    period: OPEN,
    summary: {
      revenue_vnd: 13_200_000,
      fee_vnd: 2_187_000,
      pending_vnd: 90_000,
      collected_vnd: 11_000_000,
      debt_vnd: 1_250_000,
    },
    team: [
      {
        doctor_id: "doc-1",
        doctor_name: "BS. Lê Minh Tâm",
        entry_count: 3,
        revenue_vnd: 900_000,
        fee_vnd: 90_000,
      },
      {
        doctor_id: "doc-2",
        doctor_name: "BS. Trương Hoài An",
        entry_count: 3,
        revenue_vnd: 7_200_000,
        fee_vnd: 1_440_000,
      },
    ],
    pending_entries: 2,
    ...over,
  };
}

export function invoice(over: Partial<InvoiceRow> = {}): InvoiceRow {
  return {
    id: "inv-1",
    number: "HD-2609-0001",
    patient_id: "patient-1",
    patient_code: "P001",
    patient_name: "Nguyễn Thu Hà",
    source: "finance",
    order_id: null,
    invoice_date: "2026-09-06",
    amount_vnd: 300_000,
    received_vnd: 150_000,
    due_vnd: 150_000,
    ...over,
  };
}

export function receipt(over: Partial<PaymentRow> = {}): PaymentRow {
  return {
    id: "pay-1",
    key: "key-1",
    invoice_id: "inv-1",
    invoice_number: "HD-2609-0001",
    patient_code: "P001",
    amount_vnd: 150_000,
    method: "cash",
    paid_on: "2026-09-12",
    created_at: "2026-09-12T10:30:00+07:00",
    replayed: false,
    ...over,
  };
}

export function context(over: Partial<FinanceContextValue> = {}): FinanceContextValue {
  return {
    month: "2026-09",
    scope: "clinic",
    canWrite: true,
    canClose: true,
    canCollect: true,
    isOwner: false,
    refreshKey: 0,
    reload: () => undefined,
    ...over,
  };
}

export const ACCOUNTANT: Permission[] = [
  "finance.read",
  "finance.write",
  "finance_period.close",
  "finance.collect",
  "admin.rules",
  "patient.read",
  "appointment.read",
];
export const OWNER: Permission[] = [...ACCOUNTANT, "finance.read_own", "finance.notifications"];
export const DOCTOR: Permission[] = ["finance.read_own", "appointment.read"];

type Role = Schemas["Role"];

/** The page inside the session of `role`, the toasts and the context of the finance shell. */
export function renderFinance(
  ui: ReactElement,
  {
    permissions = ACCOUNTANT,
    role = "manager",
    shell = {},
  }: { permissions?: Permission[]; role?: Role; shell?: Partial<FinanceContextValue> } = {},
) {
  return render(
    <SessionProvider
      user={{
        id: "u-1",
        clinic_id: "c-1",
        clinic_name: "Phòng khám Pema (dữ liệu mẫu)",
        display_name: "Phạm Quốc Việt",
        role,
      }}
      permissions={permissions}
      onLoggedOut={() => undefined}
    >
      <ToastProvider>
        <FinanceContext.Provider value={context(shell)}>{ui}</FinanceContext.Provider>
      </ToastProvider>
    </SessionProvider>,
  );
}
