// New tests: the bridge's HTTP surface (wire protocol of the README) with a fake gateway, a fake zca-js API,
// a recording publisher and an injected clock. Nothing here opens a network connection to Zalo.
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { Reactions, ZaloApiError } from "zca-js";
import { SIGNATURE_HEADER, TIMESTAMP_HEADER, signedHeaders } from "./auth.js";
import { createBridge, type Bridge } from "./bridge.js";
import { doiChoDenKhi } from "./doi-cho-den-khi.js";
import { MAX_BODY_BYTES } from "./app.js";
import {
  FakeGateway,
  RecordingPublisher,
  SECRET,
  TEST_CREDENTIAL,
  createFakeApi,
  createFakeSession,
  makeConfig,
  readEnvelope,
  signedSender,
  type FakeApi,
  type Sender,
} from "./test-support.js";
import type { BridgeConfig } from "./config.js";

const PUBLIC_LOOKUP = async (): Promise<string[]> => ["93.184.216.34"];
const TINY_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==";

type Fixture = {
  bridge: Bridge;
  gateway: FakeGateway;
  publisher: RecordingPublisher;
  sender: Sender;
  fake: FakeApi;
  clock: { now: number };
};

function build(configOverrides: Partial<BridgeConfig> = {}, lookup = PUBLIC_LOOKUP) {
  const gateway = new FakeGateway();
  const publisher = new RecordingPublisher();
  const clock = { now: Date.parse("2026-10-01T03:00:00Z") };
  const bridge = createBridge({
    config: makeConfig(configOverrides),
    gateway,
    publisher,
    now: () => clock.now,
    lookupHost: lookup,
  });
  const sender = signedSender(bridge.app, SECRET, () => Math.floor(clock.now / 1000));
  return { bridge, gateway, publisher, sender, clock };
}

const startBody = { clinic_slug: "clinic-a", credential: TEST_CREDENTIAL };

/** A bridge with account `acc-1` already started on a fresh fake API. */
async function running(
  configOverrides: Partial<BridgeConfig> = {},
  apiOverrides: Parameters<typeof createFakeApi>[0] = {},
): Promise<Fixture> {
  const base = build(configOverrides);
  const fake = createFakeApi(apiOverrides);
  base.gateway.nextSessions.push(createFakeSession(fake));
  const started = await base.sender.post("/v1/accounts/acc-1/start", startBody);
  assert.equal(started.status, 200);
  return { ...base, fake };
}

const sendBody = (overrides: Record<string, unknown> = {}) => ({
  thread_id: "2000001",
  thread_type: 0,
  text: "Chào bạn",
  proactive: false,
  ...overrides,
});

async function errorOf(response: Response) {
  const body = await readEnvelope(response);
  return { status: response.status, kind: body.error?.kind, code: body.error?.code, body };
}

describe("app: health and the disabled flag", () => {
  it("health_is_unsigned_and_returns_only_ok_enabled_and_the_account_count", async () => {
    const { bridge } = build();

    const response = await bridge.app.request("/health");

    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { ok: true, enabled: true, accounts: 0 });
  });

  it("health_counts_the_accounts_that_are_not_stopped", async () => {
    const { bridge, sender } = await running();
    assert.deepEqual(await (await bridge.app.request("/health")).json(), {
      ok: true,
      enabled: true,
      accounts: 1,
    });
    await sender.post("/v1/accounts/acc-1/stop", {});
    assert.equal(
      ((await (await bridge.app.request("/health")).json()) as { accounts: number }).accounts,
      0,
    );
  });

  it("a_disabled_bridge_answers_503_bridge_disabled_for_every_route_and_never_calls_zalo", async () => {
    const { bridge, gateway, sender } = build({ enabled: false, secret: "" });

    const routes = [
      sender.post("/v1/accounts/acc-1/start", startBody),
      sender.get("/v1/accounts"),
      sender.post("/v1/accounts/acc-1/send", sendBody()),
      sender.post("/v1/accounts/acc-1/login/qr", { clinic_slug: "clinic-a" }),
      sender.post("/v1/kill-switch", { on: true }),
      bridge.app.request("/v1/accounts"),
    ];
    const results = await Promise.all(routes.map(async (pending) => errorOf(await pending)));

    results.forEach((result) => {
      assert.equal(result.status, 503);
      assert.equal(result.kind, "bridge_disabled");
    });
    assert.equal(gateway.loginCalls.length, 0);
    assert.equal(gateway.qrControls.length, 0);
  });

  it("a_disabled_bridge_still_serves_health_with_enabled_false", async () => {
    const { bridge } = build({ enabled: false, secret: "" });
    const response = await bridge.app.request("/health");
    assert.deepEqual(await response.json(), { ok: true, enabled: false, accounts: 0 });
  });
});

