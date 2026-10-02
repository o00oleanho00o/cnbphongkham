// @vitest-environment jsdom
// `useLiveEvents` in a component: the fake EventSource stands where the browser's would. It checks what a screen
// sees (events for its types, mode, refresh when the stream drops for over 10 seconds) and, above all, the
// cleanup: after unmount no source, no listener and no timer is left, and a re-render does not reconnect.
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  COALESCE_MS,
  FALLBACK_AFTER_MS,
  POLL_EVERY_MS,
  type EventSourceLike,
} from "@/lib/live/live-connection";
import type { LiveEvent, LiveEventType } from "@/lib/live/live-types";
import { useLiveEvents } from "@/lib/live/use-live-events";

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

  fail(): void {
    this.readyState = 0;
    this.onerror?.(new Event("error"));
  }
}

const TYPES: readonly LiveEventType[] = ["inbox.changed"];
const createSource = (url: string) => new FakeSource(url);

function mount(onEvent: (e: LiveEvent) => void, onRefresh: () => void) {
  return renderHook(
    (props: { onEvent: (e: LiveEvent) => void; onRefresh: () => void }) =>
      useLiveEvents({ types: TYPES, createSource, ...props }),
    { initialProps: { onEvent, onRefresh } },
  );
}

const latest = () => FakeSource.all[FakeSource.all.length - 1] as FakeSource;

beforeEach(() => {
  FakeSource.all = [];
  vi.useFakeTimers();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("useLiveEvents", () => {
  it("calls the screen for an event of its type and reports live", () => {
    const onEvent = vi.fn();
    const { result } = mount(onEvent, vi.fn());
    expect(result.current).toBe("connecting");
    act(() => latest().open());
    expect(result.current).toBe("live");
    act(() => {
      latest().send({ type: "inbox.changed", id: "c-1" });
      latest().send({ type: "tasks.changed", id: "t-1" });
      vi.advanceTimersByTime(COALESCE_MS);
    });
    expect(onEvent).toHaveBeenCalledTimes(1);
    expect(onEvent).toHaveBeenCalledWith({ type: "inbox.changed", id: "c-1" });
  });

  it("goes to polling after 10 seconds without the stream and refreshes every 30 seconds", () => {
    const onRefresh = vi.fn();
    const { result } = mount(vi.fn(), onRefresh);
    act(() => latest().open());
    act(() => latest().fail());
    expect(result.current).toBe("connecting");
    act(() => vi.advanceTimersByTime(FALLBACK_AFTER_MS));
    expect(result.current).toBe("polling");
    act(() => vi.advanceTimersByTime(POLL_EVERY_MS * 2));
    expect(onRefresh).toHaveBeenCalledTimes(2);
  });

  it("returns to live and stops polling when the stream is back", () => {
    const onRefresh = vi.fn();
    const { result } = mount(vi.fn(), onRefresh);
    act(() => latest().open());
    act(() => latest().fail());
    act(() => vi.advanceTimersByTime(FALLBACK_AFTER_MS + POLL_EVERY_MS));
    expect(onRefresh).toHaveBeenCalledTimes(1);
    act(() => latest().open());
    expect(result.current).toBe("live");
    expect(onRefresh).toHaveBeenCalledTimes(2);
    act(() => vi.advanceTimersByTime(POLL_EVERY_MS * 3));
    expect(onRefresh).toHaveBeenCalledTimes(2);
  });

  it("does not reconnect when the screen re-renders with new callbacks, and uses the newest one", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = mount(first, vi.fn());
    act(() => latest().open());
    rerender({ onEvent: second, onRefresh: vi.fn() });
    expect(FakeSource.all).toHaveLength(1);
    act(() => {
      latest().send({ type: "inbox.changed", id: "c-1" });
      vi.advanceTimersByTime(COALESCE_MS);
    });
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });

  it("on unmount closes the source and leaves no timer, in the live state", () => {
    const { unmount } = mount(vi.fn(), vi.fn());
    act(() => latest().open());
    act(() => latest().send({ type: "inbox.changed", id: "c-1" }));
    unmount();
    expect(latest().closed).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("on unmount leaves no timer in the polling state either, and nothing is refreshed afterwards", () => {
    const onRefresh = vi.fn();
    const { unmount } = mount(vi.fn(), onRefresh);
    act(() => latest().open());
    act(() => latest().fail());
    act(() => vi.advanceTimersByTime(FALLBACK_AFTER_MS + POLL_EVERY_MS));
    const before = onRefresh.mock.calls.length;
    unmount();
    expect(vi.getTimerCount()).toBe(0);
    act(() => vi.advanceTimersByTime(POLL_EVERY_MS * 5));
    expect(onRefresh).toHaveBeenCalledTimes(before);
  });
});
