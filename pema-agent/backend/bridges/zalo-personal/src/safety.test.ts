import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { AccountSafety, KillSwitch, dayKey, type SafetyLimits } from "./safety.js";

const LIMITS: SafetyLimits = {
  maxSendsPerMinute: 3,
  maxProactivePerDay: 2,
  blockAfterRejectedSends: 3,
  timeZone: "Asia/Ho_Chi_Minh",
};

/** 2026-10-01 10:00 in Ho Chi Minh time (UTC+7). */
const MORNING = Date.parse("2026-10-01T03:00:00Z");

function clockAt(start: number) {
  const state = { now: start };
  return { state, now: () => state.now };
}

describe("KillSwitch", () => {
  it("a_new_switch_blocks_nothing", () => {
    const killSwitch = new KillSwitch();
    assert.equal(killSwitch.blocks(false), false);
    assert.equal(killSwitch.blocks(true), false);
  });

  it("scope_all_blocks_every_send", () => {
    const killSwitch = new KillSwitch();
    killSwitch.set({ on: true, scope: "all", reason: "test" });
    assert.equal(killSwitch.blocks(false), true);
    assert.equal(killSwitch.blocks(true), true);
  });

  it("scope_proactive_blocks_only_proactive_sends", () => {
    const killSwitch = new KillSwitch();
    killSwitch.set({ on: true, scope: "proactive" });
    assert.equal(killSwitch.blocks(false), false);
    assert.equal(killSwitch.blocks(true), true);
  });

  it("turning_it_off_takes_effect_immediately", () => {
    const killSwitch = new KillSwitch();
    killSwitch.set({ on: true, scope: "all" });
    killSwitch.set({ on: false });
    assert.equal(killSwitch.blocks(true), false);
  });

  it("the_state_reports_scope_and_reason", () => {
    const killSwitch = new KillSwitch();
    killSwitch.set({ on: true, scope: "proactive", reason: "operator" });
    assert.deepEqual(killSwitch.get(), { on: true, scope: "proactive", reason: "operator" });
  });
});

describe("dayKey", () => {
  it("the_day_boundary_follows_the_configured_time_zone", () => {
    const lateUtcEvening = Date.parse("2026-10-01T17:30:00Z");
    assert.equal(dayKey(lateUtcEvening, "UTC"), "2026-10-01");
    assert.equal(dayKey(lateUtcEvening, "Asia/Ho_Chi_Minh"), "2026-10-02");
  });
});

describe("AccountSafety: per-minute ceiling", () => {
  it("sends_over_the_ceiling_are_rate_limited_until_the_minute_slides", () => {
    const clock = clockAt(MORNING);
    const safety = new AccountSafety(LIMITS, clock.now);
    [0, 1, 2].forEach(() => assert.equal(safety.admit(false).ok, true));

    const refused = safety.admit(false);
    assert.equal(refused.ok, false);
    assert.equal(refused.ok === false && refused.kind, "rate_limited");

    clock.state.now += 60_000;
    assert.equal(safety.admit(false).ok, true);
  });

  it("a_refused_request_consumes_nothing", () => {
    const clock = clockAt(MORNING);
    const safety = new AccountSafety({ ...LIMITS, maxSendsPerMinute: 1 }, clock.now);
    safety.admit(false);
    safety.admit(false);
    safety.admit(false);
    clock.state.now += 60_000;
    assert.equal(safety.admit(false).ok, true);
    assert.equal(safety.admit(false).ok, false);
  });
});

