// The mock's accountant (package U, step U11) behaves like the backend role (`pema/clinic/rbac/matrix.py`): the
// session lists the billing side only, the accountant raises a draft order and closes a finance month, and it
// can neither approve an order nor reach the Inbox, the CRM queue or the staff list. The rules themselves are
// tested on the real backend (`backend/apps/api/tests/clinic/test_u11_accountant.py`).
import type { Server } from "node:http";
import type { AddressInfo } from "node:net";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { ROLE_PERMISSIONS, USERS } from "./auth";
import { startMockServer } from "./server";

let server: Server;
let base: string;
let cookie: string;

beforeAll(async () => {
  server = await startMockServer(0);
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  const res = await fetch(`${base}/api/v1/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email: "accountant@pema.test", password: "demo1234" }),
  });
  expect(res.status).toBe(200);
  cookie = res.headers.get("set-cookie")?.split(";")[0] ?? "";
});

afterAll(() => {
  server.close();
});

function call(method: string, path: string, body?: unknown): Promise<Response> {
  return fetch(`${base}${path}`, {
    method,
    headers: { "content-type": "application/json", cookie },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

describe("the accountant account", () => {
  it("is_a_staff_user_with_the_billing_permissions_and_never_order_approve", async () => {
    const me = (await (await call("GET", "/api/v1/me")).json()) as {
      user: { role: string };
      permissions: string[];
    };

    expect(me.user.role).toBe("accountant");
    expect(me.permissions).toEqual(
      expect.arrayContaining(["finance.read", "finance_period.close"]),
    );
    for (const denied of [
      "order.approve",
      "session.write",
      "media.write",
      "admin.users",
      "crm.task.read",
      "conversation.read",
    ]) {
      expect(me.permissions).not.toContain(denied);
    }
    expect(USERS.some((u) => u.role === "accountant")).toBe(true);
    expect(ROLE_PERMISSIONS.accountant).toContain("finance.collect");
  });

  it("is_refused_the_inbox_the_crm_queue_and_the_staff_list", async () => {
    for (const path of ["/api/v1/conversations", "/api/v1/crm/tasks", "/api/v1/admin/users"]) {
      expect((await call("GET", path)).status, path).toBe(403);
    }
  });

  it("reads_the_clinic_finance_and_the_period_list", async () => {
    expect((await call("GET", "/api/v1/finance/periods")).status).toBe(200);
  });
});
