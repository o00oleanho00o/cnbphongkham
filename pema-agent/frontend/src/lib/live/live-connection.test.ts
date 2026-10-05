// The live connection against a fake EventSource and fake timers: events reach the screen (filtered and
// coalesced), a dropped stream is retried, after 10 seconds down the screen refreshes every 30 seconds, the
// stream coming back stops that and refreshes once, and `close` leaves no timer and no listener behind.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  COALESCE_MS,
  FALLBACK_AFTER_MS,
  LiveConnection,
  POLL_EVERY_MS,
  RECONNECT_DELAYS_MS,
  type EventSourceLike,
  type LiveMode,
} from "@/lib/live/live-connection";
import type { LiveEvent } from "@/lib/live/live-types";

class FakeSource implements EventSourceLike {
  static all: FakeSource[] = [];
  readyState = 0;
  closed = false;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(readonly url: string) {
    FakeSource.all.push(this);
  }

  close(): void {
    this.closed = true;
    this.readyState = 2;
  }

  open(): void {
    this.readyState = 1;
    this.onopen?.(new Event("open"));
  }

  send(data: unknown): void {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(data) }));
  }

  /** The browser keeps retrying by itself (CONNECTING) or gives up (CLOSED). */
  fail(giveUp: boolean): void {
    this.readyState = giveUp ? 2 : 0;
    this.onerror?.(new Event("error"));
  }
}

function setup(types?: LiveEvent["type"][]) {
  const events: LiveEvent[] = [];
  const modes: LiveMode[] = [];
  const onRefresh = vi.fn();
  const connection = new LiveConnection({
    types,
    onEvent: (e) => events.push(e),
    onRefresh,
    onMode: (m) => modes.push(m),
    createSource: (url) => new FakeSource(url),
  });
  connection.start();
  const current = () => FakeSource.all[FakeSource.all.length - 1] as FakeSource;
  return { connection, events, modes, onRefresh, current };
}

