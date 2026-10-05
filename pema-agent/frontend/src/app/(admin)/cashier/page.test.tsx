// @vitest-environment jsdom
// The cashier screen (`/cashier`) against a fake of the typed client: what each role SEES (reception makes and edits
// drafts, a reader only looks), the order dialog (catalog search, a product added once and then counted up, the old
// form's sentences, what is sent to the backend), the edit of a draft with the version that was read, the refusal
// of an order with money received, and the entry from Patient 360 (`?patient=`). The rules are the backend's
// (`backend/apps/api/tests/clinic/test_orders_api.py`).
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import { SessionProvider, type Permission } from "@/lib/session/session-context";

import CashierRoute from "./page";

// The typed HTTP client is the boundary to an unmanaged dependency (the backend API), so it is replaced by a
// fake whose answers each test sets; the screen's own logic runs for real. The address bar and the router are
// replaced too: the search string is what the screen reads, the router is where it goes.
const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }));
const nav = vi.hoisted(() => ({ search: "", push: vi.fn(), replace: vi.fn() }));

vi.mock("@/lib/api/client", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    http: {
      GET: (...args: unknown[]) => api.get(...args),
      POST: (...args: unknown[]) => api.post(...args),
      PUT: (...args: unknown[]) => api.put(...args),
    },
  };
});
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: nav.push, replace: nav.replace }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));

const PATIENT: Schemas["PatientOut"] = {
  id: "patient-1",
  code: "P001",
  full_name: "Nguyễn Thu Hà",
  doctor_id: "doctor-1",
  version: 1,
} as Schemas["PatientOut"];

const H002: Schemas["ProductOut"] = {
  code: "H002",
  name: "Desloratadine 5 mg",
  unit: "Viên",
  source_type: "Thuốc",
  route: "PRESCRIPTION",
  price_vnd: 5500,
  vat: 0.05,
  row_number: 2,
  active: true,
};
const H005: Schemas["ProductOut"] = {
  ...H002,
  code: "H005",
  name: "Cicaderm Cream 40ml",
  unit: "Hộp",
  source_type: "Mỹ Phẩm",
  route: "CONSULTATION",
  price_vnd: 715_000,
};
const H095: Schemas["ProductOut"] = {
  ...H002,
  code: "H095",
  name: "Triluma Ấn 15g",
  unit: "Tuýp",
  source_type: "",
  route: "UNRESOLVED",
  price_vnd: 500_000,
};

const SUMMARY: Schemas["CatalogSummaryOut"] = {
  total: 115,
  prescription: 30,
  consultation: 78,
  unresolved: 7,
  source_name: "danhsach.xlsx",
  sha256: null,
};

function summary(over: Partial<Schemas["OrderSummaryOut"]> = {}): Schemas["OrderSummaryOut"] {
  return {
    id: "order-1",
    patient_id: PATIENT.id,
    patient_code: "P001",
    patient_name: "Nguyễn Thu Hà",
    doctor_id: "doctor-1",
    doctor_name: "BS. Lê Minh Tâm",
    status: "draft",
    order_date: "2026-09-20",
    item_count: 2,
    total_vnd: 720_500,
    created_at: "2026-09-20T09:00:00+07:00",
    version: 2,
    ...over,
  };
}

function full(over: Partial<Schemas["OrderOut"]> = {}): Schemas["OrderOut"] {
  return {
    ...summary(),
    diagnosis: "Nám",
    note: "Tránh nắng",
    items: [
      {
        line_no: 1,
        product_code: "H002",
        name: H002.name,
        source_type: "Thuốc",
        unit: "Viên",
        catalog_route: "PRESCRIPTION",
        route: "PRESCRIPTION",
        route_reason: "",
        quantity: 3,
        unit_price_vnd: 5500,
        usage: "Uống sau ăn",
        note: "",
      },
    ],
    received_vnd: 0,
    paid: false,
    invoice_id: null,
    editable: true,
    unresolved_count: 0,
    ready_to_approve: true,
    ...over,
  };
}