describe("app: HMAC authentication", () => {
  it("an_unsigned_request_is_refused_as_unauthorized", async () => {
    const { bridge } = build();
    const result = await errorOf(await bridge.app.request("/v1/accounts"));
    assert.equal(result.status, 401);
    assert.equal(result.kind, "unauthorized");
  });

  it("a_signature_made_with_the_wrong_secret_is_refused", async () => {
    const { bridge, clock } = build();
    const wrong = signedSender(bridge.app, "another-secret-0123456789", () =>
      Math.floor(clock.now / 1000),
    );
    const result = await errorOf(await wrong.get("/v1/accounts"));
    assert.equal(result.status, 401);
  });

  it("a_stale_timestamp_is_refused_even_with_a_valid_signature", async () => {
    const { bridge, clock } = build();
    const stale = signedSender(bridge.app, SECRET, () => Math.floor(clock.now / 1000) - 301);
    const result = await errorOf(await stale.get("/v1/accounts"));
    assert.equal(result.status, 401);
    assert.equal(result.kind, "unauthorized");
  });

  it("a_tampered_body_is_refused", async () => {
    const { bridge, gateway, clock } = build();
    const signedFor = JSON.stringify({ on: false });
    const sent = JSON.stringify({ on: true });

    const response = await bridge.app.request("/v1/kill-switch", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...signedHeaders(SECRET, signedFor, Math.floor(clock.now / 1000)),
      },
      body: sent,
    });

    assert.equal(response.status, 401);
    assert.equal(bridge.killSwitch.get().on, false, "the tampered command did not run");
    assert.equal(gateway.loginCalls.length, 0);
  });

  it("a_request_without_a_body_signs_the_empty_string", async () => {
    const { sender } = build();
    const response = await sender.get("/v1/accounts");
    assert.equal(response.status, 200);
  });

  it("only_get_health_is_unsigned", async () => {
    const { bridge } = build();
    const checks = await Promise.all(
      ["/v1/accounts", "/v1/kill-switch", "/v1/accounts/acc-1/state"].map(
        async (path) => (await bridge.app.request(path)).status,
      ),
    );
    assert.deepEqual(checks, [401, 401, 401]);
  });

  it("a_signed_request_to_an_unknown_route_is_a_json_404", async () => {
    const { sender } = build();
    const result = await errorOf(await sender.get("/v1/nothing-here"));
    assert.equal(result.status, 404);
  });

  it("the_signature_headers_are_named_as_documented", () => {
    assert.equal(TIMESTAMP_HEADER, "X-Pema-Timestamp");
    assert.equal(SIGNATURE_HEADER, "X-Pema-Signature");
  });
});

describe("app: account lifecycle", () => {
  it("start_answers_the_own_id_and_the_state_reads_connecting", async () => {
    const { gateway, sender } = build();
    gateway.nextSessions.push(createFakeSession(createFakeApi(), "1000042"));

    const started = await sender.post("/v1/accounts/acc-1/start", startBody);
    const state = await sender.get("/v1/accounts/acc-1/state");

    assert.deepEqual(await started.json(), { ok: true, own_id: "1000042" });
    assert.deepEqual(await state.json(), { ok: true, state: "connecting" });
  });

  it("the_accounts_list_has_state_own_id_and_the_proactive_count", async () => {
    const { sender } = await running();
    await sender.post("/v1/accounts/acc-1/send", sendBody({ proactive: true }));

    const list = await readEnvelope(await sender.get("/v1/accounts"));

    assert.deepEqual(list["accounts"], [
      { account_id: "acc-1", state: "connecting", own_id: "1000001", proactive_sent_today: 1 },
    ]);
  });

  it("an_account_never_started_reads_stopped", async () => {
    const { sender } = build();
    const state = await readEnvelope(await sender.get("/v1/accounts/unknown/state"));
    assert.equal(state["state"], "stopped");
  });

  it("stop_and_stop_all_leave_the_accounts_stopped", async () => {
    const { gateway, sender } = await running();
    gateway.nextSessions.push(createFakeSession(createFakeApi()));
    await sender.post("/v1/accounts/acc-2/start", startBody);

    const stopAll = await sender.post("/v1/accounts/stop-all", {});

    assert.equal(stopAll.status, 200);
    const list = (await readEnvelope(await sender.get("/v1/accounts")))["accounts"] as Array<{
      state: string;
    }>;
    assert.deepEqual(
      list.map((account) => account.state),
      ["stopped", "stopped"],
    );
  });

  it("start_without_a_credential_is_a_422_bad_request", async () => {
    const { sender } = build();
    const result = await errorOf(
      await sender.post("/v1/accounts/acc-1/start", { clinic_slug: "clinic-a" }),
    );
    assert.equal(result.status, 422);
    assert.equal(result.kind, "bad_request");
  });

  it("a_validation_error_never_echoes_the_values_it_rejected", async () => {
    const { sender } = build();
    const response = await sender.post("/v1/accounts/acc-1/start", {
      clinic_slug: "clinic-a",
      credential: { cookie: "SECRET-COOKIE-VALUE", imei: "i", userAgent: "u" },
    });
    assert.equal((await response.text()).includes("SECRET-COOKIE-VALUE"), false);
  });

  it("a_body_that_is_not_json_is_a_400", async () => {
    const { bridge, clock } = build();
    const raw = "{not json";
    const response = await bridge.app.request("/v1/accounts/acc-1/start", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...signedHeaders(SECRET, raw, Math.floor(clock.now / 1000)),
      },
      body: raw,
    });
    assert.equal(response.status, 400);
  });

  it("an_account_id_with_odd_characters_is_refused", async () => {
    const { sender } = build();
    const result = await errorOf(await sender.get("/v1/accounts/a%20b%3Bdrop/state"));
    assert.equal(result.status, 422);
  });

  it("a_login_refused_by_zalo_is_a_502_zalo_rejected_with_the_code", async () => {
    const { gateway, sender } = build();
    gateway.loginError = new ZaloApiError("session expired", 114);
    const result = await errorOf(await sender.post("/v1/accounts/acc-1/start", startBody));
    assert.equal(result.status, 502);
    assert.equal(result.kind, "zalo_rejected");
    assert.equal(result.code, 114);
  });

  it("a_login_that_fails_without_a_code_is_a_502_transport", async () => {
    const { gateway, sender } = build();
    gateway.loginError = new Error("socket hang up");
    const result = await errorOf(await sender.post("/v1/accounts/acc-1/start", startBody));
    assert.equal(result.status, 502);
    assert.equal(result.kind, "transport");
    assert.equal(result.code, undefined);
  });

  it("start_applies_the_kill_switch_the_api_passes_even_when_the_login_fails", async () => {
    const { bridge, gateway, sender } = build();
    gateway.loginError = new Error("down");

    await sender.post("/v1/accounts/acc-1/start", {
      ...startBody,
      kill_switch: { on: true, scope: "proactive", reason: "clinic switch" },
    });

    assert.deepEqual(bridge.killSwitch.get(), {
      on: true,
      scope: "proactive",
      reason: "clinic switch",
    });
  });

  it("start_replaces_a_running_account_of_the_same_id", async () => {
    const { gateway, sender, fake } = await running();
    const second = createFakeApi();
    gateway.nextSessions.push(createFakeSession(second));

    await sender.post("/v1/accounts/acc-1/start", startBody);

    assert.equal(fake.listener.stops >= 1, true);
    assert.equal(second.listener.starts, 1);
  });
});

