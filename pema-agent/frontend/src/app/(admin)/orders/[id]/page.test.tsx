// @vitest-environment jsdom
// The review of an order (`/orders/[id]`) against a fake of the typed client: the two A5 sheets with the old
// wording, a draft that cannot be printed, the approve button only for the responsible doctor (or the owner) and
// only when every line is classified, the approval that reloads the order, the sentences for a missing order and for
// a refusal, and text typed as HTML shown as text. The rules are the backend's
// (`backend/apps/api/tests/clinic/test_orders_api.py`).
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import { SessionProvider, type Permission } from "@/lib/session/session-context";

import OrderReviewPage from "./page";

// The typed HTTP client is the boundary to an unmanaged dependency (the backend API), so it is replaced by a
// fake whose answers each test sets; the screen's own logic runs for real.
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
vi.mock("next/navigation", () => ({ useParams: () => ({ id: "order-1" }) }));

type Item = Schemas["OrderItemOut"];

function item(over: Partial<Item> = {}): Item {
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
    usage: "Uống sau ăn\nBuổi tối",
    note: "",
    ...over,
  };
}

function printData(
  over: { order?: Partial<Schemas["OrderOut"]>; items?: Item[]; printable?: boolean } = {},
): Schemas["OrderPrintOut"] {
  const items = over.items ?? [
    item(),
    item({
      line_no: 2,
      product_code: "H005",
      name: "Cicaderm Cream 40ml",
      source_type: "Mỹ Phẩm",
      unit: "Hộp",
      catalog_route: "CONSULTATION",
      route: "CONSULTATION",
      quantity: 1,
      unit_price_vnd: 715_000,
      usage: "Bôi sáng và tối",
      note: "Tránh vùng mắt",
    }),
  ];
  const order: Schemas["OrderOut"] = {
    id: "order-1",
    patient_id: "patient-1",
    patient_code: "P001",
    patient_name: "Nguyễn Thu Hà",
    doctor_id: "doctor-1",
    doctor_name: "BS. Lê Minh Tâm",
    status: "draft",
    order_date: "2026-09-20",
    item_count: items.length,
    total_vnd: 720_500,
    reviewed_by_name: null,
    reviewed_at: null,
    created_at: "2026-09-20T09:00:00+07:00",
    version: 2,
    diagnosis: "Nám · tăng sắc tố",
    note: "Tránh nắng",
    items,
    received_vnd: 0,
    paid: false,
    invoice_id: null,
    editable: true,
    unresolved_count: items.filter((x) => x.route === "UNRESOLVED").length,
    ready_to_approve: true,
    ...over.order,
  };
  return {
    order,
    patient: { code: "P001", full_name: "Nguyễn Thu Hà", age: 28, gender: "female" },
    prescription: items.filter((x) => x.route === "PRESCRIPTION"),
    consultation: items.filter((x) => x.route === "CONSULTATION"),
    excluded: items.filter((x) => x.route === "NONE"),
    unresolved: items.filter((x) => x.route === "UNRESOLVED"),
    printable: over.printable ?? false,
  };
}

function ok<T>(data: T) {
  return Promise.resolve({ data, response: new Response(null, { status: 200 }) });
}

function refused(status: number, code: string, message: string) {
  return Promise.resolve({
    error: { error: { code, message } },
    response: new Response(null, { status }),
  });
}

const DOCTOR: Permission[] = ["order.read", "order.write", "order.approve"];
const RECEPTION: Permission[] = ["order.read", "order.write"];

function renderPage(
  permissions: Permission[] = DOCTOR,
  me: { id: string; role: Schemas["Role"] } = { id: "doctor-1", role: "doctor" },
) {
  return render(
    <SessionProvider
      user={{
        id: me.id,
        clinic_id: "c-1",
        clinic_name: "Phòng khám Pema (dữ liệu mẫu)",
        display_name: "BS. Lê Minh Tâm",
        role: me.role,
      }}
      permissions={permissions}
      onLoggedOut={() => undefined}
    >
      <ToastProvider>
        <OrderReviewPage />
      </ToastProvider>
    </SessionProvider>,
  );
}

