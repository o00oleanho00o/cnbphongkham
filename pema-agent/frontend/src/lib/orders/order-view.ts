// Pure rules of the cashier screens (`/cashier`, `/orders/[id]`, `/orders/[id]/print`; package U, step U5).
// The backend owns every rule (catalog snapshot, version, who approves, immutability, what prints); this file words
// things for the screen and checks a draft BEFORE it is sent with the same sentences the old web gave
// (`order-data.js` `validateItems`, `saveOrder`), so a mistake is told in place and the BE answer stays the last word.
// Money is whole VND, a quantity a whole number from 1 to 9999.
import type { Schemas } from "@/lib/api";
import { ApiError } from "@/lib/api/client";
import { formatDate } from "@/lib/ops/format";

export type OrderRoute = Schemas["OrderRoute"];
export type ProductRow = Schemas["ProductOut"];
export type CatalogSummary = Schemas["CatalogSummaryOut"];
export type OrderSummary = Schemas["OrderSummaryOut"];
export type OrderRow = Schemas["OrderOut"];
export type OrderItemRow = Schemas["OrderItemOut"];
export type OrderPrint = Schemas["OrderPrintOut"];
export type ApprovedGroup = Schemas["ApprovedOrderGroupOut"];
export type OrderItemBody = Schemas["OrderItemIn"];

// ---------------------------------------------------------------------------------------------------- routes
export const ROUTES: readonly OrderRoute[] = ["PRESCRIPTION", "CONSULTATION", "NONE", "UNRESOLVED"];

/** Labels of the old web (`order-ui.js` `labels`). */
export const ROUTE_LABEL: Record<OrderRoute, string> = {
  PRESCRIPTION: "Đơn thuốc",
  CONSULTATION: "Phiếu tư vấn",
  NONE: "Không in",
  UNRESOLVED: "Cần phân loại",
};

/** The route a `<select>` value stands for; the value always comes from `ROUTES`, `UNRESOLVED` is the fallback. */
export function asRoute(value: string): OrderRoute {
  return ROUTES.find((route) => route === value) ?? "UNRESOLVED";
}

export const QUANTITY_BOUNDS = { min: 1, max: 9999 } as const;
export const A5_NOTE = "A5 dọc 148 × 210 mm";
export const DRAFT_MARK = "BẢN NHÁP — CHỜ BÁC SĨ DUYỆT";

// ------------------------------------------------------------------------------------------------- the draft
/** One line of the order being typed. The quantity stays text while it is edited. */
export type DraftLine = {
  code: string;
  name: string;
  unit: string;
  unitPrice: number;
  catalogRoute: OrderRoute;
  route: OrderRoute;
  quantity: string;
  usage: string;
  note: string;
  routeReason: string;
};

export type DraftOrder = {
  patientId: string;
  doctorId: string;
  diagnosis: string;
  note: string;
  lines: DraftLine[];
};

export function lineFromProduct(product: ProductRow): DraftLine {
  return {
    code: product.code,
    name: product.name,
    unit: product.unit,
    unitPrice: product.price_vnd,
    catalogRoute: product.route,
    route: product.route,
    quantity: "1",
    usage: "",
    note: "",
    routeReason: "",
  };
}

export function lineFromItem(item: OrderItemRow): DraftLine {
  return {
    code: item.product_code,
    name: item.name,
    unit: item.unit,
    unitPrice: item.unit_price_vnd,
    catalogRoute: item.catalog_route,
    route: item.route,
    quantity: String(item.quantity),
    usage: item.usage,
    note: item.note,
    routeReason: item.route_reason,
  };
}

/** Adding a product that is already in the order raises its quantity ("Thêm cùng mã tăng số lượng"). */
export function addProduct(lines: readonly DraftLine[], product: ProductRow): DraftLine[] {
  const at = lines.findIndex((line) => line.code === product.code);
  if (at < 0) return [...lines, lineFromProduct(product)];
  return lines.map((line, index) =>
    index === at ? { ...line, quantity: String((Number(line.quantity) || 0) + 1) } : line,
  );
}