describe("app: kill switch", () => {
  it("post_and_get_kill_switch_round_trip_the_state", async () => {
    const { sender } = build();
    await sender.post("/v1/kill-switch", { on: true, scope: "proactive", reason: "clinic switch" });

    const state = await readEnvelope(await sender.get("/v1/kill-switch"));

    assert.deepEqual(
      { on: state["on"], scope: state["scope"], reason: state["reason"] },
      {
        on: true,
        scope: "proactive",
        reason: "clinic switch",
      },
    );
  });

  it("scope_all_blocks_a_reply_and_a_proactive_send_and_zalo_is_not_called", async () => {
    const { sender, fake } = await running();
    await sender.post("/v1/kill-switch", { on: true, scope: "all" });

    const reply = await errorOf(await sender.post("/v1/accounts/acc-1/send", sendBody()));
    const proactive = await errorOf(
      await sender.post("/v1/accounts/acc-1/send", sendBody({ proactive: true })),
    );

    assert.deepEqual([reply.status, reply.kind], [409, "kill_switch"]);
    assert.deepEqual([proactive.status, proactive.kind], [409, "kill_switch"]);
    assert.equal(fake.callsTo("sendMessage").length, 0);
  });

  it("scope_proactive_blocks_only_proactive_sends", async () => {
    const { sender, fake } = await running();
    await sender.post("/v1/kill-switch", { on: true, scope: "proactive" });

    const proactive = await errorOf(
      await sender.post("/v1/accounts/acc-1/send", sendBody({ proactive: true })),
    );
    const reply = await sender.post("/v1/accounts/acc-1/send", sendBody());

    assert.equal(proactive.kind, "kill_switch");
    assert.equal(reply.status, 200);
    assert.equal(fake.callsTo("sendMessage").length, 1);
  });

  it("the_switch_is_effective_immediately_in_both_directions", async () => {
    const { sender } = await running();
    assert.equal((await sender.post("/v1/accounts/acc-1/send", sendBody())).status, 200);

    await sender.post("/v1/kill-switch", { on: true, scope: "all" });
    assert.equal((await sender.post("/v1/accounts/acc-1/send", sendBody())).status, 409);

    await sender.post("/v1/kill-switch", { on: false });
    assert.equal((await sender.post("/v1/accounts/acc-1/send", sendBody())).status, 200);
  });

  it("the_switch_applies_to_every_account", async () => {
    const { gateway, sender } = await running();
    gateway.nextSessions.push(createFakeSession(createFakeApi()));
    await sender.post("/v1/accounts/acc-2/start", startBody);
    await sender.post("/v1/kill-switch", { on: true, scope: "all" });

    const first = await sender.post("/v1/accounts/acc-1/send", sendBody());
    const second = await sender.post("/v1/accounts/acc-2/send", sendBody());

    assert.deepEqual([first.status, second.status], [409, 409]);
  });

  it("an_invalid_scope_is_a_422", async () => {
    const { sender } = build();
    const result = await errorOf(await sender.post("/v1/kill-switch", { on: true, scope: "some" }));
    assert.equal(result.status, 422);
  });
});

