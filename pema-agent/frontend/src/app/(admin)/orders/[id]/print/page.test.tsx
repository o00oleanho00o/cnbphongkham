// @vitest-environment jsdom
// The A5 print page (`/orders/[id]/print`): an approved order can be printed (one sheet or both, picked by `?sheet=`),
// a draft carries the draft mark, cannot be printed and says so, and nothing prints by itself. The print stylesheet
// (A5 named page, one sheet per page, a draft prints nothing) is checked on the real page in the visual run
// (`pnpm visual`); here the markup it relies on is pinned. Rules: `backend/apps/api/tests/clinic/test_orders_api.py`.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Schemas } from "@/lib/api";

import OrderPrintRoute from "./page";

const api = vi.hoisted(() => ({ get: vi.fn() }));
const nav = vi.hoisted(() => ({ search: "" }));

vi.mock("@/lib/api/client", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api/client")>();
  return { ...actual, http: { GET: (...args: unknown[]) => api.get(...args) } };
});
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "order-1" }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));

function line(over: Partial<Schemas["OrderItemOut"]>): Schemas["OrderItemOut"] {
  return {
    line_no: 1,
    product_code: "H002",
    name: "Desloratadine 5 mg",
    source_type: "Thuốc",
    unit: "Viên",
    catalog_route: "PRESCRIPTION",
    route: "PRESCRIPTION",
    route_reason: "",
    quantity: 1,
    unit_price_vnd: 5500,
    usage: "Uống sau ăn",
    note: "",
    ...over,
  };
}

function printData(approved: boolean): Schemas["OrderPrintOut"] {
  const rx = line({});
  const advice = line({
    line_no: 2,
    product_code: "H005",
    name: "Cicaderm Cream 40ml",
    route: "CONSULTATION",
    catalog_route: "CONSULTATION",
  });
  return {
    order: {
      id: "order-1",
      patient_id: "p-1",
      patient_code: "P001",
      patient_name: "Nguyễn Thu Hà",
      doctor_id: "d-1",
      doctor_name: "BS. Lê Minh Tâm",
      status: approved ? "approved" : "draft",
      order_date: "2026-09-20",
      item_count: 2,
      total_vnd: 720_500,
      reviewed_by_name: approved ? "BS. Lê Minh Tâm" : null,
      reviewed_at: null,
      created_at: "2026-09-20T09:00:00+07:00",
      version: 2,
      diagnosis: "Nám",
      note: "",
      items: [rx, advice],
      received_vnd: 0,
      paid: false,
      invoice_id: null,
      editable: !approved,
      unresolved_count: 0,
      ready_to_approve: true,
    },
    patient: { code: "P001", full_name: "Nguyễn Thu Hà", age: 28, gender: "female" },
    prescription: [rx],
    consultation: [advice],
    excluded: [],
    unresolved: [],
    printable: approved,
  };
}

function answer(approved: boolean) {
  api.get
    .mockReset()
    .mockImplementation(() =>
      Promise.resolve({ data: printData(approved), response: new Response(null, { status: 200 }) }),
    );
}

beforeEach(() => {
  nav.search = "";
  answer(true);
  vi.spyOn(window, "print").mockImplementation(() => undefined);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("an approved order", () => {
  it("can_be_printed_and_prints_nothing_until_the_button_is_pressed", async () => {
    const user = userEvent.setup();
    const { container } = render(<OrderPrintRoute />);

    const button = await screen.findByRole("button", { name: "In tất cả" });
    expect((button as HTMLButtonElement).disabled).toBe(false);
    expect(window.print).not.toHaveBeenCalled();
    expect(container.querySelector(".order-print-root")?.getAttribute("data-approved")).toBe(
      "true",
    );
    expect(container.querySelectorAll(".order-doc-set")).toHaveLength(2);
    expect(screen.queryByText("BẢN NHÁP — CHỜ BÁC SĨ DUYỆT")).toBeNull();

    await user.click(button);
    await waitFor(() => expect(window.print).toHaveBeenCalledTimes(1));
  });

  it("names_the_sheet_that_the_address_asks_for", async () => {
    nav.search = "sheet=CONSULTATION";
    const { container } = render(<OrderPrintRoute />);

    expect(await screen.findByRole("button", { name: "In phiếu tư vấn" })).toBeTruthy();
    expect(container.querySelector(".order-print-root")?.getAttribute("data-sheet")).toBe(
      "CONSULTATION",
    );
  });

  it("goes_back_to_the_review_of_the_order", async () => {
    render(<OrderPrintRoute />);

    expect((await screen.findByRole("link", { name: "Về tách đơn" })).getAttribute("href")).toBe(
      "/orders/order-1",
    );
  });
});

describe("a draft", () => {
  it("carries_the_draft_mark_cannot_be_printed_and_is_marked_to_print_nothing", async () => {
    answer(false);
    const { container } = render(<OrderPrintRoute />);

    const button = await screen.findByRole("button", { name: "In tất cả" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(container.querySelector(".order-print-root")?.getAttribute("data-approved")).toBe(
      "false",
    );
    expect(screen.getAllByText("BẢN NHÁP — CHỜ BÁC SĨ DUYỆT").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/chưa được bác sĩ duyệt để phát hành/)).toBeTruthy();
    expect(container.querySelector(".order-print-blocked")?.textContent).toContain(
      "Đơn nháp cần bác sĩ duyệt trước khi in.",
    );
  });
});

describe("an order that cannot be opened", () => {
  it("shows_the_sentence_of_the_backend", async () => {
    api.get.mockReset().mockImplementation(() =>
      Promise.resolve({
        error: { error: { code: "not_found", message: "Không tìm thấy dữ liệu." } },
        response: new Response(null, { status: 404 }),
      }),
    );
    render(<OrderPrintRoute />);

    expect((await screen.findByRole("alert")).textContent).toContain("Không tìm thấy dữ liệu.");
  });
});