export function removeLine(lines: readonly DraftLine[], index: number): DraftLine[] {
  return lines.filter((_line, i) => i !== index);
}

export function patchLine(
  lines: readonly DraftLine[],
  index: number,
  patch: Partial<DraftLine>,
): DraftLine[] {
  return lines.map((line, i) => (i === index ? { ...line, ...patch } : line));
}

/** "Tổng tiền dự kiến": every line counts, also "Không in" (it is still billed). */
export function draftTotal(lines: readonly DraftLine[]): number {
  return lines.reduce((sum, line) => sum + (Number(line.quantity) || 0) * line.unitPrice, 0);
}

export type ParsedDraft = { ok: true; items: OrderItemBody[] } | { ok: false; problem: string };

function lineProblem(line: DraftLine, index: number): string | null {
  const quantity = Number(line.quantity);
  const validQuantity =
    line.quantity.trim() !== "" &&
    Number.isInteger(quantity) &&
    quantity >= QUANTITY_BOUNDS.min &&
    quantity <= QUANTITY_BOUNDS.max;
  if (!validQuantity) {
    return `Dòng ${index + 1}: số lượng phải là số nguyên từ ${QUANTITY_BOUNDS.min} đến ${QUANTITY_BOUNDS.max}.`;
  }
  if (line.route !== line.catalogRoute && line.routeReason.trim() === "") {
    return `Dòng ${index + 1}: ghi lý do thay đổi phân loại.`;
  }
  return null;
}

function itemBody(line: DraftLine): OrderItemBody {
  return {
    product_code: line.code,
    quantity: Number(line.quantity),
    route: line.route,
    route_reason: line.routeReason.trim(),
    usage: line.usage.trim(),
    note: line.note.trim(),
  };
}

/** The checks the old form made before saving; the BE repeats them. */
export function parseDraft(draft: DraftOrder): ParsedDraft {
  if (draft.lines.length === 0) return { ok: false, problem: "Chọn ít nhất một sản phẩm." };
  const problem = draft.lines.map(lineProblem).find((text) => text !== null);
  if (problem) return { ok: false, problem };
  return { ok: true, items: draft.lines.map(itemBody) };
}

export function emptyDraft(patientId = "", doctorId = ""): DraftOrder {
  return { patientId, doctorId, diagnosis: "", note: "", lines: [] };
}

export function draftFromOrder(order: OrderRow): DraftOrder {
  return {
    patientId: order.patient_id,
    doctorId: order.doctor_id,
    diagnosis: order.diagnosis,
    note: order.note,
    lines: order.items.map(lineFromItem),
  };
}

// ----------------------------------------------------------------------------------------------- wording
const VND = new Intl.NumberFormat("vi-VN");

/** "2.500.000 ₫". */
export function formatVnd(amount: number): string {
  return `${VND.format(amount)} ₫`;
}

/** The line above the product list: "115 sản phẩm · 30 thuốc · 78 sản phẩm tư vấn · 7 cần phân loại". */
export function catalogLine(summary: CatalogSummary): string {
  return `${summary.total} sản phẩm · ${summary.prescription} thuốc · ${summary.consultation} sản phẩm tư vấn · ${summary.unresolved} cần phân loại`;
}

/** Under a product: "H002 · Viên · Thuốc · Đơn thuốc" (an empty Excel type reads "Chưa có loại"). */
export function productLine(product: ProductRow): string {
  return `${product.code} · ${product.unit} · ${product.source_type || "Chưa có loại"} · ${ROUTE_LABEL[product.route]}`;
}

export function statusLabel(status: OrderSummary["status"]): string {
  return status === "approved" ? "Đã duyệt" : "Bản nháp";
}

/** "20/09/2026 · 2 sản phẩm · Bản nháp". */
export function historyLine(order: OrderSummary): string {
  return `${formatDate(order.order_date)} · ${order.item_count} sản phẩm · ${statusLabel(order.status)}`;
}