describe("app: send and the safety gates", () => {
  it("a_send_reaches_zalo_and_answers_the_message_id_as_a_string", async () => {
    const { sender, fake } = await running();

    const response = await sender.post("/v1/accounts/acc-1/send", sendBody());

    assert.deepEqual(await response.json(), { ok: true, msg_id: "111" });
    assert.deepEqual(fake.callsTo("sendMessage")[0]?.args, [{ msg: "Chào bạn" }, "2000001", 0]);
  });

  it("an_id_beyond_the_safe_integer_range_survives_as_a_string", async () => {
    const { sender } = await running(
      {},
      {
        sendMessage: async () => ({
          message: { msgId: 9007199254740993n as unknown as number },
          attachment: [],
        }),
      },
    );
    const response = await sender.post("/v1/accounts/acc-1/send", sendBody());
    assert.equal(((await response.json()) as { msg_id: string }).msg_id, "9007199254740993");
  });

  it("a_send_to_a_group_passes_thread_type_1", async () => {
    const { sender, fake } = await running();
    await sender.post("/v1/accounts/acc-1/send", sendBody({ thread_type: 1 }));
    assert.equal(fake.callsTo("sendMessage")[0]?.args[2], 1);
  });

  it("an_account_that_is_not_running_answers_not_running_and_zalo_is_not_called", async () => {
    const { sender, fake } = await running();
    await sender.post("/v1/accounts/acc-1/stop", {});

    const missing = await errorOf(await sender.post("/v1/accounts/nobody/send", sendBody()));
    const stopped = await errorOf(await sender.post("/v1/accounts/acc-1/send", sendBody()));

    assert.deepEqual([missing.status, missing.kind], [409, "not_running"]);
    assert.deepEqual([stopped.status, stopped.kind], [409, "not_running"]);
    assert.equal(fake.callsTo("sendMessage").length, 0);
  });

  it("styles_are_attached_only_when_non_empty", async () => {
    const { sender, fake } = await running();
    await sender.post("/v1/accounts/acc-1/send", sendBody({ styles: [] }));
    await sender.post(
      "/v1/accounts/acc-1/send",
      sendBody({ styles: [{ start: 0, len: 4, st: "b" }] }),
    );

    const [empty, styled] = fake
      .callsTo("sendMessage")
      .map((call) => call.args[0] as Record<string, unknown>);

    assert.equal("styles" in (empty ?? {}), false);
    assert.deepEqual(styled?.["styles"], [{ start: 0, len: 4, st: "b" }]);
  });

  it("a_quote_is_attached_only_when_present", async () => {
    const { sender, fake } = await running();
    const quote = {
      content: "tin gốc",
      msgType: "webchat",
      uidFrom: "2000001",
      msgId: "m1",
      cliMsgId: 77,
      ts: 1_700_000_000_000,
      ttl: 0,
    };
    await sender.post("/v1/accounts/acc-1/send", sendBody());
    await sender.post("/v1/accounts/acc-1/send", sendBody({ quote }));

    const [plain, quoted] = fake
      .callsTo("sendMessage")
      .map((call) => call.args[0] as Record<string, unknown>);

    assert.equal("quote" in (plain ?? {}), false);
    assert.deepEqual(quoted?.["quote"], { ...quote, cliMsgId: "77", ts: "1700000000000" });
  });

  it("mentions_are_forwarded_when_given_and_omitted_when_empty_or_absent", async () => {
    const { sender, fake } = await running();
    const mentions = [{ pos: 0, uid: "2000002", len: 5 }];
    await sender.post("/v1/accounts/acc-1/send", sendBody({ mentions }));
    await sender.post("/v1/accounts/acc-1/send", sendBody({ mentions: [] }));
    await sender.post("/v1/accounts/acc-1/send", sendBody());

    const [given, empty, absent] = fake
      .callsTo("sendMessage")
      .map((call) => call.args[0] as Record<string, unknown>);

    assert.deepEqual(given?.["mentions"], mentions);
    assert.equal("mentions" in (empty ?? {}), false);
    assert.equal("mentions" in (absent ?? {}), false);
  });

  it("more_than_twenty_mentions_or_a_negative_position_is_a_422", async () => {
    const { sender } = await running();
    const many = Array.from({ length: 21 }, (_, index) => ({ pos: index, uid: "2000002", len: 1 }));
    const tooMany = await errorOf(
      await sender.post("/v1/accounts/acc-1/send", sendBody({ mentions: many })),
    );
    const negative = await errorOf(
      await sender.post(
        "/v1/accounts/acc-1/send",
        sendBody({ mentions: [{ pos: -1, uid: "2000002", len: 1 }] }),
      ),
    );
    assert.deepEqual([tooMany.status, negative.status], [422, 422]);
  });

  it("a_body_missing_proactive_or_with_a_bad_thread_type_is_a_422_and_zalo_is_not_called", async () => {
    const { sender, fake } = await running();
    const withoutProactive: Record<string, unknown> = { ...sendBody() };
    delete withoutProactive.proactive;

    const first = await sender.post("/v1/accounts/acc-1/send", withoutProactive);
    const second = await sender.post("/v1/accounts/acc-1/send", sendBody({ thread_type: 2 }));
    const third = await sender.post("/v1/accounts/acc-1/send", sendBody({ text: "" }));
    const fourth = await sender.post(
      "/v1/accounts/acc-1/send",
      sendBody({ styles: [{ start: 0, len: 1, st: "zz" }] }),
    );

    assert.deepEqual(
      [first.status, second.status, third.status, fourth.status],
      [422, 422, 422, 422],
    );
    assert.equal(fake.callsTo("sendMessage").length, 0);
  });

  it("the_per_minute_ceiling_answers_429_rate_limited_until_the_minute_slides", async () => {
    const { sender, clock, fake } = await running({ maxSendsPerMinutePerAccount: 2 });
    await sender.post("/v1/accounts/acc-1/send", sendBody());
    await sender.post("/v1/accounts/acc-1/send", sendBody());

    const refused = await errorOf(await sender.post("/v1/accounts/acc-1/send", sendBody()));
    assert.deepEqual([refused.status, refused.kind], [429, "rate_limited"]);
    assert.equal(fake.callsTo("sendMessage").length, 2);

    clock.now += 60_000;
    assert.equal((await sender.post("/v1/accounts/acc-1/send", sendBody())).status, 200);
  });

  it("the_daily_proactive_ceiling_answers_429_but_a_reply_still_goes_out", async () => {
    const { sender, fake } = await running({ maxProactivePerDayPerAccount: 2 });
    await sender.post("/v1/accounts/acc-1/send", sendBody({ proactive: true }));
    await sender.post("/v1/accounts/acc-1/send", sendBody({ proactive: true }));

    const refused = await errorOf(
      await sender.post("/v1/accounts/acc-1/send", sendBody({ proactive: true })),
    );
    const reply = await sender.post("/v1/accounts/acc-1/send", sendBody());

    assert.deepEqual([refused.status, refused.kind], [429, "rate_limited"]);
    assert.equal(reply.status, 200);
    assert.equal(fake.callsTo("sendMessage").length, 3);
  });

  it("the_daily_ceiling_follows_the_day_of_the_configured_time_zone", async () => {
    const { sender, clock } = await running({
      maxProactivePerDayPerAccount: 1,
      maxSendsPerMinutePerAccount: 100,
    });
    clock.now = Date.parse("2026-10-01T16:59:00Z"); // 23:59 in Ho Chi Minh
    await sender.post("/v1/accounts/acc-1/send", sendBody({ proactive: true }));
    assert.equal(
      (await sender.post("/v1/accounts/acc-1/send", sendBody({ proactive: true }))).status,
      429,
    );

    clock.now = Date.parse("2026-10-01T17:01:00Z"); // 00:01 next day
    assert.equal(
      (await sender.post("/v1/accounts/acc-1/send", sendBody({ proactive: true }))).status,
      200,
    );
  });

  it("a_failed_proactive_send_refunds_its_daily_slot", async () => {
    let fail = true;
    const { sender, bridge } = await running(
      { maxProactivePerDayPerAccount: 1 },
      {
        sendMessage: async () => {
          if (fail) throw new Error("network down");
          return { message: { msgId: 5 }, attachment: [] };
        },
      },
    );

    const failed = await errorOf(
      await sender.post("/v1/accounts/acc-1/send", sendBody({ proactive: true })),
    );
    assert.deepEqual([failed.status, failed.kind], [502, "transport"]);
    assert.equal(bridge.accounts.list()[0]?.proactive_sent_today, 0);

    fail = false;
    assert.equal(
      (await sender.post("/v1/accounts/acc-1/send", sendBody({ proactive: true }))).status,
      200,
    );
  });

  it("a_rejection_by_zalo_answers_502_zalo_rejected_with_the_numeric_code", async () => {
    const { sender } = await running(
      {},
      {
        sendMessage: async () => {
          throw new ZaloApiError("bad style", 112);
        },
      },
    );
    const result = await errorOf(await sender.post("/v1/accounts/acc-1/send", sendBody()));
    assert.deepEqual([result.status, result.kind, result.code], [502, "zalo_rejected", 112]);
  });

  it("a_failure_without_a_code_answers_502_transport", async () => {
    const { sender } = await running(
      {},
      {
        sendMessage: async () => {
          throw new Error("ETIMEDOUT");
        },
      },
    );
    const result = await errorOf(await sender.post("/v1/accounts/acc-1/send", sendBody()));
    assert.deepEqual([result.status, result.kind, result.code], [502, "transport", undefined]);
  });

  it("the_gates_are_checked_in_order_kill_switch_then_breaker_then_ceilings", async () => {
    const { sender, bridge } = await running({
      blockAfterRejectedSends: 1,
      maxSendsPerMinutePerAccount: 1,
    });
    const account = bridge.accounts.get("acc-1");
    assert.ok(account);
    account.safety.failed({ proactive: false, dayKey: "x" }, true); // opens the breaker

    const blocked = await errorOf(await sender.post("/v1/accounts/acc-1/send", sendBody()));
    await sender.post("/v1/kill-switch", { on: true, scope: "all" });
    const killed = await errorOf(await sender.post("/v1/accounts/acc-1/send", sendBody()));

    assert.equal(blocked.kind, "blocked");
    assert.equal(killed.kind, "kill_switch", "the kill switch wins over the breaker");
  });
});