beforeEach(() => {
  api.get.mockReset().mockImplementation(() => ok(printData()));
  api.post.mockReset().mockImplementation(() => ok({}));
});

afterEach(() => cleanup());

describe("the two sheets", () => {
  it("draws_the_prescription_and_the_consultation_sheet_with_the_old_wording", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "Tách đơn – Nguyễn Thu Hà" })).toBeTruthy();
    expect(
      screen.getByText(
        "Bản nháp · Bác sĩ phụ trách: BS. Lê Minh Tâm · A5 dọc 148 × 210 mm · 2 sản phẩm",
      ),
    ).toBeTruthy();
    const prescription = screen.getByRole("region", { name: "ĐƠN THUỐC" });
    expect(within(prescription).getByText("Họ tên:")).toBeTruthy();
    expect(within(prescription).getByText("28 · Nữ")).toBeTruthy();
    expect(within(prescription).getByText(/1\. Desloratadine 5 mg/)).toBeTruthy();
    expect(within(prescription).getByText("× 3 Viên")).toBeTruthy();
    expect(within(prescription).getByText("Bác sĩ khám")).toBeTruthy();
    expect(
      within(prescription).getByText(
        "Mang theo đơn này khi tái khám. Kiểm tra thuốc trước khi nhận.",
      ),
    ).toBeTruthy();
    const consultation = screen.getByRole("region", { name: "PHIẾU TƯ VẤN" });
    expect(within(consultation).getByText("Bác sĩ tư vấn")).toBeTruthy();
    expect(within(consultation).getByText("Ghi chú: Tránh vùng mắt")).toBeTruthy();
    expect(within(consultation).getAllByText("BẢN NHÁP — CHỜ BÁC SĨ DUYỆT")).toHaveLength(1);
  });

  it("shows_a_usage_typed_as_html_as_plain_text", async () => {
    const dangerous = '<img src=x onerror="window.injected=true"> & giữ nguyên';
    api.get.mockImplementation(() =>
      ok(
        printData({
          items: [item({ usage: dangerous })],
          order: { diagnosis: "<script>1</script>" },
        }),
      ),
    );
    const { container } = renderPage();

    expect(await screen.findByText(dangerous)).toBeTruthy();
    expect(screen.getByText("<script>1</script>")).toBeTruthy();
    expect(container.querySelector(".order-item-usage img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
  });

  it("lists_the_lines_that_need_a_class_and_the_ones_that_are_not_printed", async () => {
    api.get.mockImplementation(() =>
      ok(
        printData({
          items: [
            item(),
            item({
              line_no: 2,
              name: "Triluma Ấn 15g",
              route: "UNRESOLVED",
              catalog_route: "UNRESOLVED",
            }),
            item({ line_no: 3, name: "Fogyma", route: "NONE", route_reason: "Đã cấp riêng" }),
          ],
        }),
      ),
    );
    renderPage();

    expect(await screen.findByText(/Cần phân loại 1 sản phẩm: Triluma Ấn 15g/)).toBeTruthy();
    expect(
      screen.getByText(/Không in \(1\): Fogyma — Đã cấp riêng\. Vẫn tính trong hóa đơn\./),
    ).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: "Bác sĩ duyệt & gửi app" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });
});