const RESOURCES = {
  day: "2026-09-20",
  doctors: [
    { user_id: "doctor-1", name: "BS. Lê Minh Tâm", active: true },
    { user_id: "doctor-2", name: "BS. Đoàn Thị Mai", active: true },
  ],
  rooms: [],
  blocks: [],
};

function ok<T>(data: T, status = 200) {
  return Promise.resolve({ data, response: new Response(null, { status }) });
}

function refused(status: number, code: string, message: string) {
  return Promise.resolve({
    error: { error: { code, message } },
    response: new Response(null, { status }),
  });
}

function page<T>(items: T[]) {
  return { items, total: items.length, limit: 50, offset: 0 };
}

type Answers = { orders?: Schemas["OrderSummaryOut"][]; order?: Schemas["OrderOut"] };

function answers({ orders = [], order = full() }: Answers = {}) {
  api.get
    .mockReset()
    .mockImplementation(
      (path: string, options?: { params?: { query?: Record<string, unknown> } }) => {
        const query = options?.params?.query ?? {};
        if (path === "/api/v1/catalog/summary") return ok(SUMMARY);
        if (path === "/api/v1/catalog/products") {
          const q = String(query.q ?? "").toLowerCase();
          const all = [H002, H005, H095];
          return ok(
            page(all.filter((p) => q === "" || `${p.code} ${p.name}`.toLowerCase().includes(q))),
          );
        }
        if (path === "/api/v1/orders") {
          const status = query.status as string | undefined;
          const rows = orders.filter((o) => status === undefined || o.status === status);
          return ok({ ...page(rows), limit: Number(query.limit ?? 50) });
        }
        if (path === "/api/v1/orders/{order_id}") return ok(order);
        if (path === "/api/v1/patients") return ok(page([PATIENT]));
        if (path === "/api/v1/patients/{patient_id}") return ok(PATIENT);
        if (path === "/api/v1/resources") return ok(RESOURCES);
        return refused(404, "not_found", "?");
      },
    );
}

const RECEPTION: Permission[] = ["patient.read", "order.read", "order.write"];
const READER: Permission[] = ["order.read"];

function renderPage(permissions: Permission[] = RECEPTION) {
  return render(
    <SessionProvider
      user={{
        id: "u-1",
        clinic_id: "c-1",
        clinic_name: "Phòng khám Pema (dữ liệu mẫu)",
        display_name: "Võ Ngọc Trâm",
        role: "reception",
      }}
      permissions={permissions}
      onLoggedOut={() => undefined}
    >
      <ToastProvider>
        <CashierRoute />
      </ToastProvider>
    </SessionProvider>,
  );
}

function sentBody(mock: typeof api.post | typeof api.put): Record<string, unknown> {
  const options = mock.mock.calls[0]?.[1] as { body: Record<string, unknown> };
  return options.body;
}

async function openDialog(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "Lên đơn nhanh" }));
  return screen.findByRole("dialog");
}

beforeEach(() => {
  nav.search = "";
  nav.push.mockReset();
  nav.replace.mockReset();
  answers();
  api.post.mockReset().mockImplementation(() => ok(full({ id: "order-9", version: 1 }), 201));
  api.put.mockReset().mockImplementation(() => ok(full({ version: 3 })));
});

afterEach(() => cleanup());

