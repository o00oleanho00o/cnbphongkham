// New tests: the original `zalo-listener.ts` had none. They drive the listener with an injected fake
// `api.listener` and fake timers (node:test mock timers), so no socket and no real clock is involved.
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it, mock } from "node:test";
import { CloseReason, FriendEventType, type Message } from "zca-js";
import {
  SO_CHU_KY_CHO_THEM_TRUOC_KHI_BO_CUOC,
  startListener,
  type ListenerReport,
} from "./zalo-listener.js";
import { createFakeListener, fakeFriendEvent, fakeUserMessage, type FakeListener } from "./test-support.js";

const NO_JITTER = (): number => 0;
const FLAPS_TO_SUSPICION = 5;

type Harness = {
  listener: FakeListener;
  reports: ListenerReport[];
  messages: unknown[];
  stop: () => void;
};

function harness(options: { onMessage?: (m: unknown) => Promise<void> | void } = {}): Harness {
  const listener = createFakeListener();
  const reports: ListenerReport[] = [];
  const messages: unknown[] = [];
  const stop = startListener(
    "acc-1",
    { listener },
    options.onMessage ?? ((message) => void messages.push(message)),
    undefined,
    { onReport: (report) => reports.push(report), random: NO_JITTER },
  );
  return { listener, reports, messages, stop };
}

/** Close the connection and let the scheduled reconnect fire. */
function flap(listener: FakeListener, code: number = CloseReason.AbnormalClosure): void {
  listener.emitClosed(code);
  mock.timers.tick(70_000);
}

describe("startListener: reconnect with backoff", () => {
  beforeEach(() => mock.timers.enable({ apis: ["setTimeout", "Date"], now: 0 }));
  afterEach(() => mock.timers.reset());

  it("the_listener_is_started_once_on_boot", () => {
    const { listener } = harness();
    assert.equal(listener.starts, 1);
  });

  it("a_closed_connection_reconnects_after_the_base_backoff", () => {
    const { listener } = harness();

    listener.emitClosed(CloseReason.AbnormalClosure);
    mock.timers.tick(999);
    assert.equal(listener.starts, 1, "not yet");
    mock.timers.tick(1);

    assert.equal(listener.starts, 2);
  });

  it("each_consecutive_flap_doubles_the_wait", () => {
    const { listener } = harness();

    listener.emitClosed(CloseReason.AbnormalClosure);
    mock.timers.tick(1_000);
    listener.emitClosed(CloseReason.AbnormalClosure);
    mock.timers.tick(1_999);
    assert.equal(listener.starts, 2, "second wait is 2000 ms");
    mock.timers.tick(1);
    assert.equal(listener.starts, 3);

    listener.emitClosed(CloseReason.AbnormalClosure);
    mock.timers.tick(3_999);
    assert.equal(listener.starts, 3, "third wait is 4000 ms");
    mock.timers.tick(1);
    assert.equal(listener.starts, 4);
  });

  it("a_stable_connection_resets_the_wait_to_the_base", () => {
    const { listener } = harness();
    listener.emitClosed(CloseReason.AbnormalClosure);
    mock.timers.tick(1_000);
    listener.emitClosed(CloseReason.AbnormalClosure);
    mock.timers.tick(2_000);

    listener.emitConnected();
    mock.timers.tick(5_000);
    const before = listener.starts;
    listener.emitClosed(CloseReason.AbnormalClosure);
    mock.timers.tick(1_000);

    assert.equal(listener.starts, before + 1, "wait is back to 1000 ms");
  });

  it("a_connection_that_drops_at_once_does_not_reset_the_wait", () => {
    const { listener } = harness();
    listener.emitConnected();
    mock.timers.tick(2);
    listener.emitClosed(CloseReason.AbnormalClosure);
    mock.timers.tick(1_000);
    assert.equal(listener.starts, 2);

    listener.emitConnected();
    mock.timers.tick(2);
    listener.emitClosed(CloseReason.AbnormalClosure);
    mock.timers.tick(1_999);
    assert.equal(listener.starts, 2, "second wait is 2000 ms, not reset to 1000");
  });

  it("a_start_that_throws_counts_as_a_flap_and_is_retried_with_a_longer_wait", () => {
    const { listener } = harness();
    listener.emitClosed(CloseReason.AbnormalClosure);
    listener.failNextStart = true;
    mock.timers.tick(1_000);
    assert.equal(listener.starts, 2, "the reconnect attempt threw");

    mock.timers.tick(1_999);
    assert.equal(listener.starts, 2);
    mock.timers.tick(1);
    assert.equal(listener.starts, 3, "retried after the doubled wait, no silent dead loop");
  });

  it("the_old_socket_is_stopped_before_every_reconnect", () => {
    const { listener } = harness();
    listener.emitClosed(CloseReason.AbnormalClosure);
    mock.timers.tick(1_000);
    assert.equal(listener.stops, 1);
  });
});

