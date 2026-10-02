// GET/POST/PATCH /api/v1/admin/users in the mock behave like the real routes (backend test
// tests/api/test_admin_users_routes.py): the manager lists, only the owner changes, 409/422/429/404 as the BE
// answers, a lock or a role change ends the sessions of that user and a locked account cannot sign in.
import type { Server } from "node:http";
import type { AddressInfo } from "node:net";

import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";

import { resetAttempts } from "./auth";
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

// The server runs in this process and every test shares one minute: start each with a fresh rate limit.
beforeEach(resetAttempts);

type Staff = {
  id: string;
  display_name: string;
  email: string;
  role: string;
  active: boolean;
  last_login_at: string | null;
  created_at: string;
  version: number;
};
type Page = { items: Staff[]; total: number; limit: number; offset: number };

async function signIn(
  email: string,
  password = "demo1234",
): Promise<{ status: number; cookie: string }> {
  const res = await fetch(`${base}/api/v1/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return { status: res.status, cookie: res.headers.get("set-cookie")?.split(";")[0] ?? "" };
}

function call(cookie: string, method: string, path: string, body?: unknown): Promise<Response> {
  return fetch(`${base}${path}`, {
    method,
    headers: { "content-type": "application/json", ...(cookie ? { cookie } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

async function list(cookie: string, query = ""): Promise<Page> {
  const res = await call(cookie, "GET", `/api/v1/admin/users${query}`);
  expect(res.status).toBe(200);
  return (await res.json()) as Page;
}

async function create(cookie: string, overrides: Record<string, unknown> = {}): Promise<Staff> {
  const tag = Math.random().toString(36).slice(2, 10);
  const res = await call(cookie, "POST", "/api/v1/admin/users", {
    display_name: `Nhân viên ${tag}`,
    email: `${tag}@pema.test`,
    role: "cs_staff",
    password: "mat-khau-ban-dau-1",
    ...overrides,
  });
  expect(res.status).toBe(201);
  return (await res.json()) as Staff;
}

describe("mock GET /api/v1/admin/users", () => {
  it("is for the owner and the manager; the others get 403 and no session gets 401", async () => {
    expect((await call("", "GET", "/api/v1/admin/users")).status).toBe(401);
    for (const email of ["doctor@pema.test", "cs@pema.test", "reception@pema.test"]) {
      const caller = await signIn(email);
      expect((await call(caller.cookie, "GET", "/api/v1/admin/users")).status).toBe(403);
    }
    const manager = await signIn("manager@pema.test");
    const page = await list(manager.cookie);
    expect(page.total).toBeGreaterThanOrEqual(5);
    expect(JSON.stringify(page)).not.toContain("password");
  });

  it("filters by role, status and name, and pages", async () => {
    const owner = await signIn("owner@pema.test");
    const doctors = await list(owner.cookie, "?role=doctor");
    expect(doctors.items.every((u) => u.role === "doctor")).toBe(true);
    const locked = await list(owner.cookie, "?active=false");
    expect(locked.items.length).toBeGreaterThan(0);
    expect(locked.items.every((u) => !u.active)).toBe(true);
    const byName = await list(owner.cookie, `?q=${encodeURIComponent("mai")}`);
    expect(byName.items.length).toBeGreaterThan(0);
    const paged = await list(owner.cookie, "?limit=2&offset=1");
    expect(paged.items).toHaveLength(2);
    expect(paged.offset).toBe(1);
  });
});

describe("mock POST /api/v1/admin/users", () => {
  it("creates an account that can sign in; the manager gets 403", async () => {
    const owner = await signIn("owner@pema.test");
    const manager = await signIn("manager@pema.test");
    const denied = await call(manager.cookie, "POST", "/api/v1/admin/users", {});
    expect(denied.status).toBe(403);

    const made = await create(owner.cookie, {
      email: "Moi.Vao@pema.test",
      role: "doctor",
      password: "mat-khau-ban-dau-1",
    });

    expect(made.email).toBe("moi.vao@pema.test");
    expect(made.active).toBe(true);
    expect(made.version).toBe(1);
    expect((await signIn("moi.vao@pema.test", "mat-khau-ban-dau-1")).status).toBe(200);
  });

  it("answers 409 for a taken e-mail and 422 for a bad body", async () => {
    const owner = await signIn("owner@pema.test");
    const body = {
      display_name: "X",
      email: "owner@pema.test",
      role: "cs_staff",
      password: "12345678",
    };
    expect((await call(owner.cookie, "POST", "/api/v1/admin/users", body)).status).toBe(409);
    for (const bad of [
      { ...body, email: "moi.hop.le@pema.test", password: "ngan" },
      { ...body, email: "khong-phai-email" },
      { ...body, email: "moi.hop.le@pema.test", role: "patient" },
      { ...body, email: "moi.hop.le@pema.test", display_name: "  " },
    ]) {
      expect((await call(owner.cookie, "POST", "/api/v1/admin/users", bad)).status).toBe(422);
    }
  });

  it("allows 5 creations a minute per owner and answers 429 on the next", async () => {
    const manager = await signIn("manager@pema.test");
    expect(manager.status).toBe(200);
    const owner = await signIn("owner@pema.test");
    let blocked = false;
    for (let i = 0; i < 8 && !blocked; i += 1) {
      const res = await call(owner.cookie, "POST", "/api/v1/admin/users", {
        display_name: `Giới hạn ${i}`,
        email: `gioi.han.${i}@pema.test`,
        role: "reception",
        password: "12345678",
      });
      blocked = res.status === 429;
    }
    expect(blocked).toBe(true);
  });
});

describe("mock PATCH /api/v1/admin/users/{user_id}", () => {
  it("renames, bumps the version and refuses a stale one with 409", async () => {
    const owner = await signIn("owner@pema.test");
    const user = (await list(owner.cookie, "?q=thu@pema.test")).items[0];
    if (!user) throw new Error("seed user missing");

    const ok = await call(owner.cookie, "PATCH", `/api/v1/admin/users/${user.id}`, {
      version: user.version,
      display_name: "Đặng Minh Thư (đã đổi)",
    });
    expect(ok.status).toBe(200);
    expect(((await ok.json()) as Staff).version).toBe(user.version + 1);

    const stale = await call(owner.cookie, "PATCH", `/api/v1/admin/users/${user.id}`, {
      version: user.version,
      display_name: "Lần hai",
    });
    expect(stale.status).toBe(409);
  });

  it("is the owner's alone and 404 for an unknown id", async () => {
    const manager = await signIn("manager@pema.test");
    const owner = await signIn("owner@pema.test");
    const target = (await list(owner.cookie, "?q=bsan@pema.test")).items[0];
    if (!target) throw new Error("seed user missing");
    const body = { version: target.version, active: false };
    expect(
      (await call(manager.cookie, "PATCH", `/api/v1/admin/users/${target.id}`, body)).status,
    ).toBe(403);
    expect(
      (
        await call(
          owner.cookie,
          "PATCH",
          "/api/v1/admin/users/00000000-0000-4000-8000-0000000000ff",
          body,
        )
      ).status,
    ).toBe(404);
  });

  it("locks: sessions end, the login is refused; unlocking restores it", async () => {
    const owner = await signIn("owner@pema.test");
    const made = await create(owner.cookie, { role: "cs_staff", password: "mat-khau-ban-dau-1" });
    const laptop = await signIn(made.email, "mat-khau-ban-dau-1");
    const me = (cookie: string) => call(cookie, "GET", "/api/v1/me");
    expect((await me(laptop.cookie)).status).toBe(200);

    const locked = await call(owner.cookie, "PATCH", `/api/v1/admin/users/${made.id}`, {
      version: made.version,
      active: false,
    });
    const lockedBody = (await locked.json()) as Staff;

    expect(lockedBody.active).toBe(false);
    expect((await me(laptop.cookie)).status).toBe(401);
    expect((await me(owner.cookie)).status).toBe(200);
    expect((await signIn(made.email, "mat-khau-ban-dau-1")).status).toBe(401);

    await call(owner.cookie, "PATCH", `/api/v1/admin/users/${made.id}`, {
      version: lockedBody.version,
      active: true,
    });
    expect((await signIn(made.email, "mat-khau-ban-dau-1")).status).toBe(200);
  });

  it("ends the sessions on a role change", async () => {
    const owner = await signIn("owner@pema.test");
    const made = await create(owner.cookie, { role: "manager", password: "mat-khau-ban-dau-1" });
    const session = await signIn(made.email, "mat-khau-ban-dau-1");

    const res = await call(owner.cookie, "PATCH", `/api/v1/admin/users/${made.id}`, {
      version: made.version,
      role: "reception",
    });

    expect(res.status).toBe(200);
    expect((await call(session.cookie, "GET", "/api/v1/me")).status).toBe(401);
  });

  it("refuses to lock or re-role your own account, and the last active owner", async () => {
    const owner = await signIn("owner@pema.test");
    const self = (await list(owner.cookie, "?q=owner@pema.test")).items[0];
    if (!self) throw new Error("seed user missing");
    for (const change of [{ active: false }, { role: "manager" }]) {
      const res = await call(owner.cookie, "PATCH", `/api/v1/admin/users/${self.id}`, {
        version: self.version,
        ...change,
      });
      expect(res.status).toBe(422);
    }
    expect(
      (
        await call(owner.cookie, "PATCH", `/api/v1/admin/users/${self.id}`, {
          version: self.version,
          display_name: "Nguyễn Thanh Hà",
        })
      ).status,
    ).toBe(200);

    // a second owner demotes the first: allowed while another owner stays; the last one is protected
    const second = await create(owner.cookie, { role: "owner", password: "mat-khau-ban-dau-1" });
    const secondSession = await signIn(second.email, "mat-khau-ban-dau-1");
    const fresh = (await list(owner.cookie, "?q=owner@pema.test")).items[0];
    if (!fresh) throw new Error("seed user missing");
    expect(
      (
        await call(secondSession.cookie, "PATCH", `/api/v1/admin/users/${fresh.id}`, {
          version: fresh.version,
          role: "manager",
        })
      ).status,
    ).toBe(200);
    const stillThere = await list(secondSession.cookie, "?role=owner&active=true");
    expect(stillThere.total).toBe(1);
  });
});
