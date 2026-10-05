// Mock of the cashier screens: the product catalog (`/catalog/products`, `/catalog/summary`) and quick orders
// (`/orders`, `/orders/{id}`, `/orders/{id}/approve`, `/orders/{id}/print-data`, `/patients/{id}/approved-orders`).
// The rules are the backend's (`pema.clinic.actions.orders|catalog`, `pema.clinic.domain.orders`); the mock keeps the
// ones the screens show: the catalog decides name, unit and price (a saved line keeps its own snapshot), a changed
// sheet needs a reason, a draft is edited with the version it was read at and only while nothing is received,
// approval needs every line classified with its usage plus a diagnosis, only the responsible doctor (or the owner)
// approves, an approved order never changes and a draft cannot be printed.
import { USERS } from "../auth";
import { DOCTOR_NAMES, appointments, patientById } from "../data/clinic";
import { invoiceOfOrder, syncOrderInvoice } from "../data/finance";
import { CATALOG_SOURCE, orders, products, type OrderRecord } from "../data/orders";
import {
  bodyOf,
  fail,
  isoFromNow,
  paginate,
  uid,
  type Ctx,
  type Permission,
  type Reply,
  type Router,
  type Schemas,
} from "../core";

type S = Schemas;

const STALE = "Đơn đã thay đổi ở cửa sổ khác. Hãy mở lại.";
const ROUTES = ["PRESCRIPTION", "CONSULTATION", "NONE", "UNRESOLVED"] as const;

function has(ctx: Ctx, permission: Permission): boolean {
  return ctx.session?.permissions.includes(permission) ?? false;
}

function needAny(ctx: Ctx, ...permissions: Permission[]): void {
  if (!permissions.some((p) => has(ctx, p))) {
    fail(403, "forbidden", "Bạn không có quyền thực hiện thao tác này.");
  }
}