describe("startListener: suspected dead session", () => {
  beforeEach(() => mock.timers.enable({ apis: ["setTimeout", "Date"], now: 0 }));
  afterEach(() => mock.timers.reset());

  it("below_the_threshold_nothing_but_disconnects_is_reported", () => {
    const { listener, reports } = harness();
    Array.from({ length: FLAPS_TO_SUSPICION - 1 }).forEach(() => flap(listener));

    assert.equal(
      reports.every((report) => report.state === "disconnected"),
      true,
    );
  });

  it("five_consecutive_flaps_report_session_dead_once_and_the_account_keeps_reconnecting", () => {
    const { listener, reports } = harness();
    Array.from({ length: FLAPS_TO_SUSPICION }).forEach(() => flap(listener));

    const dead = reports.filter((report) => report.state === "session_dead");
    assert.deepEqual(dead, [{ state: "session_dead", reason: "reconnect_flapping" }]);
    assert.equal(listener.starts, 1 + FLAPS_TO_SUSPICION, "the original behaviour holds: keep backing off");
  });

  it("the_report_waits_for_the_threshold_to_persist_before_giving_up", () => {
    const { listener } = harness();
    Array.from({ length: FLAPS_TO_SUSPICION + SO_CHU_KY_CHO_THEM_TRUOC_KHI_BO_CUOC - 1 }).forEach(() =>
      flap(listener),
    );
    const beforeLast = listener.starts;

    // The 3rd persisting cycle after the report: still reconnects.
    assert.equal(beforeLast, 1 + FLAPS_TO_SUSPICION + SO_CHU_KY_CHO_THEM_TRUOC_KHI_BO_CUOC - 1);
    flap(listener);
    assert.equal(listener.starts, beforeLast, "the next cycle gives up: no reconnect is scheduled");
  });

  it("after_giving_up_no_timer_is_left_to_reconnect", () => {
    const { listener } = harness();
    Array.from({ length: FLAPS_TO_SUSPICION + SO_CHU_KY_CHO_THEM_TRUOC_KHI_BO_CUOC }).forEach(() =>
      flap(listener),
    );
    const final = listener.starts;

    mock.timers.tick(10 * 60_000);

    assert.equal(listener.starts, final);
  });

  it("being_kicked_again_and_again_is_reported_as_logged_out", () => {
    const { listener, reports } = harness();
    Array.from({ length: FLAPS_TO_SUSPICION }).forEach(() => flap(listener, CloseReason.KickConnection));

    assert.deepEqual(
      reports.filter((report) => report.state === "logged_out"),
      [{ state: "logged_out", reason: "kicked_by_zalo" }],
    );
  });

  it("a_duplicate_connection_is_reported_as_session_dead_with_its_reason", () => {
    const { listener, reports } = harness();
    Array.from({ length: FLAPS_TO_SUSPICION }).forEach(() =>
      flap(listener, CloseReason.DuplicateConnection),
    );

    assert.deepEqual(
      reports.filter((report) => report.state === "session_dead"),
      [{ state: "session_dead", reason: "duplicate_connection" }],
    );
  });

  it("a_stable_connection_clears_the_suspicion_so_the_account_never_gives_up", () => {
    const { listener, reports } = harness();
    Array.from({ length: FLAPS_TO_SUSPICION }).forEach(() => flap(listener));

    listener.emitConnected();
    mock.timers.tick(5_000);
    listener.emitClosed(CloseReason.AbnormalClosure);
    mock.timers.tick(1_000);
    const afterRecovery = listener.starts;
    Array.from({ length: SO_CHU_KY_CHO_THEM_TRUOC_KHI_BO_CUOC + 1 }).forEach(() => flap(listener));

    assert.equal(reports.filter((report) => report.state === "connected").length, 1);
    assert.equal(
      listener.starts,
      afterRecovery + SO_CHU_KY_CHO_THEM_TRUOC_KHI_BO_CUOC + 1,
      "every flap after the recovery still reconnects",
    );
  });

  it("a_start_that_keeps_throwing_reaches_the_threshold_too", () => {
    const { listener, reports } = harness();
    listener.emitClosed(CloseReason.AbnormalClosure);
    const failEveryStart = (): void => {
      listener.failNextStart = true;
    };
    Array.from({ length: FLAPS_TO_SUSPICION }).forEach(() => {
      failEveryStart();
      mock.timers.tick(70_000);
    });

    assert.equal(reports.some((report) => report.state === "session_dead"), true);
  });
});