describe("AccountSafety: per-day proactive ceiling", () => {
  it("proactive_sends_over_the_daily_ceiling_are_rate_limited_but_replies_still_pass", () => {
    const clock = clockAt(MORNING);
    const safety = new AccountSafety({ ...LIMITS, maxSendsPerMinute: 100 }, clock.now);
    assert.equal(safety.admit(true).ok, true);
    assert.equal(safety.admit(true).ok, true);

    const refused = safety.admit(true);
    assert.equal(refused.ok, false);
    assert.equal(refused.ok === false && refused.kind, "rate_limited");
    assert.equal(safety.admit(false).ok, true, "a reply is not proactive");
    assert.equal(safety.proactiveSentToday(), 2);
  });

  it("a_failed_send_refunds_its_daily_slot", () => {
    const clock = clockAt(MORNING);
    const safety = new AccountSafety({ ...LIMITS, maxSendsPerMinute: 100 }, clock.now);
    const first = safety.admit(true);
    safety.admit(true);
    assert.equal(safety.proactiveSentToday(), 2);

    if (first.ok) safety.failed(first.reservation, false);
    assert.equal(safety.proactiveSentToday(), 1);
    assert.equal(safety.admit(true).ok, true);
  });

  it("the_count_restarts_at_midnight_of_the_configured_time_zone", () => {
    const clock = clockAt(Date.parse("2026-10-01T16:59:00Z")); // 23:59 in +07
    const safety = new AccountSafety({ ...LIMITS, maxSendsPerMinute: 100 }, clock.now);
    safety.admit(true);
    safety.admit(true);
    assert.equal(safety.admit(true).ok, false);

    clock.state.now = Date.parse("2026-10-01T17:01:00Z"); // 00:01 next day in +07
    assert.equal(safety.proactiveSentToday(), 0);
    assert.equal(safety.admit(true).ok, true);
  });

  it("refunding_a_slot_taken_yesterday_does_not_reduce_todays_count", () => {
    const clock = clockAt(Date.parse("2026-10-01T16:59:30Z"));
    const safety = new AccountSafety({ ...LIMITS, maxSendsPerMinute: 100 }, clock.now);
    const yesterday = safety.admit(true);
    clock.state.now = Date.parse("2026-10-01T17:00:30Z");
    safety.admit(true);

    if (yesterday.ok) safety.failed(yesterday.reservation, false);
    assert.equal(safety.proactiveSentToday(), 1);
  });
});

describe("AccountSafety: breaker", () => {
  function admitted(safety: AccountSafety) {
    const admission = safety.admit(false);
    assert.ok(admission.ok);
    return admission.reservation;
  }

  it("consecutive_server_rejections_open_the_breaker_on_the_configured_count", () => {
    const safety = new AccountSafety({ ...LIMITS, maxSendsPerMinute: 100 }, clockAt(MORNING).now);
    assert.equal(safety.failed(admitted(safety), true).blockedNow, false);
    assert.equal(safety.failed(admitted(safety), true).blockedNow, false);
    assert.equal(safety.failed(admitted(safety), true).blockedNow, true);
    assert.equal(safety.blocked, true);
  });

  it("an_open_breaker_refuses_every_send_as_blocked", () => {
    const safety = new AccountSafety({ ...LIMITS, blockAfterRejectedSends: 1 }, clockAt(MORNING).now);
    safety.failed(admitted(safety), true);

    const refused = safety.admit(false);
    assert.equal(refused.ok, false);
    assert.equal(refused.ok === false && refused.kind, "blocked");
  });

  it("a_success_resets_the_count_of_consecutive_rejections", () => {
    const safety = new AccountSafety({ ...LIMITS, maxSendsPerMinute: 100 }, clockAt(MORNING).now);
    safety.failed(admitted(safety), true);
    safety.failed(admitted(safety), true);
    admitted(safety);
    safety.succeeded();

    assert.equal(safety.failed(admitted(safety), true).blockedNow, false);
    assert.equal(safety.failed(admitted(safety), true).blockedNow, false);
    assert.equal(safety.blocked, false);
  });

  it("transport_failures_neither_count_nor_reset", () => {
    const safety = new AccountSafety({ ...LIMITS, maxSendsPerMinute: 100 }, clockAt(MORNING).now);
    safety.failed(admitted(safety), true);
    safety.failed(admitted(safety), true);
    assert.equal(safety.failed(admitted(safety), false).blockedNow, false);
    assert.equal(safety.failed(admitted(safety), true).blockedNow, true, "the third rejection still opens it");
  });

  it("only_clearing_the_breaker_lets_the_account_send_again", () => {
    const safety = new AccountSafety({ ...LIMITS, blockAfterRejectedSends: 1 }, clockAt(MORNING).now);
    safety.failed(admitted(safety), true);
    assert.equal(safety.admit(false).ok, false);

    safety.clearBlocked();
    assert.equal(safety.blocked, false);
    assert.equal(safety.admit(false).ok, true);
  });
});
