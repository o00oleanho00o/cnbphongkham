// New tests: the original `account-manager.ts` ran in-process against a database. These drive the bridge's
// version of it (`AccountManager`) with a fake gateway, fake listeners and a recording publisher.
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it, mock } from "node:test";
import { CloseReason, FriendEventType } from "zca-js";
import { AccountManager } from "./account-registry.js";
import { ON_DINH_MS } from "./reconnect-planner.js";
import {
  FakeGateway,
  RecordingPublisher,
  TEST_CREDENTIAL,
  createFakeApi,
  createFakeSession,
  fakeFriendEvent,
  fakeUserMessage,
  makeConfig,
} from "./test-support.js";

function setup(configOverrides = {}) {
  const gateway = new FakeGateway();
  const publisher = new RecordingPublisher();
  const manager = new AccountManager({
    config: makeConfig(configOverrides),
    gateway,
    publisher,
  });
  return { gateway, publisher, manager };
}

async function startWithFake(manager: AccountManager, gateway: FakeGateway, accountId = "acc-1") {
  const fake = createFakeApi();
  gateway.nextSessions.push(createFakeSession(fake));
  await manager.start(accountId, "clinic-a", TEST_CREDENTIAL);
  return fake;
}

describe("AccountManager: start and stop", () => {
  it("start_logs_in_with_the_credential_and_reports_the_own_id", async () => {
    const { gateway, manager } = setup();
    gateway.nextSessions.push(createFakeSession(createFakeApi(), "1000042"));

    const result = await manager.start("acc-1", "clinic-a", TEST_CREDENTIAL);

    assert.equal(result.ownId, "1000042");
    assert.deepEqual(gateway.loginCalls, [TEST_CREDENTIAL]);
    assert.deepEqual(manager.list(), [
      { account_id: "acc-1", state: "connecting", own_id: "1000042", proactive_sent_today: 0 },
    ]);
  });

  it("start_replaces_a_running_account_of_the_same_id", async () => {
    const { gateway, manager } = setup();
    const first = await startWithFake(manager, gateway);

    const second = await startWithFake(manager, gateway);

    assert.equal(first.listener.stops >= 1, true, "the old listener was stopped");
    assert.equal(second.listener.starts, 1);
    assert.equal(manager.list().length, 1);
  });

  it("a_failed_login_leaves_the_account_stopped_and_rethrows", async () => {
    const { gateway, manager } = setup();
    gateway.loginError = new Error("bad cookie");

    await assert.rejects(manager.start("acc-1", "clinic-a", TEST_CREDENTIAL), /bad cookie/);

    assert.equal(manager.get("acc-1")?.state, "stopped");
    assert.equal(manager.activeCount(), 0);
  });

  it("a_listener_that_cannot_start_leaves_the_account_stopped_and_rethrows", async () => {
    const { gateway, manager } = setup();
    const fake = createFakeApi();
    fake.listener.failNextStart = true;
    gateway.nextSessions.push(createFakeSession(fake));

    await assert.rejects(manager.start("acc-1", "clinic-a", TEST_CREDENTIAL), /start failed/);

    assert.equal(manager.get("acc-1")?.state, "stopped");
  });

  it("stop_stops_the_listener_and_the_account_reads_stopped", async () => {
    const { gateway, manager } = setup();
    const fake = await startWithFake(manager, gateway);

    await manager.stop("acc-1");

    assert.equal(fake.listener.stops >= 1, true);
    assert.equal(manager.get("acc-1")?.state, "stopped");
    assert.equal(manager.get("acc-1")?.canSend, false);
  });

  it("stop_all_stops_every_account", async () => {
    const { gateway, manager } = setup();
    await startWithFake(manager, gateway, "acc-1");
    await startWithFake(manager, gateway, "acc-2");

    await manager.stopAll();

    assert.equal(manager.activeCount(), 0);
    assert.deepEqual(
      manager.list().map((account) => account.state),
      ["stopped", "stopped"],
    );
  });

  it("two_starts_of_the_same_account_run_one_after_the_other", async () => {
    const { gateway, manager } = setup();
    gateway.holdLogin();
    const first = createFakeApi();
    const second = createFakeApi();
    gateway.nextSessions.push(createFakeSession(first), createFakeSession(second));

    const pendingFirst = manager.start("acc-1", "clinic-a", TEST_CREDENTIAL);
    const pendingSecond = manager.start("acc-1", "clinic-a", TEST_CREDENTIAL);
    gateway.releaseLogin();
    await Promise.all([pendingFirst, pendingSecond]);

    assert.equal(
      first.listener.stops >= 1,
      true,
      "the first attachment was replaced by the second",
    );
    assert.equal(manager.get("acc-1")?.api, second.api);
  });
});

