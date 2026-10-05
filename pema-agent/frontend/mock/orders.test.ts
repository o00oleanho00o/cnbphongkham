// The cashier routes of the mock behave like backend `pema/clinic/actions/orders.py` and `catalog.py`: the catalog
// is searched without accents, a saved line keeps its snapshot, a draft is edited with the version it was read at,
// only the responsible doctor (or the owner) approves, an approved order never changes, a draft cannot be printed and
// the app preview lists approved orders only. The rules themselves are tested on the real backend
// (`backend/apps/api/tests/clinic/test_orders_api.py`).
import type { Server } from "node:http";
import type { AddressInfo } from "node:net";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { patientRef } from "./data/clinic";
import { orders } from "./data/orders";
import { startMockServer } from "./server";

let server: Server;
let base: string;

beforeAll(async () => {
  server = await startMockServer(0);
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});

afterAll(() => {
  server.close();
});

async function signIn(email: string): Promise<string> {
  const res = await fetch(`${base}/api/v1/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email, password: "demo1234" }),
  });
  expect(res.status).toBe(200);
  return res.headers.get("set-cookie")?.split(";")[0] ?? "";
}

function call(cookie: string, method: string, path: string, body?: unknown): Promise<Response> {
  return fetch(`${base}${path}`, {
    method,
    headers: { "content-type": "application/json", ...(cookie ? { cookie } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

type Order = {
  id: string;
  status: string;
  version: number;
  total_vnd: number;
  unresolved_count: number;
  editable: boolean;
  items: { product_code: string; unit_price_vnd: number; route: string; quantity: number }[];
};

const line = (code: string, over: Record<string, unknown> = {}) => ({
  product_code: code,
  quantity: 1,
  usage: "Dùng theo hướng dẫn (mẫu)",
  ...over,
});

async function draft(
  cookie: string,
  items = [line("H002"), line("H005")],
  over = {},
): Promise<Order> {
  const res = await call(cookie, "POST", "/api/v1/orders", {
    patient_id: patientRef(1).id,
    diagnosis: "Nám (mẫu)",
    items,
    ...over,
  });
  expect(res.status).toBe(201);
  return (await res.json()) as Order;
}

describe("catalog (mock)", () => {
  it("searches_without_accents_and_puts_an_exact_code_first", async () => {
    const reception = await signIn("reception@pema.test");

    const byType = (await (
      await call(reception, "GET", "/api/v1/catalog/products?q=my%20pham")
    ).json()) as {
      items: { code: string }[];
    };
    expect(byType.items.length).toBeGreaterThan(3);
    const exact = (await (
      await call(reception, "GET", "/api/v1/catalog/products?q=h005")
    ).json()) as {
      items: { code: string }[];
    };
    expect(exact.items[0]?.code).toBe("H005");
  });

  it("is_not_for_care_staff", async () => {
    const care = await signIn("cs@pema.test");

    expect((await call(care, "GET", "/api/v1/catalog/summary")).status).toBe(403);
    expect((await call(care, "GET", "/api/v1/orders")).status).toBe(403);
  });
});

describe("drafts (mock)", () => {
  it("snapshots_name_and_price_and_totals_every_line", async () => {
    const reception = await signIn("reception@pema.test");

    const order = await draft(reception, [line("H002", { quantity: 3 }), line("H005")]);

    expect(order.version).toBe(1);
    expect(order.total_vnd).toBe(3 * 5500 + 715_000);
    expect(order.items[0]?.unit_price_vnd).toBe(5500);
  });

  it("asks_for_a_reason_when_a_sheet_is_changed_and_refuses_an_unknown_product", async () => {
    const reception = await signIn("reception@pema.test");
    const common = { patient_id: patientRef(1).id, diagnosis: "x" };

    const noReason = await call(reception, "POST", "/api/v1/orders", {
      ...common,
      items: [line("H095", { route: "CONSULTATION" })],
    });
    const unknown = await call(reception, "POST", "/api/v1/orders", {
      ...common,
      items: [line("ZZZ")],
    });

    expect(noReason.status).toBe(422);
    expect(((await noReason.json()) as { error: { message: string } }).error.message).toBe(
      "Dòng 1: ghi lý do thay đổi phân loại.",
    );
    expect(unknown.status).toBe(422);
  });

  it("refuses_a_stale_edit_and_counts_every_save_as_a_version", async () => {
    const reception = await signIn("reception@pema.test");
    const order = await draft(reception);
    const body = {
      version: order.version,
      diagnosis: "Đã sửa",
      items: [line("H002", { quantity: 2 })],
    };

    const saved = await call(reception, "PUT", `/api/v1/orders/${order.id}`, body);
    const again = await call(reception, "PUT", `/api/v1/orders/${order.id}`, body);

    expect(((await saved.json()) as Order).version).toBe(2);
    expect(again.status).toBe(409);
  });

  it("refuses_an_edit_when_money_was_received", async () => {
    const reception = await signIn("reception@pema.test");
    const order = await draft(reception);
    const row = orders.find((o) => o.id === order.id);
    if (row) row.received_vnd = 1000;

    const res = await call(reception, "PUT", `/api/v1/orders/${order.id}`, {
      version: order.version,
      diagnosis: "x",
      items: [line("H002")],
    });

    expect(res.status).toBe(409);
    expect(((await res.json()) as { error: { message: string } }).error.message).toBe(
      "Đơn đã thu tiền; không thể sửa.",
    );
  });
});

describe("approval (mock)", () => {
  it("is_for_the_responsible_doctor_with_the_version_that_was_read", async () => {
    const reception = await signIn("reception@pema.test");
    const order = await draft(reception, [line("H002")], {
      doctor_id: "00000000-0000-4000-8001-000000000003",
    });
    const url = `/api/v1/orders/${order.id}/approve`;

    expect((await call(reception, "POST", url, { version: order.version })).status).toBe(403);
    const other = await signIn("bsan@pema.test");
    expect((await call(other, "POST", url, { version: order.version })).status).toBe(403);
    const doctor = await signIn("doctor@pema.test");
    expect((await call(doctor, "POST", url, { version: 99 })).status).toBe(409);
    const approved = await call(doctor, "POST", url, { version: order.version });

    expect(approved.status).toBe(200);
    expect(((await approved.json()) as Order).status).toBe("approved");
  });

  it("needs_every_line_classified_and_a_usage_on_every_printed_line", async () => {
    const reception = await signIn("reception@pema.test");
    const doctor = await signIn("doctor@pema.test");
    const doctorId = "00000000-0000-4000-8001-000000000003";
    const unresolved = await draft(reception, [line("H095")], { doctor_id: doctorId });
    const noUsage = await draft(reception, [line("H002", { usage: "" })], { doctor_id: doctorId });

    const first = await call(doctor, "POST", `/api/v1/orders/${unresolved.id}/approve`, {
      version: 1,
    });
    const second = await call(doctor, "POST", `/api/v1/orders/${noUsage.id}/approve`, {
      version: 1,
    });

    expect(((await first.json()) as { error: { message: string } }).error.message).toBe(
      "Dòng 1: cần phân loại trước khi duyệt hoặc in.",
    );
    expect(((await second.json()) as { error: { message: string } }).error.message).toBe(
      "Dòng 1: cần cách dùng trước khi duyệt.",
    );
  });

  it("makes_the_order_immutable_printable_and_visible_in_the_app_preview", async () => {
    const reception = await signIn("reception@pema.test");
    const doctor = await signIn("doctor@pema.test");
    const order = await draft(reception, [line("H002"), line("H005")], {
      doctor_id: "00000000-0000-4000-8001-000000000003",
    });
    const strict = `/api/v1/orders/${order.id}/print-data?require_approved=true`;
    expect((await call(reception, "GET", strict)).status).toBe(409);

    await call(doctor, "POST", `/api/v1/orders/${order.id}/approve`, { version: order.version });

    const edit = await call(reception, "PUT", `/api/v1/orders/${order.id}`, {
      version: 2,
      diagnosis: "x",
      items: [line("H002")],
    });
    expect(edit.status).toBe(409);
    const print = (await (await call(reception, "GET", strict)).json()) as {
      printable: boolean;
      prescription: unknown[];
      consultation: unknown[];
    };
    expect(print.printable).toBe(true);
    expect([print.prescription.length, print.consultation.length]).toEqual([1, 1]);
    const preview = (await (
      await call(doctor, "GET", `/api/v1/patients/${patientRef(1).id}/approved-orders`)
    ).json()) as { order_id: string }[];
    expect(preview.some((g) => g.order_id === order.id)).toBe(true);
  });
});