describe("a draft", () => {
  it("cannot_be_printed_and_says_a_doctor_must_approve_first", async () => {
    renderPage(RECEPTION, { id: "reception-1", role: "reception" });

    await screen.findByRole("heading", { name: "Tách đơn – Nguyễn Thu Hà" });
    for (const name of ["In đơn thuốc", "In phiếu tư vấn", "In tất cả"]) {
      expect((screen.getByRole("button", { name }) as HTMLButtonElement).disabled).toBe(true);
    }
    expect(screen.getByText(/Đơn nháp cần bác sĩ duyệt trước khi in/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Bác sĩ duyệt & gửi app" })).toBeNull();
    expect(screen.getByRole("link", { name: "Sửa nháp" }).getAttribute("href")).toBe(
      "/cashier?edit=order-1",
    );
    expect(screen.getByRole("link", { name: "Về thu ngân" }).getAttribute("href")).toBe("/cashier");
  });

  it("is_not_offered_for_approval_to_a_doctor_who_is_not_responsible_for_it", async () => {
    renderPage(DOCTOR, { id: "doctor-2", role: "doctor" });

    await screen.findByRole("heading", { name: "Tách đơn – Nguyễn Thu Hà" });
    expect(screen.queryByRole("button", { name: "Bác sĩ duyệt & gửi app" })).toBeNull();
  });

  it("is_approved_by_the_responsible_doctor_with_the_version_that_was_read_and_then_reloaded", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Bác sĩ duyệt & gửi app" }));

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    const [path, options] = api.post.mock.calls[0] as [string, { params: unknown; body: unknown }];
    expect(path).toBe("/api/v1/orders/{order_id}/approve");
    expect(options.body).toEqual({ version: 2 });
    await waitFor(() => expect(api.get.mock.calls.length).toBeGreaterThan(1));
  });

  it("shows_the_backend_sentence_when_the_approval_is_refused", async () => {
    api.post.mockImplementation(() =>
      refused(422, "validation_failed", "Dòng 1: cần cách dùng trước khi duyệt."),
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Bác sĩ duyệt & gửi app" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Dòng 1: cần cách dùng trước khi duyệt.",
    );
  });
});

describe("an approved order", () => {
  const approved = () =>
    printData({
      printable: true,
      order: {
        status: "approved",
        reviewed_by_name: "BS. Lê Minh Tâm",
        editable: false,
        version: 3,
      },
    });

  it("opens_the_print_page_for_each_sheet_and_no_longer_offers_approval", async () => {
    api.get.mockImplementation(() => ok(approved()));
    renderPage();

    await screen.findByRole("heading", { name: "Tách đơn – Nguyễn Thu Hà" });
    expect(
      screen.getByText("Đã duyệt bởi BS. Lê Minh Tâm · A5 dọc 148 × 210 mm · 2 sản phẩm"),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: "In đơn thuốc" }).getAttribute("href")).toBe(
      "/orders/order-1/print?sheet=PRESCRIPTION",
    );
    expect(screen.getByRole("link", { name: "In phiếu tư vấn" }).getAttribute("href")).toBe(
      "/orders/order-1/print?sheet=CONSULTATION",
    );
    expect(screen.getByRole("link", { name: "In tất cả" }).getAttribute("href")).toBe(
      "/orders/order-1/print?sheet=all",
    );
    expect(screen.queryByRole("button", { name: "Bác sĩ duyệt & gửi app" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Sửa nháp" })).toBeNull();
    expect(screen.queryByText("BẢN NHÁP — CHỜ BÁC SĨ DUYỆT")).toBeNull();
  });

  it("disables_the_button_of_a_sheet_that_has_no_line", async () => {
    api.get.mockImplementation(() =>
      ok({ ...approved(), consultation: [], order: { ...approved().order, items: [item()] } }),
    );
    renderPage();

    await screen.findByRole("heading", { name: "Tách đơn – Nguyễn Thu Hà" });
    expect(
      (screen.getByRole("button", { name: "In phiếu tư vấn" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(screen.getByRole("link", { name: "In đơn thuốc" })).toBeTruthy();
  });
});

describe("an order that cannot be opened", () => {
  it("says_the_order_is_not_found_and_offers_the_way_back", async () => {
    api.get.mockImplementation(() => refused(404, "not_found", "Không tìm thấy dữ liệu."));
    renderPage();

    expect((await screen.findByRole("alert")).textContent).toContain("Không tìm thấy dữ liệu.");
    expect(screen.getByRole("link", { name: "Về thu ngân" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Bác sĩ duyệt & gửi app" })).toBeNull();
  });
});