describe("what the page shows", () => {
  it("shows_the_tiles_the_banner_and_an_empty_history", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "Thu ngân" })).toBeTruthy();
    expect(screen.getByText("Catalog sản phẩm")).toBeTruthy();
    expect(screen.getByText("115")).toBeTruthy();
    expect(screen.getByText("Từ danhsach.xlsx")).toBeTruthy();
    expect(screen.getByText("Lên đơn theo mẫu PEMA")).toBeTruthy();
    expect(screen.getByText("Chưa có đơn từ catalog.")).toBeTruthy();
    expect(screen.getByText(/Hóa đơn và thu tiền nằm ở bước Tài chính/)).toBeTruthy();
  });

  it("lists_orders_with_view_and_edit_for_a_draft_and_view_only_for_an_approved_one", async () => {
    answers({
      orders: [
        summary(),
        summary({
          id: "order-2",
          patient_name: "Trần Minh Anh",
          status: "approved",
          item_count: 1,
        }),
      ],
    });
    renderPage();

    expect(await screen.findByText("20/09/2026 · 2 sản phẩm · Bản nháp")).toBeTruthy();
    expect(screen.getByText("20/09/2026 · 1 sản phẩm · Đã duyệt")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sửa nháp đơn của Nguyễn Thu Hà" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Sửa nháp đơn của Trần Minh Anh" })).toBeNull();
    const view = screen.getByRole("link", { name: "Xem / in đơn của Trần Minh Anh" });
    expect(view.getAttribute("href")).toBe("/orders/order-2");
  });

  it("gives_a_reader_the_list_without_any_button_that_changes_an_order", async () => {
    answers({ orders: [summary()] });
    renderPage(READER);

    expect(await screen.findByText("20/09/2026 · 2 sản phẩm · Bản nháp")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Lên đơn nhanh" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Sửa nháp/ })).toBeNull();
    expect(screen.getByRole("link", { name: /Xem \/ in đơn/ })).toBeTruthy();
  });
});

describe("making an order", () => {
  it("searches_the_catalog_adds_a_product_once_and_counts_it_up", async () => {
    const user = userEvent.setup();
    renderPage();
    const dialog = await openDialog(user);

    expect(
      await within(dialog).findByText(
        "115 sản phẩm · 30 thuốc · 78 sản phẩm tư vấn · 7 cần phân loại",
      ),
    ).toBeTruthy();
    await user.type(within(dialog).getByLabelText("Tìm mã hoặc tên sản phẩm"), "cica");
    await waitFor(() =>
      expect(within(dialog).queryByRole("button", { name: `Thêm ${H002.name}` })).toBeNull(),
    );
    expect(within(dialog).getByRole("button", { name: `Thêm ${H005.name}` })).toBeTruthy();

    await user.click(within(dialog).getByRole("button", { name: `Thêm ${H005.name}` }));
    await user.click(within(dialog).getByRole("button", { name: `Thêm ${H005.name}` }));
    expect(within(dialog).getAllByLabelText(/^Số lượng/)).toHaveLength(1);
    expect((within(dialog).getByLabelText(/^Số lượng/) as HTMLInputElement).value).toBe("2");
    expect(within(dialog).getByText("1.430.000 ₫")).toBeTruthy();
  });

  it("says_what_is_missing_before_anything_is_sent", async () => {
    const user = userEvent.setup();
    renderPage();
    const dialog = await openDialog(user);

    await user.click(within(dialog).getByRole("button", { name: "Lưu nháp & xem tách đơn" }));
    expect((await within(dialog).findByRole("alert")).textContent).toContain(
      "Chọn ít nhất một sản phẩm.",
    );
    expect(api.post).not.toHaveBeenCalled();

    await user.click(await within(dialog).findByRole("button", { name: `Thêm ${H095.name}` }));
    await user.selectOptions(within(dialog).getByLabelText("Loại phiếu"), "CONSULTATION");
    await user.click(within(dialog).getByRole("button", { name: "Lưu nháp & xem tách đơn" }));
    expect((await within(dialog).findByRole("alert")).textContent).toContain(
      "Dòng 1: ghi lý do thay đổi phân loại.",
    );
    expect(api.post).not.toHaveBeenCalled();
  });

  it("sends_the_lines_with_the_usage_and_opens_the_review_of_the_two_sheets", async () => {
    const user = userEvent.setup();
    renderPage();
    const dialog = await openDialog(user);

    await user.type(within(dialog).getByLabelText("Chẩn đoán / nội dung tư vấn"), "Nám");
    await user.click(await within(dialog).findByRole("button", { name: `Thêm ${H002.name}` }));
    const quantity = within(dialog).getByLabelText(/^Số lượng/);
    await user.clear(quantity);
    await user.type(quantity, "3");
    await user.type(
      within(dialog).getByLabelText("Cách dùng / tần suất / thời gian"),
      "Uống sau ăn",
    );
    await user.click(within(dialog).getByRole("button", { name: "Lưu nháp & xem tách đơn" }));

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    expect(sentBody(api.post)).toEqual({
      patient_id: "patient-1",
      doctor_id: "doctor-1",
      diagnosis: "Nám",
      note: "",
      items: [
        {
          product_code: "H002",
          quantity: 3,
          route: "PRESCRIPTION",
          route_reason: "",
          usage: "Uống sau ăn",
          note: "",
        },
      ],
    });
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/orders/order-9"));
  });

  it("shows_the_backend_sentence_when_it_refuses_the_order", async () => {
    api.post.mockImplementation(() =>
      refused(422, "validation_failed", "Dòng 1: chọn sản phẩm từ catalog."),
    );
    const user = userEvent.setup();
    renderPage();
    const dialog = await openDialog(user);

    await user.click(await within(dialog).findByRole("button", { name: `Thêm ${H002.name}` }));
    await user.click(within(dialog).getByRole("button", { name: "Lưu nháp & xem tách đơn" }));

    expect((await within(dialog).findByRole("alert")).textContent).toContain(
      "Dòng 1: chọn sản phẩm từ catalog.",
    );
    expect(nav.push).not.toHaveBeenCalled();
  });

  it("opens_for_the_patient_of_the_address_when_it_comes_from_patient_360", async () => {
    nav.search = "patient=patient-1";
    renderPage();

    const dialog = await screen.findByRole("dialog");
    await waitFor(() =>
      expect((within(dialog).getByLabelText("Bệnh nhân") as HTMLSelectElement).value).toBe(
        "patient-1",
      ),
    );
    expect((within(dialog).getByLabelText("Bác sĩ phụ trách") as HTMLSelectElement).value).toBe(
      "doctor-1",
    );
  });
});