describe("startListener: lifecycle and handlers", () => {
  beforeEach(() => mock.timers.enable({ apis: ["setTimeout", "Date"], now: 0 }));
  afterEach(() => mock.timers.reset());

  it("connecting_is_reported", () => {
    const { listener, reports } = harness();
    listener.emitConnected();
    assert.deepEqual(reports, [{ state: "connected", reason: "connected" }]);
  });

  it("stopping_cancels_the_pending_reconnect", () => {
    const { listener, stop } = harness();
    listener.emitClosed(CloseReason.AbnormalClosure);

    stop();
    mock.timers.tick(70_000);

    assert.equal(listener.starts, 1);
    assert.equal(listener.stops >= 1, true);
  });

  it("a_close_after_stopping_is_ignored", () => {
    const { listener, reports, stop } = harness();
    stop();

    listener.emitClosed(CloseReason.ManualClosure);
    mock.timers.tick(70_000);

    assert.equal(listener.starts, 1);
    assert.deepEqual(reports, []);
  });

  it("stopping_twice_is_harmless", () => {
    const { listener, stop } = harness();
    listener.stop = () => {
      throw new Error("already closed");
    };
    assert.doesNotThrow(() => {
      stop();
      stop();
    });
  });

  it("a_message_reaches_the_handler", () => {
    const { listener, messages } = harness();
    const message = fakeUserMessage();
    listener.emitMessage(message);
    assert.deepEqual(messages, [message]);
  });

  it("a_failing_message_handler_does_not_break_the_listener", async () => {
    const seen: Message[] = [];
    const { listener } = harness({
      onMessage: async (message) => {
        seen.push(message as Message);
        throw new Error("handler failed");
      },
    });

    listener.emitMessage(fakeUserMessage());
    listener.emitMessage(fakeUserMessage("2000002"));
    await Promise.resolve();

    assert.equal(seen.length, 2);
  });

  it("friend_events_are_forwarded_only_when_a_handler_is_given", () => {
    const withoutHandler = createFakeListener();
    startListener("acc-2", { listener: withoutHandler }, () => undefined);
    assert.doesNotThrow(() => withoutHandler.emitFriendEvent(fakeFriendEvent(FriendEventType.ADD)));

    const withHandler = createFakeListener();
    const received: unknown[] = [];
    startListener("acc-3", { listener: withHandler }, () => undefined, (event) => void received.push(event));
    const event = fakeFriendEvent(FriendEventType.REQUEST);
    withHandler.emitFriendEvent(event);

    assert.deepEqual(received, [event]);
  });

  it("a_listener_error_is_logged_without_stopping_anything", () => {
    const { listener } = harness();
    assert.doesNotThrow(() => listener.emitError(new Error("socket error")));
    assert.equal(listener.starts, 1);
  });
});
