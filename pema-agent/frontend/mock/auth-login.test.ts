// POST /api/v1/auth/login in the mock: one installation is ONE clinic (CONTRACTS-AI01 section 10), so the body
// is e-mail + password. A `clinic_slug` left over from an old client is accepted and ignored.
import type { Server } from "node:http";
import type { AddressInfo } from "node:net";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

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

function login(body: Record<string, string>): Promise<Response> {
  return fetch(`${base}/api/v1/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("mock POST /api/v1/auth/login", () => {
  it("signs in with e-mail and password only and names the one clinic in the summary", async () => {
    const res = await login({ email: "cs@pema.test", password: "demo1234" });
    expect(res.status).toBe(200);
    expect(res.headers.get("set-cookie")).toContain("pema_session=");
    const body = (await res.json()) as { user: { clinic_name: string; role: string } };
    expect(body.user.role).toBe("cs_staff");
    expect(body.user.clinic_name).not.toBe("");
  });

  it("still accepts a leftover clinic_slug and ignores whatever it says", async () => {
    const credentials = { email: "cs@pema.test", password: "demo1234" };
    const same = await login({ clinic_slug: "pema-demo", ...credentials });
    const other = await login({ clinic_slug: "khac", ...credentials });
    expect(same.status).toBe(200);
    expect(other.status).toBe(200);
  });

  it("refuses a wrong password with a message that does not mention a clinic", async () => {
    const res = await login({ email: "cs@pema.test", password: "sai-mat-khau" });
    expect(res.status).toBe(401);
    const body = (await res.json()) as { error: { message: string } };
    expect(body.error.message).toBe("Sai email hoặc mật khẩu.");
  });
});