describe("app: breaker", () => {
  let rejectedCalls = 0;
  const rejecting = {
    sendMessage: async () => {
      rejectedCalls += 1;
      throw new ZaloApiError("rejected", 112);
    },
  };

  it("consecutive_rejections_block_the_account_and_report_account_state_blocked_once", async () => {
    rejectedCalls = 0;
    const { sender, publisher } = await running({ blockAfterRejectedSends: 3 }, rejecting);

    const statuses = await Promise.all(
      [1, 2, 3].map(async () => (await sender.post("/v1/accounts/acc-1/send", sendBody())).status),
    );
    const after = await errorOf(await sender.post("/v1/accounts/acc-1/send", sendBody()));

    assert.deepEqual(statuses, [502, 502, 502]);
    assert.deepEqual([after.status, after.kind], [409, "blocked"]);
    assert.equal(rejectedCalls, 3, "the fourth send never reached zca-js");
    assert.deepEqual(publisher.ofType("account_state"), [
      { type: "account_state", state: "blocked", reason: "send_rejected_repeatedly" },
    ]);
  });

  it("a_blocked_account_reads_blocked_in_state_and_list", async () => {
    const { sender } = await running({ blockAfterRejectedSends: 1 }, rejecting);
    await sender.post("/v1/accounts/acc-1/send", sendBody());

    const state = await readEnvelope(await sender.get("/v1/accounts/acc-1/state"));
    const list = (await readEnvelope(await sender.get("/v1/accounts")))["accounts"] as Array<{
      state: string;
    }>;

    assert.equal(state["state"], "blocked");
    assert.equal(list[0]?.state, "blocked");
  });

  it("a_successful_send_resets_the_count_so_the_breaker_stays_closed", async () => {
    let reject = true;
    const { sender, publisher } = await running(
      { blockAfterRejectedSends: 3, maxSendsPerMinutePerAccount: 100 },
      {
        sendMessage: async () => {
          if (reject) throw new ZaloApiError("rejected", 112);
          return { message: { msgId: 1 }, attachment: [] };
        },
      },
    );

    await sender.post("/v1/accounts/acc-1/send", sendBody());
    await sender.post("/v1/accounts/acc-1/send", sendBody());
    reject = false;
    await sender.post("/v1/accounts/acc-1/send", sendBody());
    reject = true;
    await sender.post("/v1/accounts/acc-1/send", sendBody());
    await sender.post("/v1/accounts/acc-1/send", sendBody());

    assert.equal(publisher.ofType("account_state").length, 0);
  });

  it("send_attachment_and_send_video_also_feed_the_breaker", async () => {
    const { sender } = await running(
      { blockAfterRejectedSends: 2 },
      {
        sendMessage: rejecting.sendMessage,
        sendVideo: async () => {
          throw new ZaloApiError("rejected", 114);
        },
      },
    );
    await sender.post("/v1/accounts/acc-1/send-attachment", {
      thread_id: "2000001",
      thread_type: 0,
      filename: "a.pdf",
      data_base64: Buffer.from("x").toString("base64"),
      caption: "",
      proactive: false,
    });
    await sender.post("/v1/accounts/acc-1/send-video", {
      thread_id: "2000001",
      thread_type: 0,
      video_url: "https://videos.example.test/a.mp4",
      caption: "",
      proactive: false,
    });

    const after = await errorOf(await sender.post("/v1/accounts/acc-1/send", sendBody()));
    assert.equal(after.kind, "blocked");
  });

  it("blocked_clears_on_a_new_start", async () => {
    const { sender, gateway } = await running({ blockAfterRejectedSends: 1 }, rejecting);
    await sender.post("/v1/accounts/acc-1/send", sendBody());
    assert.equal(
      (await errorOf(await sender.post("/v1/accounts/acc-1/send", sendBody()))).kind,
      "blocked",
    );

    gateway.nextSessions.push(createFakeSession(createFakeApi()));
    await sender.post("/v1/accounts/acc-1/start", startBody);

    assert.equal((await sender.post("/v1/accounts/acc-1/send", sendBody())).status, 200);
  });

  it("blocked_clears_on_a_new_qr_login", async () => {
    const { sender, gateway } = await running({ blockAfterRejectedSends: 1 }, rejecting);
    await sender.post("/v1/accounts/acc-1/send", sendBody());

    await sender.post("/v1/accounts/acc-1/login/qr", { clinic_slug: "clinic-a" });
    gateway.qrControls[0]?.succeed(createFakeSession(createFakeApi()));
    await doiChoDenKhi(
      async () =>
        (await readEnvelope(await sender.get("/v1/accounts/acc-1/state")))["state"] ===
        "connecting",
      { moTa: "account re-attached after the QR login" },
    );

    assert.equal((await sender.post("/v1/accounts/acc-1/send", sendBody())).status, 200);
  });
});

