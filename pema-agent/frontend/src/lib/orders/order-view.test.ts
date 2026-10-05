// Pure rules of the cashier screens: the draft being typed (merging a product, the total that still counts a line
// that is not printed, the old form's sentences), the wording of the lists and the review page, and who sees the
// approve button. The rules themselves are the backend's (`backend/apps/api/tests/clinic/test_orders_api.py`).
import { describe, expect, it } from "vitest";

import type { Schemas } from "@/lib/api";
import { ApiError } from "@/lib/api/client";

import {
  addProduct,
  ageGender,
  asRoute,
  catalogLine,
  draftFromOrder,
  draftTotal,
  emptyDraft,
  excludedNote,
  formatVnd,
  historyLine,
  lineFromProduct,
  orderErrorMessage,
  orderStale,
  parseDraft,
  patchLine,
  productLine,
  removeLine,
  reviewStatusLine,
  showApprove,
  unresolvedNote,
  type OrderPrint,
  type OrderRow,
  type ProductRow,
} from "./order-view";

const H002: ProductRow = {
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
const H005: ProductRow = {
  ...H002,
  code: "H005",
  name: "Cicaderm Cream 40ml",
  unit: "Hộp",
  source_type: "Mỹ Phẩm",
  route: "CONSULTATION",
  price_vnd: 715_000,
};
const H095: ProductRow = {
  ...H002,
  code: "H095",
  name: "Triluma Ấn 15g",
  unit: "Tuýp",
  source_type: "",
  route: "UNRESOLVED",
  price_vnd: 500_000,
};

function order(overrides: Partial<OrderRow> = {}): OrderRow {
  return {
    id: "o-1",
    patient_id: "p-1",
    patient_code: "P001",
    patient_name: "Nguyễn Thu Hà",
    doctor_id: "d-1",
    doctor_name: "BS. Lê Minh Tâm",
    status: "draft",
    order_date: "2026-09-20",
    item_count: 2,
    total_vnd: 720_500,
    reviewed_by_name: null,
    reviewed_at: null,
    created_at: "2026-09-20T09:00:00+07:00",
    version: 1,
    diagnosis: "Nám",
    note: "",
    items: [],
    received_vnd: 0,
    paid: false,
    invoice_id: null,
    editable: true,
    unresolved_count: 0,
    ready_to_approve: true,
    ...overrides,
  };
}

describe("the draft being typed", () => {
  it("adds_a_product_once_and_raises_the_quantity_when_it_is_added_again", () => {
    const once = addProduct([], H002);
    const twice = addProduct(once, H002);
    expect(twice).toHaveLength(1);
    expect(twice[0]?.quantity).toBe("2");
    expect(addProduct(twice, H005).map((l) => l.code)).toEqual(["H002", "H005"]);
  });

  it("starts_a_line_with_the_catalog_sheet_and_price", () => {
    expect(lineFromProduct(H095)).toMatchObject({
      route: "UNRESOLVED",
      catalogRoute: "UNRESOLVED",
      unitPrice: 500_000,
      quantity: "1",
      usage: "",
    });
  });

  it("removes_a_line_and_patches_one_without_touching_the_others", () => {
    const lines = addProduct(addProduct([], H002), H005);
    expect(removeLine(lines, 0).map((l) => l.code)).toEqual(["H005"]);
    const patched = patchLine(lines, 1, { usage: "Sáng và tối" });
    expect(patched[1]?.usage).toBe("Sáng và tối");
    expect(patched[0]?.usage).toBe("");
    expect(lines[1]?.usage).toBe("");
  });

  it("totals_every_line_also_one_that_is_not_printed", () => {
    const lines = patchLine(
      patchLine(addProduct(addProduct([], H002), H005), 0, { quantity: "3" }),
      1,
      { route: "NONE" },
    );
    expect(draftTotal(lines)).toBe(3 * 5500 + 715_000);
    expect(draftTotal(patchLine(lines, 0, { quantity: "" }))).toBe(715_000);
  });
});

describe("the checks of the old form", () => {
  const base = (lines = addProduct([], H002)) => ({ ...emptyDraft("p-1", "d-1"), lines });

  it("asks_for_at_least_one_product", () => {
    expect(parseDraft(base([]))).toEqual({ ok: false, problem: "Chọn ít nhất một sản phẩm." });
  });

  it.each(["", "0", "1.5", "10000", "abc"])("refuses_the_quantity_%s", (quantity) => {
    const result = parseDraft(base(patchLine(addProduct([], H002), 0, { quantity })));
    expect(result).toEqual({
      ok: false,
      problem: "Dòng 1: số lượng phải là số nguyên từ 1 đến 9999.",
    });
  });

  it("asks_for_a_reason_when_the_sheet_differs_from_the_catalog", () => {
    const lines = patchLine(addProduct(addProduct([], H002), H095), 1, { route: "CONSULTATION" });
    expect(parseDraft(base(lines))).toEqual({
      ok: false,
      problem: "Dòng 2: ghi lý do thay đổi phân loại.",
    });
    const reasoned = patchLine(lines, 1, { routeReason: " Phân loại thủ công " });
    const parsed = parseDraft(base(reasoned));
    expect(parsed.ok && parsed.items[1]).toMatchObject({
      product_code: "H095",
      route: "CONSULTATION",
      route_reason: "Phân loại thủ công",
    });
  });

  it("sends_trimmed_text_and_a_number_not_a_string", () => {
    const lines = patchLine(addProduct([], H002), 0, {
      quantity: "3",
      usage: "  Uống sau ăn  ",
      note: " ghi chú ",
    });
    const parsed = parseDraft(base(lines));
    expect(parsed).toEqual({
      ok: true,
      items: [
        {
          product_code: "H002",
          quantity: 3,
          route: "PRESCRIPTION",
          route_reason: "",
          usage: "Uống sau ăn",
          note: "ghi chú",
        },
      ],
    });
  });

  it("opens_a_saved_draft_with_every_field_kept", () => {
    const saved = order({
      diagnosis: "Nám",
      note: "Tránh nắng",
      items: [
        {
          line_no: 1,
          product_code: "H002",
          name: "Desloratadine 5 mg",
          source_type: "Thuốc",
          unit: "Viên",
          catalog_route: "PRESCRIPTION",
          route: "NONE",
          route_reason: "Đã cấp riêng",
          quantity: 3,
          unit_price_vnd: 5500,
          usage: "Uống",
          note: "n",
        },
      ],
    });
    const draft = draftFromOrder(saved);
    expect(draft.lines[0]).toMatchObject({
      quantity: "3",
      route: "NONE",
      catalogRoute: "PRESCRIPTION",
      routeReason: "Đã cấp riêng",
      unitPrice: 5500,
    });
    expect(draft.diagnosis).toBe("Nám");
  });
});

describe("wording", () => {
  it("writes_money_and_the_catalog_line_as_the_old_web_did", () => {
    expect(formatVnd(2_808_000)).toBe("2.808.000 ₫");
    expect(
      catalogLine({
        total: 115,
        prescription: 30,
        consultation: 78,
        unresolved: 7,
        source_name: null,
        sha256: null,
      }),
    ).toBe("115 sản phẩm · 30 thuốc · 78 sản phẩm tư vấn · 7 cần phân loại");
  });

  it("says_which_sheet_a_product_goes_to_and_names_a_missing_type", () => {
    expect(productLine(H002)).toBe("H002 · Viên · Thuốc · Đơn thuốc");
    expect(productLine(H095)).toBe("H095 · Tuýp · Chưa có loại · Cần phân loại");
  });

  it("describes_a_history_row_and_the_review_header", () => {
    expect(historyLine(order())).toBe("20/09/2026 · 2 sản phẩm · Bản nháp");
    expect(reviewStatusLine(order({ items: [] }))).toBe(
      "Bản nháp · Bác sĩ phụ trách: BS. Lê Minh Tâm · A5 dọc 148 × 210 mm · 0 sản phẩm",
    );
    expect(
      reviewStatusLine(order({ status: "approved", reviewed_by_name: "BS. Lê Minh Tâm" })),
    ).toContain("Đã duyệt bởi BS. Lê Minh Tâm");
  });

  it("falls_back_to_the_doctor_when_nobody_signed_yet_and_reads_the_route_labels", () => {
    expect(asRoute("NONE")).toBe("NONE");
    expect(asRoute("anything else")).toBe("UNRESOLVED");
  });

  it("formats_age_and_gender_for_the_patient_block", () => {
    expect(ageGender({ code: "P1", full_name: "A", age: 28, gender: "female" })).toBe("28 · Nữ");
    expect(ageGender({ code: "P1", full_name: "A", age: null, gender: "unknown" })).toBe("-");
  });

  it("lists_the_lines_that_need_a_class_and_the_ones_that_are_not_printed", () => {
    const line = (name: string, reason = ""): Schemas["OrderItemOut"] => ({
      line_no: 1,
      product_code: "X",
      name,
      source_type: "",
      unit: "",
      catalog_route: "UNRESOLVED",
      route: "UNRESOLVED",
      route_reason: reason,
      quantity: 1,
      unit_price_vnd: 0,
      usage: "",
      note: "",
    });
    const print = {
      unresolved: [line("Triluma Ấn"), line("Triluma Mỹ")],
      excluded: [line("Fogyma", "Đã cấp riêng")],
    } as unknown as OrderPrint;
    expect(unresolvedNote(print)).toBe(
      "Cần phân loại 2 sản phẩm: Triluma Ấn; Triluma Mỹ. Mở “Sửa nháp” trong hồ sơ hoặc thu ngân để xử lý.",
    );
    expect(excludedNote(print)).toBe(
      "Không in (1): Fogyma — Đã cấp riêng. Vẫn tính trong hóa đơn.",
    );
    expect(unresolvedNote({ ...print, unresolved: [] })).toBeNull();
    expect(excludedNote({ ...print, excluded: [] })).toBeNull();
  });
});

describe("who sees the approve button", () => {
  const doctor = { id: "d-1", role: "doctor" as const };

  it("shows_it_to_the_responsible_doctor_and_the_owner_only", () => {
    expect(showApprove(order(), doctor, true)).toBe(true);
    expect(showApprove(order(), { id: "d-2", role: "doctor" }, true)).toBe(false);
    expect(showApprove(order(), { id: "o-1", role: "owner" }, true)).toBe(true);
  });

  it("hides_it_without_the_permission_or_once_approved", () => {
    expect(showApprove(order(), { id: "r-1", role: "reception" }, false)).toBe(false);
    expect(showApprove(order({ status: "approved" }), doctor, true)).toBe(false);
  });
});

describe("errors", () => {
  it("shows_the_backend_sentence_for_a_rule_and_a_fixed_one_for_the_rest", () => {
    expect(orderErrorMessage(new ApiError(422, "Dòng 1: cần cách dùng trước khi duyệt."))).toBe(
      "Dòng 1: cần cách dùng trước khi duyệt.",
    );
    expect(
      orderErrorMessage(new ApiError(409, "Đơn đã thu tiền; không thể sửa.", "invalid_state")),
    ).toBe("Đơn đã thu tiền; không thể sửa.");
    expect(orderErrorMessage(new ApiError(404, "x"))).toBe("Không tìm thấy đơn.");
    expect(
      orderErrorMessage(
        new ApiError(403, "Bác sĩ duyệt phải là bác sĩ phụ trách đơn.", "forbidden"),
      ),
    ).toBe("Bác sĩ duyệt phải là bác sĩ phụ trách đơn.");
    expect(orderErrorMessage(new Error("boom"))).toBe("Có lỗi xảy ra. Hãy thử lại.");
  });

  it("marks_a_conflict_or_a_missing_order_as_stale", () => {
    expect(orderStale(new ApiError(409, "x", "version_conflict"))).toBe(true);
    expect(orderStale(new ApiError(404, "x"))).toBe(true);
    expect(orderStale(new ApiError(422, "x"))).toBe(false);
  });
});