describe("AccountManager: events to the API", () => {
  it("a_listener_message_is_published_with_the_own_id_and_the_clinic_target", async () => {
    const { gateway, publisher, manager } = setup();
    const fake = createFakeApi();
    gateway.nextSessions.push(createFakeSession(fake, "1000042"));
    await manager.start("acc-1", "clinic-a", TEST_CREDENTIAL);
    const message = fakeUserMessage();

    fake.listener.emitMessage(message);

    assert.deepEqual(publisher.events, [
      {
        target: { accountId: "acc-1", clinicSlug: "clinic-a" },
        event: { type: "message", self_id: "1000042", message },
      },
    ]);
  });

  it("a_friend_event_is_published_with_its_kind_by_enum_name", async () => {
    const { gateway, publisher, manager } = setup();
    const fake = await startWithFake(manager, gateway);

    fake.listener.emitFriendEvent(fakeFriendEvent(FriendEventType.REQUEST, "2000009"));

    assert.deepEqual(
      publisher.ofType("friend_event").map((event) => event.event.kind),
      ["request"],
    );
    assert.equal(publisher.ofType("friend_event")[0]?.event.thread_id, "2000009");
  });

  it("events_of_a_stopped_attachment_are_not_published", async () => {
    const { gateway, publisher, manager } = setup();
    const fake = await startWithFake(manager, gateway);
    await manager.stop("acc-1");

    fake.listener.emitMessage(fakeUserMessage());

    assert.equal(publisher.events.length, 0);
  });

  it("a_qr_login_publishes_the_new_credential_before_the_listener_starts", async () => {
    const { publisher, manager } = setup();
    const fake = createFakeApi();

    await manager.attachFromQr("acc-1", "clinic-a", createFakeSession(fake));

    assert.deepEqual(publisher.ofType("credential_updated"), [
      { type: "credential_updated", credential: TEST_CREDENTIAL },
    ]);
    assert.equal(fake.listener.starts, 1);
    assert.equal(manager.get("acc-1")?.state, "connecting");
  });

  it("a_plain_start_does_not_publish_the_credential_back", async () => {
    const { gateway, publisher, manager } = setup();
    await startWithFake(manager, gateway);
    assert.equal(publisher.ofType("credential_updated").length, 0);
  });
});