beforeEach(() => {
  FakeSource.all = [];
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("LiveConnection events", () => {
  it("connects to /api/v1/events and reports live once it is open", () => {
    const { modes, current } = setup();
    expect(current().url).toBe("/api/v1/events");
    current().open();
    expect(modes).toEqual(["live"]);
  });

  it("hands a screen the events it asked for and ignores the rest, heartbeats and garbage", () => {
    const { events, current } = setup(["tasks.changed"]);
    current().open();
    current().send({ type: "tasks.changed", id: "t-1" });
    current().send({ type: "inbox.changed", id: "c-1" });
    current().send({ type: "unknown.thing", id: "x" });
    current().onmessage?.(new MessageEvent("message", { data: "not json" }));
    vi.advanceTimersByTime(COALESCE_MS);
    expect(events).toEqual([{ type: "tasks.changed", id: "t-1" }]);
  });

  it("coalesces a burst of the same event into one call", () => {
    const { events, current } = setup();
    current().open();
    current().send({ type: "inbox.changed", id: "c-1" });
    current().send({ type: "inbox.changed", id: "c-1" });
    current().send({ type: "inbox.changed", id: "c-2" });
    expect(events).toEqual([]);
    vi.advanceTimersByTime(COALESCE_MS);
    expect(events).toEqual([
      { type: "inbox.changed", id: "c-1" },
      { type: "inbox.changed", id: "c-2" },
    ]);
  });

  it("keeps the id of an event as null when the server sends none", () => {
    const { events, current } = setup();
    current().open();
    current().send({ type: "review.changed" });
    vi.advanceTimersByTime(COALESCE_MS);
    expect(events).toEqual([{ type: "review.changed", id: null }]);
  });
});

describe("LiveConnection drop and fallback", () => {
  it("does not poll while the stream is up, even after a long time", () => {
    const { onRefresh, current } = setup();
    current().open();
    vi.advanceTimersByTime(POLL_EVERY_MS * 3);
    expect(onRefresh).not.toHaveBeenCalled();
  });

  it("reconnects by itself when the browser gave up, with growing delays", () => {
    const { current } = setup();
    current().open();
    current().fail(true);
    expect(FakeSource.all).toHaveLength(1);
    vi.advanceTimersByTime(RECONNECT_DELAYS_MS[0] ?? 0);
    expect(FakeSource.all).toHaveLength(2);
    current().fail(true);
    vi.advanceTimersByTime((RECONNECT_DELAYS_MS[1] ?? 0) - 1);
    expect(FakeSource.all).toHaveLength(2);
    vi.advanceTimersByTime(1);
    expect(FakeSource.all).toHaveLength(3);
  });

  it("falls back to a refresh every 30 seconds once the stream was down for over 10 seconds", () => {
    const { modes, onRefresh, current } = setup();
    current().open();
    current().fail(false);
    vi.advanceTimersByTime(FALLBACK_AFTER_MS - 1);
    expect(modes).toEqual(["live", "connecting"]);
    vi.advanceTimersByTime(1);
    expect(modes).toEqual(["live", "connecting", "polling"]);
    expect(onRefresh).not.toHaveBeenCalled();
    vi.advanceTimersByTime(POLL_EVERY_MS);
    expect(onRefresh).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(POLL_EVERY_MS * 2);
    expect(onRefresh).toHaveBeenCalledTimes(3);
  });

  it("does not fall back when the stream is back within 10 seconds, but refreshes once for what it missed", () => {
    const { modes, onRefresh, current } = setup();
    current().open();
    current().fail(false);
    vi.advanceTimersByTime(FALLBACK_AFTER_MS - 1000);
    current().open();
    expect(modes).toEqual(["live", "connecting", "live"]);
    expect(onRefresh).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(POLL_EVERY_MS * 2);
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it("stops polling when the stream comes back and refreshes once", () => {
    const { modes, onRefresh, current } = setup();
    current().open();
    current().fail(true);
    vi.advanceTimersByTime(FALLBACK_AFTER_MS + POLL_EVERY_MS);
    expect(onRefresh).toHaveBeenCalledTimes(1);
    current().open();
    expect(modes.at(-1)).toBe("live");
    expect(onRefresh).toHaveBeenCalledTimes(2);
    vi.advanceTimersByTime(POLL_EVERY_MS * 3);
    expect(onRefresh).toHaveBeenCalledTimes(2);
  });

  it("starts polling when the very first connection never opens", () => {
    const { modes, onRefresh, current } = setup();
    current().fail(false);
    vi.advanceTimersByTime(FALLBACK_AFTER_MS + POLL_EVERY_MS);
    expect(modes).toEqual(["polling"]);
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it("ignores events of a source it already replaced", () => {
    const { events, current } = setup();
    const first = current();
    first.open();
    first.fail(true);
    vi.advanceTimersByTime(RECONNECT_DELAYS_MS[0] ?? 0);
    first.send({ type: "inbox.changed", id: "stale" });
    vi.advanceTimersByTime(COALESCE_MS);
    expect(events).toEqual([]);
  });
});

describe("LiveConnection close", () => {
  it("closes the source and leaves no timer behind in any state", () => {
    const { connection, onRefresh, current } = setup();
    current().open();
    current().send({ type: "inbox.changed", id: "c-1" });
    current().fail(true);
    vi.advanceTimersByTime(FALLBACK_AFTER_MS + POLL_EVERY_MS);
    const refreshesBefore = onRefresh.mock.calls.length;

    connection.close();

    expect(current().closed).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
    vi.advanceTimersByTime(POLL_EVERY_MS * 5);
    expect(onRefresh).toHaveBeenCalledTimes(refreshesBefore);
  });

  it("drops events that were still waiting to be handed over", () => {
    const { connection, events, current } = setup();
    current().open();
    current().send({ type: "inbox.changed", id: "c-1" });
    connection.close();
    vi.advanceTimersByTime(COALESCE_MS * 4);
    expect(events).toEqual([]);
  });

  it("does not reconnect after close", () => {
    const { connection, current } = setup();
    current().open();
    current().fail(true);
    connection.close();
    vi.advanceTimersByTime(RECONNECT_DELAYS_MS.at(-1) ?? 0);
    expect(FakeSource.all).toHaveLength(1);
  });
});
