// Tests of the logic behind `pnpm kill-switch`.
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { SIGNATURE_HEADER, TIMESTAMP_HEADER, verifySignature } from "./auth.js";
import { parseKillSwitchArgs, sendKillSwitch } from "./kill-switch-cli.js";
import { SECRET } from "./test-support.js";

type Captured = { url: string; method: string; headers: Record<string, string>; body: string };

function capturingFetch(status = 200) {
  const captured: Captured[] = [];
  const fetchImpl: typeof fetch = async (input, init) => {
    captured.push({
      url: String(input),
      method: String(init?.method),
      headers: (init?.headers ?? {}) as Record<string, string>,
      body: String(init?.body ?? ""),
    });
    return new Response('{"ok":true}', { status });
  };
  return { fetchImpl, captured };
}

const ENV = {
  PEMA_ZALO_BRIDGE_SECRET: SECRET,
  PEMA_ZALO_BRIDGE_HOST: "127.0.0.1",
  PEMA_ZALO_BRIDGE_PORT: "8200",
};
const NOW = 1_700_000_000;

describe("parseKillSwitchArgs", () => {
  it("on_defaults_to_scope_all", () => {
    assert.deepEqual(parseKillSwitchArgs(["on"]), { action: "on", scope: "all" });
  });

  it("on_takes_a_scope_and_a_reason", () => {
    assert.deepEqual(parseKillSwitchArgs(["on", "--scope", "proactive", "--reason", "khẩn cấp"]), {
      action: "on",
      scope: "proactive",
      reason: "khẩn cấp",
    });
  });

  it("off_and_status_are_recognised", () => {
    assert.deepEqual(parseKillSwitchArgs(["off"]), { action: "off" });
    assert.deepEqual(parseKillSwitchArgs(["status"]), { action: "status" });
  });

  it("anything_else_is_an_error", () => {
    assert.ok("error" in parseKillSwitchArgs([]));
    assert.ok("error" in parseKillSwitchArgs(["maybe"]));
    assert.ok("error" in parseKillSwitchArgs(["on", "--scope", "some"]));
  });
});

describe("sendKillSwitch", () => {
  it("on_posts_a_signed_json_body_to_the_bridge", async () => {
    const { fetchImpl, captured } = capturingFetch();

    const result = await sendKillSwitch(
      { action: "on", scope: "all", reason: "test" },
      ENV,
      fetchImpl,
      NOW,
    );

    assert.equal(result.ok, true);
    assert.equal(captured[0]?.url, "http://127.0.0.1:8200/v1/kill-switch");
    assert.equal(captured[0]?.method, "POST");
    assert.deepEqual(JSON.parse(captured[0]?.body ?? ""), {
      on: true,
      scope: "all",
      reason: "test",
    });
    const headers = captured[0]?.headers ?? {};
    assert.deepEqual(
      verifySignature({
        secret: SECRET,
        timestamp: headers[TIMESTAMP_HEADER],
        signature: headers[SIGNATURE_HEADER],
        body: captured[0]?.body ?? "",
        nowSeconds: NOW,
      }),
      { ok: true },
    );
  });

  it("off_posts_on_false", async () => {
    const { fetchImpl, captured } = capturingFetch();
    await sendKillSwitch({ action: "off" }, ENV, fetchImpl, NOW);
    assert.deepEqual(JSON.parse(captured[0]?.body ?? ""), { on: false });
  });

  it("status_is_a_get_that_signs_the_empty_string", async () => {
    const { fetchImpl, captured } = capturingFetch();
    await sendKillSwitch({ action: "status" }, ENV, fetchImpl, NOW);
    const headers = captured[0]?.headers ?? {};
    assert.equal(captured[0]?.method, "GET");
    assert.deepEqual(
      verifySignature({
        secret: SECRET,
        timestamp: headers[TIMESTAMP_HEADER],
        signature: headers[SIGNATURE_HEADER],
        body: "",
        nowSeconds: NOW,
      }),
      { ok: true },
    );
  });

  it("a_missing_secret_is_an_error_that_does_not_send_anything", async () => {
    const { fetchImpl, captured } = capturingFetch();
    await assert.rejects(
      sendKillSwitch({ action: "on", scope: "all" }, {}, fetchImpl, NOW),
      /SECRET/,
    );
    assert.equal(captured.length, 0);
  });

  it("a_refused_request_is_reported_not_ok", async () => {
    const { fetchImpl } = capturingFetch(401);
    const result = await sendKillSwitch({ action: "on", scope: "all" }, ENV, fetchImpl, NOW);
    assert.deepEqual([result.ok, result.status], [false, 401]);
  });

  it("an_ipv6_host_is_bracketed_in_the_url", async () => {
    const { fetchImpl, captured } = capturingFetch();
    await sendKillSwitch(
      { action: "status" },
      { ...ENV, PEMA_ZALO_BRIDGE_HOST: "::1" },
      fetchImpl,
      NOW,
    );
    assert.equal(captured[0]?.url, "http://[::1]:8200/v1/kill-switch");
  });
});