describe("AccountManager: reported state", () => {
  beforeEach(() => mock.timers.enable({ apis: ["setTimeout", "Date"], now: 0 }));
  afterEach(() => mock.timers.reset());

  it("connected_is_reported_only_after_the_connection_proved_stable", async () => {
    const { gateway, publisher, manager } = setup();
    const fake = await startWithFake(manager, gateway);

    fake.listener.emitConnected();
    assert.equal(manager.get("acc-1")?.state, "connected");
    mock.timers.tick(ON_DINH_MS - 1);
    assert.deepEqual(publisher.states(), []);
    mock.timers.tick(1);

    assert.deepEqual(publisher.states(), ["connected"]);
  });

  it("a_connection_that_drops_at_once_is_never_reported_connected_nor_disconnected", async () => {
    const { gateway, publisher, manager } = setup();
    const fake = await startWithFake(manager, gateway);

    fake.listener.emitConnected();
    mock.timers.tick(2);
    fake.listener.emitClosed(CloseReason.AbnormalClosure);
    mock.timers.tick(ON_DINH_MS * 2);

    assert.deepEqual(publisher.states(), []);
    assert.equal(manager.get("acc-1")?.state, "disconnected");
  });

  it("a_reported_connection_that_closes_is_reported_disconnected", async () => {
    const { gateway, publisher, manager } = setup();
    const fake = await startWithFake(manager, gateway);
    fake.listener.emitConnected();
    mock.timers.tick(ON_DINH_MS);

    fake.listener.emitClosed(CloseReason.AbnormalClosure);

    assert.deepEqual(publisher.states(), ["connected", "disconnected"]);
  });

  it("five_consecutive_flaps_report_session_dead_and_refuse_sends", async () => {
    const { gateway, publisher, manager } = setup();
    const fake = await startWithFake(manager, gateway);

    Array.from({ length: 5 }).forEach(() => {
      fake.listener.emitClosed(CloseReason.AbnormalClosure);
      mock.timers.tick(70_000);
    });

    assert.deepEqual(publisher.states(), ["session_dead"]);
    assert.equal(publisher.ofType("account_state")[0]?.reason, "reconnect_flapping");
    assert.equal(manager.get("acc-1")?.state, "session_dead");
    assert.equal(manager.get("acc-1")?.canSend, false);
  });

  it("repeated_kicks_report_logged_out", async () => {
    const { gateway, publisher, manager } = setup();
    const fake = await startWithFake(manager, gateway);

    Array.from({ length: 5 }).forEach(() => {
      fake.listener.emitClosed(CloseReason.KickConnection);
      mock.timers.tick(70_000);
    });

    assert.deepEqual(publisher.states(), ["logged_out"]);
    assert.equal(manager.get("acc-1")?.state, "logged_out");
  });

  it("a_stable_connection_after_a_dead_verdict_brings_the_account_back", async () => {
    const { gateway, publisher, manager } = setup();
    const fake = await startWithFake(manager, gateway);
    Array.from({ length: 5 }).forEach(() => {
      fake.listener.emitClosed(CloseReason.AbnormalClosure);
      mock.timers.tick(70_000);
    });

    fake.listener.emitConnected();
    mock.timers.tick(ON_DINH_MS);

    assert.deepEqual(publisher.states(), ["session_dead", "connected"]);
    assert.equal(manager.get("acc-1")?.canSend, true);
  });

  it("a_blocked_account_reports_blocked_and_the_state_wins_over_the_listener", async () => {
    const { gateway, publisher, manager } = setup();
    const fake = await startWithFake(manager, gateway);
    fake.listener.emitConnected();
    const account = manager.get("acc-1");
    assert.ok(account);

    Array.from({ length: 5 }).forEach(() =>
      account.safety.failed({ proactive: false, dayKey: "x" }, true),
    );
    manager.reportBlocked(account);
    mock.timers.tick(ON_DINH_MS);

    assert.deepEqual(
      publisher.states(),
      ["blocked"],
      "a blocked account is never reported connected",
    );
    assert.equal(account.state, "blocked");
  });

  it("blocked_clears_only_on_a_new_start", async () => {
    const { gateway, manager } = setup({ blockAfterRejectedSends: 1 });
    await startWithFake(manager, gateway);
    const account = manager.get("acc-1");
    assert.ok(account);
    account.safety.failed({ proactive: false, dayKey: "x" }, true);
    assert.equal(account.state, "blocked");

    await startWithFake(manager, gateway);

    assert.equal(manager.get("acc-1")?.state, "connecting");
  });

  it("the_daily_count_survives_a_restart_of_the_account", async () => {
    const { gateway, manager } = setup();
    await startWithFake(manager, gateway);
    manager.get("acc-1")?.safety.admit(true);

    await startWithFake(manager, gateway);

    assert.equal(manager.list()[0]?.proactive_sent_today, 1);
  });
});
