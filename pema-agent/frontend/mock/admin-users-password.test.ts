// POST /api/v1/admin/users/{user_id}/password in the mock behaves like the real route (backend test
// tests/api/test_admin_users_password_route.py): owner only, 404 for an unknown user, 422 for your own
// account or a short password, 429 after 5 resets a minute, 204 without a body, and every session of the
// reset user ends while the owner keeps theirs.
import type { Server } from "node:http";
import type { AddressInfo } from "node:net";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { USERS } from "./auth";
import { startMockServer } from "./server";

let server: Server;
let base: string;

const TARGET = USERS.find((u) => u.email === "cs@pema.test");
const OWNER = USERS.find((u) => u.email === "owner@pema.test");
const NEW = "mat-khau-do-chu-dat-1";

beforeAll(async () => {
  server = await startMockServer(0);
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});

afterAll(() => {
  server.close();
});

async function signIn(
  email: string,
  password: string,
): Promise<{ status: number; cookie: string }> {
  const res = await fetch(`${base}/api/v1/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ clinic_slug: "pema-demo", email, password }),
  });
  return { status: res.status, cookie: res.headers.get("set-cookie")?.split(";")[0] ?? "" };
}

function reset(cookie: string, userId: string, password: string): Promise<Response> {
  return fetch(`${base}/api/v1/admin/users/${userId}/password`, {
    method: "POST",
    headers: { "content-type": "application/json", ...(cookie ? { cookie } : {}) },
    body: JSON.stringify({ new_password: password }),
  });
}

describe("mock POST /api/v1/admin/users/{user_id}/password", () => {
  it("is the owner's alone: no session 401, the manager and others 403", async () => {
    if (!TARGET) throw new Error("seed user missing");
    expect((await reset("", TARGET.id, NEW)).status).toBe(401);
    for (const email of ["manager@pema.test", "doctor@pema.test", "reception@pema.test"]) {
      const caller = await signIn(email, "demo1234");
      expect((await reset(caller.cookie, TARGET.id, NEW)).status).toBe(403);
    }
    expect((await signIn(TARGET.email, "demo1234")).status).toBe(200);
  });

  it("refuses your own account, a short password and an unknown user", async () => {
    if (!OWNER || !TARGET) throw new Error("seed user missing");
    const owner = await signIn(OWNER.email, "demo1234");
    expect((await reset(owner.cookie, OWNER.id, NEW)).status).toBe(422);
    expect((await reset(owner.cookie, TARGET.id, "ngan")).status).toBe(422);
    expect((await reset(owner.cookie, "00000000-0000-4000-8000-0000000000ff", NEW)).status).toBe(
      404,
    );
  });

  it("resets the password, ends every session of that user and keeps the owner signed in", async () => {
    if (!OWNER || !TARGET) throw new Error("seed user missing");
    const owner = await signIn(OWNER.email, "demo1234");
    const laptop = await signIn(TARGET.email, "demo1234");
    const phone = await signIn(TARGET.email, "demo1234");
    const me = (cookie: string) => fetch(`${base}/api/v1/me`, { headers: { cookie } });
    expect((await me(laptop.cookie)).status).toBe(200);

    const res = await reset(owner.cookie, TARGET.id, NEW);

    expect(res.status).toBe(204);
    expect(await res.text()).toBe("");
    expect((await me(laptop.cookie)).status).toBe(401);
    expect((await me(phone.cookie)).status).toBe(401);
    expect((await me(owner.cookie)).status).toBe(200);
    expect((await signIn(TARGET.email, NEW)).status).toBe(200);
    expect((await signIn(TARGET.email, "demo1234")).status).toBe(401);
  });

  it("allows 5 resets a minute per owner and answers 429 on the 6th", async () => {
    if (!OWNER || !TARGET) throw new Error("seed user missing");
    // The earlier tests already spent some of this owner's budget in the same minute: a fresh owner
    // session does not matter, the limit is per user. Spend what is left, then expect the block.
    const owner = await signIn(OWNER.email, "demo1234");
    let blocked = false;
    for (let i = 0; i < 6 && !blocked; i += 1) {
      blocked = (await reset(owner.cookie, TARGET.id, NEW)).status === 429;
    }
    expect(blocked).toBe(true);
  });
});