/** Under the title of the review page. */
export function reviewStatusLine(order: OrderRow): string {
  const who =
    order.status === "approved"
      ? `Đã duyệt bởi ${order.reviewed_by_name ?? order.doctor_name}`
      : `Bản nháp · Bác sĩ phụ trách: ${order.doctor_name}`;
  return `${who} · ${A5_NOTE} · ${order.items.length} sản phẩm`;
}

export function sheetTitle(route: "PRESCRIPTION" | "CONSULTATION"): string {
  return route === "CONSULTATION" ? "PHIẾU TƯ VẤN" : "ĐƠN THUỐC";
}

/** "Mang theo đơn này..." differs per sheet, as in the old print. */
export function sheetReminder(route: "PRESCRIPTION" | "CONSULTATION"): string {
  return route === "CONSULTATION"
    ? "Mang theo phiếu này khi tái khám. Kiểm tra sản phẩm trước khi nhận."
    : "Mang theo đơn này khi tái khám. Kiểm tra thuốc trước khi nhận.";
}

export function signerTitle(route: "PRESCRIPTION" | "CONSULTATION"): string {
  return route === "CONSULTATION" ? "Bác sĩ tư vấn" : "Bác sĩ khám";
}

export function genderLabel(gender: OrderPrint["patient"]["gender"]): string {
  return { female: "Nữ", male: "Nam", other: "Khác", unknown: "" }[gender];
}

/** "28 · Nữ", "28", "Nữ" or "-". */
export function ageGender(patient: OrderPrint["patient"]): string {
  const parts = [patient.age === null || patient.age === undefined ? "" : String(patient.age)];
  parts.push(genderLabel(patient.gender));
  return parts.filter(Boolean).join(" · ") || "-";
}

/** The notes under the sheets: lines that need a class and lines that are not printed. */
export function unresolvedNote(print: OrderPrint): string | null {
  if (print.unresolved.length === 0) return null;
  const names = print.unresolved.map((x) => x.name).join("; ");
  return `Cần phân loại ${print.unresolved.length} sản phẩm: ${names}. Mở “Sửa nháp” trong hồ sơ hoặc thu ngân để xử lý.`;
}

export function excludedNote(print: OrderPrint): string | null {
  if (print.excluded.length === 0) return null;
  const names = print.excluded
    .map((x) => (x.route_reason ? `${x.name} — ${x.route_reason}` : x.name))
    .join("; ");
  return `Không in (${print.excluded.length}): ${names}. Vẫn tính trong hóa đơn.`;
}

/** Can this person approve this order on screen? (the BE decides; this only shows the button.) */
export function showApprove(
  order: OrderRow,
  me: { id: string; role: Schemas["Role"] },
  canApprove: boolean,
): boolean {
  if (!canApprove || order.status !== "draft") return false;
  return me.role !== "doctor" || me.id === order.doctor_id;
}

// --------------------------------------------------------------------------------------------------- errors
const FIXED: Record<number, string> = {
  401: "Phiên đăng nhập đã hết. Hãy đăng nhập lại.",
  403: "Bạn không có quyền thực hiện thao tác này.",
  404: "Không tìm thấy đơn.",
  500: "Máy chủ đang gặp lỗi. Hãy thử lại sau.",
};

/** Sentence for a failed call: the BE sentence for a rule (409, 422), a fixed one for the rest. */
export function orderErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "Có lỗi xảy ra. Hãy thử lại.";
  const fixed = FIXED[error.status];
  if (fixed && error.code !== "forbidden") return fixed;
  if (error.status === 403 || error.status === 409 || error.status === 422 || error.status === 0) {
    return error.message;
  }
  return "Có lỗi xảy ra. Hãy thử lại.";
}

/** After these answers the order on screen is out of date: open it again. */
export function orderStale(error: unknown): boolean {
  return error instanceof ApiError && (error.code === "version_conflict" || error.status === 404);
}
