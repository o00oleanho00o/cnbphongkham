// New tests of the signed, retrying, non-blocking event publisher.
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { SIGNATURE_HEADER, TIMESTAMP_HEADER, verifySignature } from "./auth.js";
import { HttpEventPublisher, type BridgeEvent } from "./event-publisher.js";
import { SECRET, TEST_CREDENTIAL } from "./test-support.js";

type Seen = { url: string; headers: Record<string, string>; body: string };

type Reply = number | Error;

/** A hand-written fetch: answers the scripted replies in order (200 once they run out) and records requests. */
function scriptedFetch(replies: Reply[] = []) {
  const seen: Seen[] = [];
  const queue = [...replies];
  const fetchImpl: typeof fetch = async (input, init) => {
    seen.push({
      url: String(input),
      headers: (init?.headers ?? {}) as Record<string, string>,
      body: String(init?.body ?? ""),
    });
    const next = queue.shift() ?? 200;
    if (next instanceof Error) throw next;
    return new Response("{}", { status: next });
  };
  return { fetchImpl, seen };
}

function publisherWith(
  replies: Reply[] = [],
  extra: Partial<ConstructorParameters<typeof HttpEventPublisher>[0]> = {},
) {
  const { fetchImpl, seen } = scriptedFetch(replies);
  const sleeps: number[] = [];
  const publisher = new HttpEventPublisher({
    secret: SECRET,
    apiBaseUrl: "http://api.test/api/v1",
    fetchImpl,
    sleep: async (ms) => void sleeps.push(ms),
    nowSeconds: () => 1_700_000_000,
    ...extra,
  });
  return { publisher, seen, sleeps };
}

const target = { accountId: "acc-1", clinicSlug: "clinic-a" };
const stateEvent: BridgeEvent = { type: "account_state", state: "connected", reason: "connected" };

describe("HttpEventPublisher", () => {
  it("an_event_is_posted_to_the_webhook_of_its_clinic_and_account_with_a_valid_signature", async () => {
    const { publisher, seen } = publisherWith();

    publisher.publish(target, stateEvent);
    await publisher.flush();

    assert.equal(seen.length, 1);
    assert.equal(seen[0]?.url, "http://api.test/api/v1/webhooks/zalo-bridge/clinic-a/acc-1");
    assert.deepEqual(JSON.parse(seen[0]?.body ?? ""), stateEvent);
    const headers = seen[0]?.headers ?? {};
    assert.deepEqual(
      verifySignature({
        secret: SECRET,
        timestamp: headers[TIMESTAMP_HEADER],
        signature: headers[SIGNATURE_HEADER],
        body: seen[0]?.body ?? "",
        nowSeconds: 1_700_000_000,
      }),
      { ok: true },
    );
  });

  it("the_clinic_slug_and_account_id_are_escaped_in_the_path", async () => {
    const { publisher, seen } = publisherWith();
    publisher.publish({ accountId: "a/b", clinicSlug: "c d" }, stateEvent);
    await publisher.flush();
    assert.equal(seen[0]?.url, "http://api.test/api/v1/webhooks/zalo-bridge/c%20d/a%2Fb");
  });

  it("publish_returns_at_once_and_never_waits_for_the_api", () => {
    const { publisher } = publisherWith([500, 500, 500, 500]);
    const started = publisher.publish(target, stateEvent);
    assert.equal(started, undefined);
  });

  it("a_server_error_is_retried_three_times_with_exponential_backoff", async () => {
    const { publisher, seen, sleeps } = publisherWith([503, 503, 503, 503], { baseDelayMs: 500 });

    publisher.publish(target, stateEvent);
    await publisher.flush();

    assert.equal(seen.length, 4, "the first attempt and three retries");
    assert.deepEqual(sleeps, [500, 1000, 2000]);
  });

  it("a_retry_succeeds_when_the_api_comes_back", async () => {
    const { publisher, seen } = publisherWith([new Error("ECONNREFUSED"), 502]);

    publisher.publish(target, stateEvent);
    await publisher.flush();

    assert.equal(seen.length, 3, "two failures then a success");
  });

  it("a_client_error_other_than_slow_down_is_not_retried", async () => {
    const { publisher, seen } = publisherWith([401]);
    publisher.publish(target, stateEvent);
    await publisher.flush();
    assert.equal(seen.length, 1);
  });

  it("too_many_requests_is_retried", async () => {
    const { publisher, seen } = publisherWith([429]);
    publisher.publish(target, stateEvent);
    await publisher.flush();
    assert.equal(seen.length, 2);
  });

  it("events_of_one_account_are_delivered_in_order_even_when_the_first_needs_a_retry", async () => {
    const { publisher, seen } = publisherWith([500]);
    const first: BridgeEvent = { type: "account_state", state: "connected", reason: "first" };
    const second: BridgeEvent = { type: "account_state", state: "disconnected", reason: "second" };

    publisher.publish(target, first);
    publisher.publish(target, second);
    await publisher.flush();

    assert.deepEqual(
      seen.map((request) => (JSON.parse(request.body) as { reason: string }).reason),
      ["first", "first", "second"],
    );
  });

  it("a_credential_update_carries_the_credential", async () => {
    const { publisher, seen } = publisherWith();
    publisher.publish(target, { type: "credential_updated", credential: TEST_CREDENTIAL });
    await publisher.flush();
    assert.deepEqual(JSON.parse(seen[0]?.body ?? ""), {
      type: "credential_updated",
      credential: TEST_CREDENTIAL,
    });
  });

  it("ids_beyond_the_safe_integer_range_are_written_as_strings", async () => {
    const { publisher, seen } = publisherWith();
    publisher.publish(target, {
      type: "message",
      self_id: "1",
      message: { data: { id: 9007199254740993n } },
    });
    await publisher.flush();
    assert.equal(seen[0]?.body.includes('"9007199254740993"'), true);
  });

  it("an_event_that_cannot_be_serialised_is_dropped_without_stopping_the_queue", async () => {
    const { publisher, seen } = publisherWith();
    const circular: Record<string, unknown> = {};
    circular["self"] = circular;

    publisher.publish(target, { type: "message", self_id: "1", message: circular });
    publisher.publish(target, stateEvent);
    await publisher.flush();

    assert.equal(seen.length, 1);
  });

  it("the_queue_is_bounded_and_drops_the_oldest_event_when_the_api_stays_down", async () => {
    let release: () => void = () => undefined;
    const blocker = new Promise<void>((resolve) => {
      release = resolve;
    });
    const seenBodies: string[] = [];
    const { publisher } = publisherWith([], {
      maxQueuePerAccount: 2,
      fetchImpl: async (_input, init) => {
        await blocker;
        seenBodies.push(String(init?.body));
        return new Response("{}", { status: 200 });
      },
    });
    const named = (reason: string): BridgeEvent => ({
      type: "account_state",
      state: "connected",
      reason,
    });

    ["a", "b", "c", "d"].forEach((reason) => publisher.publish(target, named(reason)));
    release();
    await publisher.flush();

    // "a" was already taken by the delivery loop; "b" was dropped when "d" arrived.
    assert.deepEqual(
      seenBodies.map((body) => (JSON.parse(body) as { reason: string }).reason),
      ["a", "c", "d"],
    );
  });
});