describe("app: send-attachment", () => {
  const attachmentBody = (overrides: Record<string, unknown> = {}) => ({
    thread_id: "2000001",
    thread_type: 0,
    filename: "huong-dan.pdf",
    data_base64: Buffer.from("noi dung tong hop").toString("base64"),
    caption: "Tài liệu",
    proactive: false,
    ...overrides,
  });

  it("the_file_is_sent_from_memory_with_its_caption_and_size", async () => {
    const { sender, fake } = await running();

    const response = await sender.post("/v1/accounts/acc-1/send-attachment", attachmentBody());

    assert.equal(response.status, 200);
    const [payload, threadId, type] = fake.callsTo("sendMessage")[0]?.args as [
      {
        msg: string;
        attachments: Array<{ data: Buffer; filename: string; metadata: { totalSize: number } }>;
      },
      string,
      number,
    ];
    assert.equal(payload.msg, "Tài liệu");
    assert.equal(payload.attachments[0]?.filename, "huong-dan.pdf");
    assert.equal(payload.attachments[0]?.data.toString(), "noi dung tong hop");
    assert.equal(payload.attachments[0]?.metadata.totalSize, "noi dung tong hop".length);
    assert.deepEqual([threadId, type], ["2000001", 0]);
  });

  it("an_image_gets_its_width_and_height_measured", async () => {
    const { sender, fake } = await running();
    await sender.post(
      "/v1/accounts/acc-1/send-attachment",
      attachmentBody({ filename: "anh.png", data_base64: TINY_PNG_BASE64 }),
    );
    const [payload] = fake.callsTo("sendMessage")[0]?.args as [
      { attachments: Array<{ metadata: { width?: number; height?: number } }> },
    ];
    assert.deepEqual(
      [payload.attachments[0]?.metadata.width, payload.attachments[0]?.metadata.height],
      [1, 1],
    );
  });

  it("a_file_over_10_mb_decoded_is_refused_before_zalo_is_called", async () => {
    const { sender, fake } = await running();
    const tooBig = Buffer.alloc(10 * 1024 * 1024 + 1).toString("base64");

    const result = await errorOf(
      await sender.post(
        "/v1/accounts/acc-1/send-attachment",
        attachmentBody({ data_base64: tooBig }),
      ),
    );

    assert.deepEqual([result.status, result.kind], [422, "bad_request"]);
    assert.equal(fake.callsTo("sendMessage").length, 0);
  });

  it("a_file_of_exactly_10_mb_is_accepted", async () => {
    const { sender } = await running();
    const exactly = Buffer.alloc(10 * 1024 * 1024).toString("base64");
    assert.ok(exactly.length < MAX_BODY_BYTES);
    const response = await sender.post(
      "/v1/accounts/acc-1/send-attachment",
      attachmentBody({ data_base64: exactly }),
    );
    assert.equal(response.status, 200);
  });

  it("text_that_is_not_base64_is_refused", async () => {
    const { sender } = await running();
    const result = await errorOf(
      await sender.post(
        "/v1/accounts/acc-1/send-attachment",
        attachmentBody({ data_base64: "not base64 !!" }),
      ),
    );
    assert.equal(result.status, 422);
  });

  it("a_filename_with_a_path_is_refused", async () => {
    const { sender } = await running();
    const result = await errorOf(
      await sender.post(
        "/v1/accounts/acc-1/send-attachment",
        attachmentBody({ filename: "../etc/passwd.txt" }),
      ),
    );
    assert.equal(result.status, 422);
  });

  it("an_attachment_obeys_the_same_gates_as_a_text_send", async () => {
    const { sender, fake } = await running();
    await sender.post("/v1/kill-switch", { on: true, scope: "proactive" });

    const proactive = await errorOf(
      await sender.post("/v1/accounts/acc-1/send-attachment", attachmentBody({ proactive: true })),
    );

    assert.equal(proactive.kind, "kill_switch");
    assert.equal(fake.callsTo("sendMessage").length, 0);
  });

  it("an_attachment_counts_toward_the_per_minute_ceiling", async () => {
    const { sender } = await running({ maxSendsPerMinutePerAccount: 1 });
    await sender.post("/v1/accounts/acc-1/send-attachment", attachmentBody());
    const second = await errorOf(await sender.post("/v1/accounts/acc-1/send", sendBody()));
    assert.equal(second.kind, "rate_limited");
  });
});

