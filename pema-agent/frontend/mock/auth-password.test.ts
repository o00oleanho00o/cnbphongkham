// POST /api/v1/auth/password in the mock behaves like the real route (backend test
// tests/api/test_dashboard_password_route.py): 204 and the same cookie on success, 401 for a wrong current
// password or no session, 422 for a short or unchanged one, and every OTHER session of the user ends.
import type { Server } from "node:http";
import type { AddressInfo } from "node:net";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { USERS } from "./auth";
import { startMockServer } from "./server";

let server: Server;
let base: string;

// `reception` is only used here, so changing its password cannot disturb another test file.
const EMAIL = "reception@pema.test";
const START = "demo1234";

beforeAll(async () => {
  server = await startMockServer(0);
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});

afterAll(() => {
  server.close();
});

async function signIn(password: string): Promise<{ status: number; cookie: string }> {
  const res = await fetch(`${base}/api/v1/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email: EMAIL, password }),
  });
  return { status: res.status, cookie: res.headers.get("set-cookie")?.split(";")[0] ?? "" };
}

function change(cookie: string, current: string, next: string): Promise<Response> {
  return fetch(`${base}/api/v1/auth/password`, {
    method: "POST",
    headers: { "content-type": "application/json", ...(cookie ? { cookie } : {}) },
    body: JSON.stringify({ current_password: current, new_password: next }),
  });
}

describe("mock POST /api/v1/auth/password", () => {
  it("refuses without a session, a wrong current password, a short and an unchanged password", async () => {
    const mine = await signIn(START);
    expect(mine.status).toBe(200);

    expect((await change("", START, "mat-khau-moi-456")).status).toBe(401);
    expect((await change(mine.cookie, "doan-bua", "mat-khau-moi-456")).status).toBe(401);
    expect((await change(mine.cookie, START, "ngan")).status).toBe(422);
    expect((await change(mine.cookie, START, START)).status).toBe(422);
    expect((await signIn(START)).status).toBe(200);
  });

  it("changes it, keeps the caller signed in and ends the other sessions", async () => {
    const mine = await signIn(START);
    const otherDevice = await signIn(START);
    const me = (cookie: string) => fetch(`${base}/api/v1/me`, { headers: { cookie } });
    expect((await me(otherDevice.cookie)).status).toBe(200);

    expect((await change(mine.cookie, START, "mat-khau-moi-456")).status).toBe(204);

    expect((await me(mine.cookie)).status).toBe(200);
    expect((await me(otherDevice.cookie)).status).toBe(401);
    expect((await signIn("mat-khau-moi-456")).status).toBe(200);
    expect((await signIn(START)).status).toBe(401);

    const user = USERS.find((u) => u.email === EMAIL);
    if (user) user.password = START;
  });
});
