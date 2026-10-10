// The mock's agent-token route and fake agent (`pnpm dev:mock`): the owner and the manager get a short token, other
// roles 403 with the API's sentence, no session 401; the fake agent wants that token and lists the Zalo plugin.
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

async function cookieOf(email: string): Promise<string> {
  const res = await fetch(`${base}/api/v1/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email, password: "demo1234" }),
  });
  return res.headers.get("set-cookie")?.split(";")[0] ?? "";
}

const askToken = (cookie: string) =>
  fetch(`${base}/api/v1/auth/agent-token`, {
    method: "POST",
    headers: cookie ? { cookie } : {},
  });

describe("mock POST /api/v1/auth/agent-token", () => {
  it("gives_the_owner_and_the_manager_a_short_token", async () => {
    for (const email of ["owner@pema.test", "manager@pema.test"]) {
      const res = await askToken(await cookieOf(email));
      const body = (await res.json()) as { token: string; expires_at: string };

      expect(res.status).toBe(200);
      expect(body.token).toMatch(/^mock-agent-/);
      expect(Date.parse(body.expires_at)).toBeGreaterThan(Date.now());
    }
  });

  it("refuses_a_role_without_admin_agents_with_the_apis_sentence_and_no_session_with_401", async () => {
    const res = await askToken(await cookieOf("doctor@pema.test"));

    expect(res.status).toBe(403);
    expect(await res.json()).toEqual({
      error: expect.objectContaining({
        code: "forbidden",
        message: "Bạn không có quyền quản trị agent.",
      }) as unknown,
    });
    expect((await askToken("")).status).toBe(401);
  });
});

describe("the fake agent", () => {
  it("wants_a_token_then_lists_the_zalo_script_and_its_accounts", async () => {
    expect((await fetch(`${base}/v1/admin/ui`)).status).toBe(401);

    const { token } = (await (await askToken(await cookieOf("owner@pema.test"))).json()) as {
      token: string;
    };
    const signed = { headers: { authorization: `Bearer ${token}` } };
    const listing = (await (await fetch(`${base}/v1/admin/ui`, signed)).json()) as {
      plugins: { name: string; script: string }[];
    };
    const accounts = (await (await fetch(`${base}/v1/plugins/zalo/accounts`, signed)).json()) as {
      id: string;
    }[];

    expect(listing.plugins).toEqual([
      expect.objectContaining({ name: "zalo", script: "/ui/zalo/client.js" }),
    ]);
    expect(accounts.length).toBeGreaterThan(0);
  });
});

describe("the fake agent's dashboard routes", () => {
  async function signed() {
    const { token } = (await (await askToken(await cookieOf("owner@pema.test"))).json()) as {
      token: string;
    };
    return { authorization: `Bearer ${token}`, "content-type": "application/json" };
  }

  it("keeps_a_saved_model_change_until_it_is_reset_to_the_profile", async () => {
    const headers = await signed();
    const patch = await fetch(`${base}/v1/admin/model`, {
      method: "PATCH",
      headers,
      body: JSON.stringify({ model: "deepseek-reasoner", api_key: "sk-test" }),
    });
    const saved = (await patch.json()) as { model: string; sources: Record<string, string> };
    const reset = await fetch(`${base}/v1/admin/model`, { method: "DELETE", headers });

    expect(saved.model).toBe("deepseek-reasoner");
    expect(saved.sources).toMatchObject({ model: "db", api_key: "db" });
    expect(await reset.json()).toMatchObject({
      model: "deepseek-chat",
      sources: { api_key: "unset" },
    });
  });

  it("switches_a_plugin_off_and_on_in_the_listing", async () => {
    const headers = await signed();
    const off = await fetch(`${base}/v1/admin/plugins/zalo/disable`, { method: "POST", headers });
    const on = await fetch(`${base}/v1/admin/plugins/zalo/enable`, { method: "POST", headers });

    expect(await off.json()).toMatchObject({ name: "zalo", enabled: false });
    expect(await on.json()).toMatchObject({ name: "zalo", enabled: true });
  });

  it("saves_a_plugins_setting_as_the_admins_value", async () => {
    const headers = await signed();
    const saved = await fetch(`${base}/v1/admin/plugins/zalo/settings`, {
      method: "PATCH",
      headers: { ...headers, "content-type": "application/json" },
      body: JSON.stringify({ settings: { rich_text: false } }),
    });

    expect(await saved.json()).toMatchObject({
      settings: [{ key: "rich_text", value: false, source: "admin" }],
    });
  });

  it("lists_the_sessions_and_traces_filtered_and_deletes_a_session", async () => {
    const headers = await signed();
    const get = async (path: string) => (await fetch(`${base}${path}`, { headers })).json();

    const zalo = (await get("/v1/admin/sessions?channel=zalo-cskh-mau")) as {
      items: { user_id: string }[];
    };
    const failed = (await get("/v1/admin/traces?errors_only=true")) as {
      items: { stop: string }[];
    };
    const usage = (await get("/v1/admin/usage?days=7")) as { days: unknown[] };
    const id = encodeURIComponent("clinic:http:u-mau-03:0");
    const deleted = await fetch(`${base}/v1/admin/sessions/${id}`, { method: "DELETE", headers });
    const again = await fetch(`${base}/v1/admin/sessions/${id}`, { method: "DELETE", headers });

    expect(zalo.items.map((s) => s.user_id)).toEqual(["u-mau-01", "u-mau-02"]);
    expect(failed.items.map((t) => t.stop)).toEqual(["error"]);
    expect(usage.days).toHaveLength(7);
    expect([deleted.status, again.status]).toEqual([200, 404]);
  });
});