describe("app: send-video", () => {
  const videoBody = (overrides: Record<string, unknown> = {}) => ({
    thread_id: "2000001",
    thread_type: 0,
    video_url: "https://videos.example.test/huong-dan.mp4",
    caption: "Video hướng dẫn",
    proactive: false,
    ...overrides,
  });

  it("the_video_url_and_caption_are_forwarded_to_zalo", async () => {
    const { sender, fake } = await running();

    const response = await sender.post(
      "/v1/accounts/acc-1/send-video",
      videoBody({ thumbnail_url: "https://videos.example.test/t.jpg" }),
    );

    assert.deepEqual(await response.json(), { ok: true, msg_id: "222" });
    assert.deepEqual(fake.callsTo("sendVideo")[0]?.args, [
      {
        msg: "Video hướng dẫn",
        videoUrl: "https://videos.example.test/huong-dan.mp4",
        thumbnailUrl: "https://videos.example.test/t.jpg",
      },
      "2000001",
      0,
    ]);
  });

  it("urls_that_point_inside_the_network_are_refused_before_zalo_is_called", async () => {
    const { sender, fake } = await running();
    const urls = [
      "http://127.0.0.1/a.mp4",
      "http://localhost/a.mp4",
      "http://169.254.169.254/latest/meta-data",
      "http://10.0.0.5/a.mp4",
      "http://[::1]/a.mp4",
      "ftp://videos.example.test/a.mp4",
      "https://user:pass@videos.example.test/a.mp4",
    ];

    const statuses = await Promise.all(
      urls.map(
        async (url) =>
          (await sender.post("/v1/accounts/acc-1/send-video", videoBody({ video_url: url })))
            .status,
      ),
    );

    assert.deepEqual(
      statuses,
      urls.map(() => 422),
    );
    assert.equal(fake.callsTo("sendVideo").length, 0);
  });

  it("a_host_that_resolves_to_a_private_address_is_refused", async () => {
    const gateway = new FakeGateway();
    const fake = createFakeApi();
    const bridge = createBridge({
      config: makeConfig(),
      gateway,
      publisher: new RecordingPublisher(),
      lookupHost: async () => ["10.1.2.3"],
    });
    const sender = signedSender(bridge.app);
    gateway.nextSessions.push(createFakeSession(fake));
    await sender.post("/v1/accounts/acc-1/start", startBody);

    const response = await sender.post("/v1/accounts/acc-1/send-video", videoBody());

    assert.equal(response.status, 422);
    assert.equal(fake.callsTo("sendVideo").length, 0);
  });

  it("a_video_obeys_the_same_gates_as_a_text_send", async () => {
    const { sender, fake } = await running();
    await sender.post("/v1/kill-switch", { on: true, scope: "all" });

    const result = await errorOf(await sender.post("/v1/accounts/acc-1/send-video", videoBody()));

    assert.equal(result.kind, "kill_switch");
    assert.equal(fake.callsTo("sendVideo").length, 0);
  });
});

describe("app: typing, receipts and reactions", () => {
  const params = [
    {
      msgId: "m1",
      cliMsgId: "c1",
      uidFrom: "2000001",
      idTo: "1000001",
      msgType: "webchat",
      st: 3,
      at: 0,
      cmd: 501,
      ts: "1700000000000",
    },
  ];

  it("typing_sends_one_typing_event", async () => {
    const { sender, fake } = await running();
    const response = await sender.post("/v1/accounts/acc-1/typing", {
      thread_id: "2000001",
      thread_type: 1,
    });
    assert.equal(response.status, 200);
    assert.deepEqual(fake.callsTo("sendTypingEvent")[0]?.args, ["2000001", 1]);
  });

  it("delivered_receipts_pass_is_seen_false_and_the_nine_fields", async () => {
    const { sender, fake } = await running();
    await sender.post("/v1/accounts/acc-1/receipts/delivered", {
      is_seen: false,
      params,
      thread_type: 0,
    });
    assert.deepEqual(fake.callsTo("sendDeliveredEvent")[0]?.args, [false, params, 0]);
  });

  it("seen_receipts_pass_the_params_and_the_thread_type", async () => {
    const { sender, fake } = await running();
    await sender.post("/v1/accounts/acc-1/receipts/seen", { params, thread_type: 1 });
    assert.deepEqual(fake.callsTo("sendSeenEvent")[0]?.args, [params, 1]);
  });

  it("more_than_fifty_receipts_in_one_call_is_a_422", async () => {
    const { sender } = await running();
    const many = Array.from({ length: 51 }, () => params[0]);
    const result = await errorOf(
      await sender.post("/v1/accounts/acc-1/receipts/seen", { params: many, thread_type: 0 }),
    );
    assert.equal(result.status, 422);
  });

  it("a_reaction_maps_its_key_to_the_zalo_icon", async () => {
    const { sender, fake } = await running();
    await sender.post("/v1/accounts/acc-1/reaction", {
      icon_key: "like",
      msg_id: "m1",
      cli_msg_id: "c1",
      thread_id: "2000001",
      thread_type: 0,
    });
    assert.deepEqual(fake.callsTo("addReaction")[0]?.args, [
      Reactions.LIKE,
      { data: { msgId: "m1", cliMsgId: "c1" }, threadId: "2000001", type: 0 },
    ]);
  });

  it("an_unknown_reaction_key_falls_back_to_the_heart", async () => {
    const { sender, fake } = await running();
    await sender.post("/v1/accounts/acc-1/reaction", {
      icon_key: "constructor",
      msg_id: "m1",
      cli_msg_id: "c1",
      thread_id: "2000001",
      thread_type: 0,
    });
    assert.equal(fake.callsTo("addReaction")[0]?.args[0], Reactions.HEART);
  });

  it("calls_for_an_account_that_is_not_running_answer_not_running", async () => {
    const { sender } = build();
    const result = await errorOf(
      await sender.post("/v1/accounts/nobody/typing", { thread_id: "1", thread_type: 0 }),
    );
    assert.deepEqual([result.status, result.kind], [409, "not_running"]);
  });

  it("a_zalo_failure_on_typing_is_mapped_like_any_other", async () => {
    const { sender } = await running(
      {},
      {
        sendTypingEvent: async () => {
          throw new ZaloApiError("no", 200);
        },
      },
    );
    const result = await errorOf(
      await sender.post("/v1/accounts/acc-1/typing", { thread_id: "2000001", thread_type: 0 }),
    );
    assert.deepEqual([result.status, result.kind, result.code], [502, "zalo_rejected", 200]);
  });
});