function fold(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replaceAll("đ", "d")
    .replaceAll("Đ", "D")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

/** Staff accounts, plus the doctors of the sample patients that have no account in the mock (BS. Mai). */
function nameOf(userId: string | null): string {
  if (userId === null) return "";
  return USERS.find((u) => u.id === userId)?.display_name ?? DOCTOR_NAMES[userId] ?? "";
}

/** A doctor reaches the patients he owns or is scheduled for; the owner of the order always reaches it. */
function canOpen(ctx: Ctx, order: OrderRecord): boolean {
  if (ctx.session?.role !== "doctor") return true;
  if (ctx.session.userId === order.doctor_id) return true;
  const patient = patientById(order.patient_id);
  if (patient?.doctor_id === ctx.session.userId) return true;
  return appointments.some(
    (a) =>
      a.patient_id === order.patient_id &&
      a.doctor_id === ctx.session?.userId &&
      !["cancelled", "missed"].includes(a.status),
  );
}

function orderOr404(ctx: Ctx): OrderRecord {
  const found = orders.find((o) => o.id === ctx.params.order_id);
  if (!found) fail(404, "not_found", "Không tìm thấy dữ liệu trong phòng khám này. (đơn)");
  if (!canOpen(ctx, found)) {
    fail(403, "forbidden", "Hồ sơ này không thuộc bác sĩ phụ trách.");
  }
  return found;
}

function total(order: OrderRecord): number {
  return order.items.reduce((sum, x) => sum + x.quantity * x.unit_price_vnd, 0);
}

function problemWithLines(items: S["OrderItemOut"][]): string | null {
  if (items.length === 0) return "Chọn ít nhất một sản phẩm.";
  const bad = items.findIndex((x) => x.route === "UNRESOLVED");
  if (bad >= 0) return `Dòng ${bad + 1}: cần phân loại trước khi duyệt hoặc in.`;
  const noUsage = items.findIndex((x) => x.route !== "NONE" && x.usage.trim() === "");
  if (noUsage >= 0) return `Dòng ${noUsage + 1}: cần cách dùng trước khi duyệt.`;
  if (items.every((x) => x.route === "NONE")) return "Đơn không có sản phẩm để phát hành.";
  return null;
}

function summaryOf(order: OrderRecord): S["OrderSummaryOut"] {
  const patient = patientById(order.patient_id);
  return {
    id: order.id,
    patient_id: order.patient_id,
    patient_code: patient?.code ?? "",
    patient_name: patient?.full_name ?? "",
    doctor_id: order.doctor_id,
    doctor_name: nameOf(order.doctor_id),
    status: order.status,
    order_date: order.order_date,
    item_count: order.items.length,
    total_vnd: total(order),
    reviewed_by_name: order.reviewed_by ? nameOf(order.reviewed_by) : null,
    reviewed_at: order.reviewed_at,
    created_at: order.created_at,
    version: order.version,
  };
}

function orderOut(order: OrderRecord): S["OrderOut"] {
  return {
    ...summaryOf(order),
    diagnosis: order.diagnosis,
    note: order.note,
    items: order.items,
    received_vnd: order.received_vnd,
    paid: order.paid,
    invoice_id: invoiceOfOrder(order.id)?.id ?? null,
    editable: order.status === "draft" && order.received_vnd === 0 && !order.paid,
    unresolved_count: order.items.filter((x) => x.route === "UNRESOLVED").length,
    ready_to_approve: order.diagnosis.trim() !== "" && problemWithLines(order.items) === null,
  };
}

/** `saveOrder`: the catalog, or the snapshot the draft already holds, decides name, unit, class and price. */
function buildLines(
  inputs: S["OrderItemIn"][],
  previous: S["OrderItemOut"][],
): S["OrderItemOut"][] {
  return inputs.map((input, index) => {
    const code = input.product_code.trim().toUpperCase();
    const before = previous.find((x) => x.product_code === code);
    const catalog = products.find((p) => p.code === code && p.active);
    const source = before ?? catalog;
    if (!source) fail(422, "validation_failed", `Dòng ${index + 1}: chọn sản phẩm từ catalog.`);
    const catalogRoute = before?.catalog_route ?? catalog?.route ?? "UNRESOLVED";
    const route = input.route ?? catalogRoute;
    if (!ROUTES.includes(route)) {
      fail(422, "validation_failed", `Dòng ${index + 1}: phân loại không hợp lệ.`);
    }
    const reason = (input.route_reason ?? "").trim();
    if (route !== catalogRoute && reason === "") {
      fail(422, "validation_failed", `Dòng ${index + 1}: ghi lý do thay đổi phân loại.`);
    }
    return {
      line_no: index + 1,
      product_code: code,
      name: source.name,
      source_type: source.source_type,
      unit: source.unit,
      catalog_route: catalogRoute,
      route,
      route_reason: reason,
      quantity: input.quantity,
      unit_price_vnd: before?.unit_price_vnd ?? catalog?.price_vnd ?? 0,
      usage: (input.usage ?? "").trim(),
      note: (input.note ?? "").trim(),
    };
  });
}

function checkDoctor(doctorId: string | null | undefined): string {
  const account = USERS.find((u) => u.id === doctorId && u.role === "doctor" && u.active);
  const known = doctorId != null && doctorId in DOCTOR_NAMES;
  if (doctorId == null || (!account && !known)) {
    fail(422, "validation_failed", "Chọn bác sĩ trong danh sách.");
  }
  return doctorId;
}

function registerCatalog(r: Router): void {
  r.get("/api/v1/catalog/products", null, (ctx): Reply => {
    needAny(ctx, "order.read", "order.write");
    const q = fold(ctx.query.get("q") ?? "");
    const hits = products
      .filter((p) => p.active)
      .filter((p) => q === "" || [p.code, p.name, p.source_type].some((v) => fold(v).includes(q)))
      .toSorted((a, b) => Number(fold(b.code) === q) - Number(fold(a.code) === q));
    return { body: paginate(hits, ctx.query) };
  });

  r.get("/api/v1/catalog/summary", null, (ctx): Reply => {
    needAny(ctx, "order.read", "order.write");
    const active = products.filter((p) => p.active);
    const count = (route: S["OrderRoute"]) => active.filter((p) => p.route === route).length;
    const body: S["CatalogSummaryOut"] = {
      total: active.length,
      prescription: count("PRESCRIPTION"),
      consultation: count("CONSULTATION"),
      unresolved: count("UNRESOLVED"),
      source_name: CATALOG_SOURCE,
      sha256: "0".repeat(64),
      imported_at: isoFromNow(-86_400_000),
    };
    return { body };
  });
}

function registerOrders(r: Router): void {
  r.get("/api/v1/orders", null, (ctx): Reply => {
    needAny(ctx, "order.read", "order.write");
    const patientId = ctx.query.get("patient_id");
    const status = ctx.query.get("status");
    const rows = orders
      .filter((o) => canOpen(ctx, o))
      .filter((o) => patientId === null || o.patient_id === patientId)
      .filter((o) => status === null || o.status === status)
      .toSorted((a, b) => b.created_at.localeCompare(a.created_at));
    return { body: paginate(rows.map(summaryOf), ctx.query) };
  });

  r.post("/api/v1/orders", "order.write", (ctx): Reply => {
    const input = bodyOf<S["OrderCreate"]>(ctx);
    const patient = patientById(input.patient_id);
    if (!patient)
      fail(404, "not_found", "Không tìm thấy dữ liệu trong phòng khám này. (bệnh nhân)");
    const created: OrderRecord = {
      id: uid("order"),
      patient_id: patient.id,
      doctor_id: checkDoctor(input.doctor_id ?? patient.doctor_id),
      status: "draft",
      order_date: isoFromNow(0).slice(0, 10),
      diagnosis: (input.diagnosis ?? "").trim(),
      note: (input.note ?? "").trim(),
      items: buildLines(input.items, []),
      reviewed_by: null,
      reviewed_at: null,
      received_vnd: 0,
      paid: false,
      created_at: isoFromNow(0),
      version: 1,
    };
    orders.push(created);
    return { status: 201, body: orderOut(created) };
  });

  r.get("/api/v1/orders/{order_id}", null, (ctx): Reply => {
    needAny(ctx, "order.read", "order.write");
    return { body: orderOut(orderOr404(ctx)) };
  });

  r.put("/api/v1/orders/{order_id}", "order.write", (ctx): Reply => {
    const order = orderOr404(ctx);
    const input = bodyOf<S["OrderUpdate"]>(ctx);
    if (order.status !== "draft") {
      fail(409, "invalid_state", "Chỉ được sửa đơn nháp còn tồn tại.");
    }
    if (input.version !== order.version) fail(409, "version_conflict", STALE);
    const items = buildLines(input.items, order.items);
    const doctorId = checkDoctor(input.doctor_id ?? order.doctor_id);
    if (order.received_vnd > 0 || order.paid) {
      fail(409, "invalid_state", "Đơn đã thu tiền; không thể sửa.");
    }
    order.doctor_id = doctorId;
    order.diagnosis = (input.diagnosis ?? "").trim();
    order.note = (input.note ?? "").trim();
    order.items = items;
    order.version += 1;
    syncOrderInvoice(order);
    return { body: orderOut(order) };
  });

  r.post("/api/v1/orders/{order_id}/approve", "order.approve", (ctx): Reply => {
    const order = orderOr404(ctx);
    const input = bodyOf<S["OrderApprove"]>(ctx);
    if (order.status === "approved") return { body: orderOut(order) };
    if (ctx.session?.role === "doctor" && ctx.session.userId !== order.doctor_id) {
      fail(403, "forbidden", "Bác sĩ duyệt phải là bác sĩ phụ trách đơn.");
    }
    if (input.version !== order.version) fail(409, "version_conflict", STALE);
    const problem = problemWithLines(order.items);
    if (problem) fail(422, "validation_failed", problem);
    if (order.diagnosis.trim() === "") {
      fail(422, "validation_failed", "Cần nội dung tư vấn / chẩn đoán trước khi duyệt.");
    }
    order.status = "approved";
    order.reviewed_by = ctx.session?.userId ?? null;
    order.reviewed_at = isoFromNow(0);
    order.version += 1;
    return { body: orderOut(order) };
  });

  r.get("/api/v1/orders/{order_id}/print-data", null, (ctx): Reply => {
    needAny(ctx, "order.read", "order.write");
    const order = orderOr404(ctx);
    const strict = ctx.query.get("require_approved") === "true";
    if (strict) {
      const problem = problemWithLines(order.items);
      if (problem) fail(422, "validation_failed", problem);
      if (order.status !== "approved") {
        fail(409, "invalid_state", "Đơn nháp cần bác sĩ duyệt trước khi in.");
      }
    }
    const patient = patientById(order.patient_id);
    const year = patient?.birth_date ? Number(patient.birth_date.slice(0, 4)) : null;
    const body: S["OrderPrintOut"] = {
      order: orderOut(order),
      patient: {
        code: patient?.code ?? "",
        full_name: patient?.full_name ?? "",
        age: year === null ? null : new Date().getFullYear() - year,
        gender: patient?.gender ?? "unknown",
      },
      prescription: order.items.filter((x) => x.route === "PRESCRIPTION"),
      consultation: order.items.filter((x) => x.route === "CONSULTATION"),
      excluded: order.items.filter((x) => x.route === "NONE"),
      unresolved: order.items.filter((x) => x.route === "UNRESOLVED"),
      printable: order.status === "approved" && problemWithLines(order.items) === null,
    };
    return { body };
  });

  r.get("/api/v1/patients/{patient_id}/approved-orders", null, (ctx): Reply => {
    needAny(ctx, "order.read", "order.write");
    const body: S["ApprovedOrderGroupOut"][] = orders
      .filter((o) => o.patient_id === ctx.params.patient_id && o.status === "approved")
      .filter((o) => canOpen(ctx, o))
      .map((o) => ({
        order_id: o.id,
        order_date: o.order_date,
        doctor_name: nameOf(o.doctor_id),
        diagnosis: o.diagnosis,
        note: o.note,
        prescription: o.items.filter((x) => x.route === "PRESCRIPTION"),
        consultation: o.items.filter((x) => x.route === "CONSULTATION"),
        approved_at: o.reviewed_at,
      }));
    return { body };
  });
}

export function register(r: Router): void {
  registerCatalog(r);
  registerOrders(r);
}