describe("editing a draft", () => {
  it("opens_the_saved_lines_and_saves_them_with_the_version_that_was_read", async () => {
    answers({ orders: [summary()], order: full({ version: 2 }) });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Sửa nháp đơn của Nguyễn Thu Hà" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Sửa đơn nháp")).toBeTruthy();
    expect((within(dialog).getByLabelText(/^Số lượng/) as HTMLInputElement).value).toBe("3");
    expect((within(dialog).getByLabelText("Bệnh nhân") as HTMLSelectElement).disabled).toBe(true);

    await user.click(within(dialog).getByRole("button", { name: "Lưu nháp & xem tách đơn" }));
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1));
    expect(sentBody(api.put)).toMatchObject({ version: 2, diagnosis: "Nám", note: "Tránh nắng" });
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/orders/order-1"));
  });

  it("refuses_to_open_an_order_that_has_money_received", async () => {
    answers({ orders: [summary()], order: full({ editable: false, received_vnd: 1000 }) });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Sửa nháp đơn của Nguyễn Thu Hà" }));

    expect(await screen.findByText("Đơn đã thu tiền; không thể sửa.")).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("asks_to_reopen_the_order_when_another_window_saved_it_first", async () => {
    api.put.mockImplementation(() =>
      refused(409, "version_conflict", "Đơn đã thay đổi ở cửa sổ khác. Hãy mở lại."),
    );
    answers({ orders: [summary()], order: full({ version: 2 }) });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Sửa nháp đơn của Nguyễn Thu Hà" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Lưu nháp & xem tách đơn" }));

    expect((await within(dialog).findByRole("alert")).textContent).toContain(
      "Đơn đã thay đổi ở cửa sổ khác. Hãy mở lại.",
    );
  });
});