describe("app: directory and friends", () => {
  it("user_info_answers_what_zalo_returned", async () => {
    const { sender, fake } = await running();
    const response = await sender.get("/v1/accounts/acc-1/user-info?uid=2000001");
    assert.equal(response.status, 200);
    assert.deepEqual(fake.callsTo("getUserInfo")[0]?.args, ["2000001"]);
    assert.deepEqual(((await response.json()) as { data: unknown }).data, {
      unchanged_profiles: {},
      phonebook_version: 0,
      changed_profiles: {},
    });
  });

  it("user_info_without_a_uid_is_a_422", async () => {
    const { sender } = await running();
    assert.equal((await sender.get("/v1/accounts/acc-1/user-info")).status, 422);
  });

  it("friends_returns_only_user_id_display_name_and_zalo_name", async () => {
    const richUser = {
      userId: "2000001",
      displayName: "Bạn Thử Nghiệm",
      zaloName: "ban.thu",
      phoneNumber: "0900000000",
      dob: "01/01/1990",
      avatar: "https://example.test/a.png",
      gender: 0,
    };
    // The synthetic user lacks the library's many unrelated `User` fields, hence the cast.
    const { sender } = await running({}, { getAllFriends: async () => [richUser] as never });

    const body = await readEnvelope(await sender.get("/v1/accounts/acc-1/friends"));

    assert.deepEqual(body["friends"], [
      { userId: "2000001", displayName: "Bạn Thử Nghiệm", zaloName: "ban.thu" },
    ]);
    assert.equal(JSON.stringify(body).includes("0900000000"), false);
    assert.equal(JSON.stringify(body).includes("1990"), false);
  });

  it("accept_and_reject_pass_the_uid_to_zalo", async () => {
    const { sender, fake } = await running();
    assert.equal(
      (await sender.post("/v1/accounts/acc-1/friends/accept", { uid: "2000007" })).status,
      200,
    );
    assert.equal(
      (await sender.post("/v1/accounts/acc-1/friends/reject", { uid: "2000008" })).status,
      200,
    );
    assert.deepEqual(fake.callsTo("acceptFriendRequest")[0]?.args, ["2000007"]);
    assert.deepEqual(fake.callsTo("rejectFriendRequest")[0]?.args, ["2000008"]);
  });

  it("accept_without_a_uid_is_a_422_and_a_zalo_failure_is_a_502", async () => {
    const { sender } = await running(
      {},
      {
        acceptFriendRequest: async () => {
          throw new Error("boom");
        },
      },
    );
    assert.equal((await sender.post("/v1/accounts/acc-1/friends/accept", {})).status, 422);
    assert.equal(
      (await sender.post("/v1/accounts/acc-1/friends/accept", { uid: "2000007" })).status,
      502,
    );
  });

  it("group_info_passes_the_thread_id", async () => {
    const { sender, fake } = await running();
    const response = await sender.get("/v1/accounts/acc-1/group-info?thread_id=3000001");
    assert.equal(response.status, 200);
    assert.deepEqual(fake.callsTo("getGroupInfo")[0]?.args, ["3000001"]);
  });
});

describe("app: QR login", () => {
  it("a_qr_login_goes_from_starting_to_waiting_scan_to_success_and_the_account_runs", async () => {
    const { sender, gateway, publisher } = build();

    const started = await readEnvelope(
      await sender.post("/v1/accounts/acc-1/login/qr", { clinic_slug: "clinic-a" }),
    );
    assert.equal(started["state"], "starting");

    gateway.qrControls[0]?.emit({ type: "qr", qrBase64: "QR_PNG_BASE64" });
    const waiting = await readEnvelope(await sender.get("/v1/accounts/acc-1/login/qr"));
    assert.deepEqual(
      [waiting["state"], waiting["qr_png_base64"]],
      ["waiting_scan", "QR_PNG_BASE64"],
    );

    gateway.qrControls[0]?.emit({ type: "scanned" });
    assert.equal(
      (await readEnvelope(await sender.get("/v1/accounts/acc-1/login/qr")))["state"],
      "scanned",
    );

    gateway.qrControls[0]?.succeed(createFakeSession(createFakeApi(), "1000099"));
    await doiChoDenKhi(
      async () =>
        (await readEnvelope(await sender.get("/v1/accounts/acc-1/login/qr")))["state"] ===
        "success",
      { moTa: "QR status success" },
    );

    const done = await readEnvelope(await sender.get("/v1/accounts/acc-1/login/qr"));
    assert.equal(done["qr_png_base64"], undefined, "the QR is dropped once the login is done");
    assert.equal(
      (await readEnvelope(await sender.get("/v1/accounts/acc-1/state")))["state"],
      "connecting",
    );
    assert.deepEqual(publisher.ofType("credential_updated"), [
      { type: "credential_updated", credential: TEST_CREDENTIAL },
    ]);
  });

  it("a_declined_login_reads_declined", async () => {
    const { sender, gateway } = build();
    await sender.post("/v1/accounts/acc-1/login/qr", { clinic_slug: "clinic-a" });
    gateway.qrControls[0]?.emit({ type: "declined" });
    assert.equal(
      (await readEnvelope(await sender.get("/v1/accounts/acc-1/login/qr")))["state"],
      "declined",
    );
  });

  it("an_account_without_a_session_reads_idle", async () => {
    const { sender } = build();
    assert.equal(
      (await readEnvelope(await sender.get("/v1/accounts/acc-9/login/qr")))["state"],
      "idle",
    );
  });

  it("a_qr_session_times_out_after_three_minutes", async () => {
    const { sender, gateway, clock } = build();
    await sender.post("/v1/accounts/acc-1/login/qr", { clinic_slug: "clinic-a" });
    gateway.qrControls[0]?.emit({ type: "qr", qrBase64: "QR" });

    clock.now += 3 * 60_000;
    // The signed timestamp follows the same clock, so the request is still inside the 300 s window.
    const status = await readEnvelope(await sender.get("/v1/accounts/acc-1/login/qr"));

    assert.equal(status["state"], "timeout");
    assert.equal(gateway.qrControls[0]?.signal.aborted, true);
  });

  it("a_second_qr_login_supersedes_a_dead_one_and_aborts_it", async () => {
    const { sender, gateway } = build();
    await sender.post("/v1/accounts/acc-1/login/qr", { clinic_slug: "clinic-a" });
    gateway.qrControls[0]?.emit({ type: "declined" });

    await sender.post("/v1/accounts/acc-1/login/qr", { clinic_slug: "clinic-a" });

    assert.equal(gateway.qrControls.length, 2);
    assert.equal(gateway.qrControls[0]?.signal.aborted, true);
  });

  it("the_qr_login_without_a_clinic_slug_is_a_422", async () => {
    const { sender } = build();
    assert.equal((await sender.post("/v1/accounts/acc-1/login/qr", {})).status, 422);
  });
});
