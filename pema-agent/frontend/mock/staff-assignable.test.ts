// GET /api/v1/staff/assignable in the mock behaves like the real route (backend test
// tests/api/test_staff_assignable_route.py): 401 without a session, 200 for every signed-in role, only
// `{id, name, role}`, active staff of an assignable role (no reception, no locked account), A to Z by name. The
// route that resolves a task refuses the same targets with the one 422 answer (tests/clinic/test_assignee_validation.py).
import type { Server } from "node:http";
import type { AddressInfo } from "node:net";

import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";

import { USERS, resetAttempts } from "./auth";
import { ASSIGNABLE_ROLES } from "./assignable";
import { tasks } from "./data/clinic";
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

beforeEach(resetAttempts);

type Row = { id: string; name: string; role: string };

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

async function assignable(cookie: string): Promise<Row[]> {
  const res = await call(cookie, "GET", "/api/v1/staff/assignable");
  expect(res.status).toBe(200);
  return (await res.json()) as Row[];
}

describe("GET /api/v1/staff/assignable (mock)", () => {
  it("answers 401 without a session", async () => {
    const res = await call("", "GET", "/api/v1/staff/assignable");
    expect(res.status).toBe(401);
  });

  it("answers every signed-in role, with the same list", async () => {
    const owner = await assignable(await signIn("owner@pema.test"));
    const cs = await assignable(await signIn("cs@pema.test"));
    expect(cs).toEqual(owner);
    expect(owner.length).toBeGreaterThan(0);
  });

  it("carries only id, name and role", async () => {
    const rows = await assignable(await signIn("cs@pema.test"));
    for (const row of rows) expect(Object.keys(row).toSorted()).toEqual(["id", "name", "role"]);
  });

  it("lists active staff with an assignable role, A to Z by name", async () => {
    const rows = await assignable(await signIn("owner@pema.test"));
    const expected = USERS.filter((u) => u.active && ASSIGNABLE_ROLES.includes(u.role)).map(
      (u) => u.id,
    );
    expect(rows.map((r) => r.id).toSorted()).toEqual(expected.toSorted());
    expect(rows.every((r) => ASSIGNABLE_ROLES.includes(r.role as never))).toBe(true);
    const names = rows.map((r) => r.name.toLowerCase());
    expect(names).toEqual(names.toSorted((a, b) => a.localeCompare(b)));
  });

  it("leaves out a locked account, and reception", async () => {
    const reception = USERS.find((u) => u.role === "reception");
    expect(reception).toBeDefined();
    const ids = (await assignable(await signIn("owner@pema.test"))).map((r) => r.id);
    expect(ids).not.toContain(reception?.id);
  });
});

describe("assignee check of the mock task route", () => {
  it("resolving a task refuses a non-assignable owner and leaves the task open", async () => {
    const cookie = await signIn("cs@pema.test");
    const task = tasks.find((t) => t.status === "open");
    expect(task).toBeDefined();
    const reception = USERS.find((u) => u.role === "reception");
    const res = await call(cookie, "POST", `/api/v1/crm/tasks/${task?.id}/resolve`, {
      version: task?.version,
      outcome: "no_need",
      channel: "call",
      note: "Đã gọi (ghi chú mẫu)",
      owner_user_id: reception?.id,
    });
    expect(res.status).toBe(422);
    expect(((await res.json()) as { error: { message: string } }).error.message).toBe(
      "Chọn người phụ trách hợp lệ.",
    );
    expect(task?.status).toBe("open");
  });
});
