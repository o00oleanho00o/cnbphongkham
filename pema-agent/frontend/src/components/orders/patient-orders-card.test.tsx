// @vitest-environment jsdom
// "Đơn thuốc & phiếu tư vấn" in the Kế hoạch tab of Patient 360: the entry to a new draft, the history of the patient,
// and the staff preview of what the app will show (approved orders only, grouped as Đơn thuốc and Phiếu tư vấn).
// The tab itself keeps its own tests (`plan-tab.test.tsx`); the card shows only with an order permission.
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PATIENT_ID, asRole, ok } from "@/components/ops/patient/test-support";
import { PlanTab } from "@/components/ops/patient/plan-tab";
import type { Schemas } from "@/lib/api";

import { PatientOrdersCard } from "./patient-orders-card";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }));

vi.mock("@/lib/api/client", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    http: {
      GET: (...args: unknown[]) => api.get(...args),
      POST: (...args: unknown[]) => api.post(...args),
      PATCH: (...args: unknown[]) => api.patch(...args),
    },
  };
});

function item(over: Partial<Schemas["OrderItemOut"]> = {}): Schemas["OrderItemOut"] {
  return {
    line_no: 1,
    product_code: "H002",
    name: "Desloratadine 5 mg",
    source_type: "Thuốc",
    unit: "Viên",
    catalog_route: "PRESCRIPTION",
    route: "PRESCRIPTION",
    route_reason: "",
    quantity: 3,
    unit_price_vnd: 5500,
    usage: "Uống sau ăn",
    note: "",
    ...over,
  };
}

function summary(over: Partial<Schemas["OrderSummaryOut"]> = {}): Schemas["OrderSummaryOut"] {
  return {
    id: "order-1",
    patient_id: PATIENT_ID,
    patient_code: "P001",
    patient_name: "Nguyễn Thu Hà",
    doctor_id: "d-1",
    doctor_name: "BS. Lê Minh Tâm",
    status: "approved",
    order_date: "2026-09-20",
    item_count: 2,
    total_vnd: 720_500,
    created_at: "2026-09-20T09:00:00+07:00",
    version: 3,
    ...over,
  };
}

const GROUP: Schemas["ApprovedOrderGroupOut"] = {
  order_id: "order-1",
  order_date: "2026-09-20",
  doctor_name: "BS. Lê Minh Tâm",
  diagnosis: "Nám",
  note: "",
  prescription: [item()],
  consultation: [
    item({
      line_no: 2,
      name: "Cicaderm Cream 40ml",
      unit: "Hộp",
      quantity: 1,
      usage: "Bôi sáng tối",
      note: "Tránh vùng mắt",
    }),
  ],
};

function answers(
  orders: Schemas["OrderSummaryOut"][],
  approved: Schemas["ApprovedOrderGroupOut"][],
) {
  api.get.mockReset().mockImplementation((path: string) => {
    if (path === "/api/v1/orders") {
      return ok({ items: orders, total: orders.length, limit: 50, offset: 0 });
    }
    if (path === "/api/v1/patients/{patient_id}/approved-orders") return ok(approved);
    return Promise.resolve({
      error: { error: { code: "not_found", message: "?" } },
      response: new Response(null, { status: 404 }),
    });
  });
}

beforeEach(() => answers([], []));
afterEach(() => cleanup());

describe("the card", () => {
  it("offers_a_new_draft_for_this_patient_to_who_may_write_orders", async () => {
    render(asRole(["order.read", "order.write"], <PatientOrdersCard patientId={PATIENT_ID} />));

    expect(await screen.findByText("Chưa có đơn nào cho bệnh nhân này.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Tạo đơn nháp" }).getAttribute("href")).toBe(
      `/cashier?patient=${PATIENT_ID}`,
    );
  });

  it("only_reads_for_who_may_read_orders", async () => {
    answers([summary()], [GROUP]);
    render(asRole(["order.read"], <PatientOrdersCard patientId={PATIENT_ID} />));

    expect(await screen.findByText("20/09/2026 · 2 sản phẩm · Đã duyệt")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Tạo đơn nháp" })).toBeNull();
    expect(screen.getByRole("link", { name: "Xem / in" }).getAttribute("href")).toBe(
      "/orders/order-1",
    );
  });

  it("previews_the_approved_orders_grouped_as_the_app_will_show_them", async () => {
    answers([summary(), summary({ id: "order-2", status: "draft" })], [GROUP]);
    render(asRole(["order.read"], <PatientOrdersCard patientId={PATIENT_ID} />));

    const preview = await screen.findByRole("region", { name: "Hiển thị trên app" });
    expect(within(preview).getByText("Đơn thuốc")).toBeTruthy();
    expect(within(preview).getByText("Phiếu tư vấn")).toBeTruthy();
    expect(within(preview).getByText(/Desloratadine 5 mg × 3 Viên/)).toBeTruthy();
    expect(within(preview).getByText("Ghi chú: Tránh vùng mắt")).toBeTruthy();
    expect(screen.getAllByText(/Bản nháp/).length).toBeGreaterThan(0);
  });

  it("shows_no_preview_while_nothing_is_approved", async () => {
    answers([summary({ status: "draft" })], []);
    render(asRole(["order.read"], <PatientOrdersCard patientId={PATIENT_ID} />));

    expect(await screen.findByText("20/09/2026 · 2 sản phẩm · Bản nháp")).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Hiển thị trên app" })).toBeNull();
  });
});

describe("the Kế hoạch tab", () => {
  const tab = (permissions: Parameters<typeof asRole>[0]) =>
    asRole(
      permissions,
      <PlanTab
        patientId={PATIENT_ID}
        plans={[]}
        doctorName="BS. Lê Minh Tâm"
        nextVisit={null}
        canWrite={false}
        onChanged={() => undefined}
      />,
    );

  it("shows_the_card_with_an_order_permission", async () => {
    render(tab(["patient.read_360", "order.read"]));

    expect(await screen.findByText("Đơn thuốc & phiếu tư vấn")).toBeTruthy();
  });

  it("does_not_ask_the_backend_for_orders_without_one", () => {
    render(tab(["patient.read_360"]));

    expect(screen.queryByText("Đơn thuốc & phiếu tư vấn")).toBeNull();
    expect(api.get).not.toHaveBeenCalled();
  });
});
