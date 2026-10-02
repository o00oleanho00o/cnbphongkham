// @vitest-environment jsdom
// The presence beat: sent at once and then every 15 seconds while the conversation is open, again straight away
// when the state changes to "replying", not while the tab is hidden, never blocks anything when it fails, and
// stops on unmount or when another conversation opens.
import { cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PresenceState } from "@/lib/live/live-types";
import { PRESENCE_INTERVAL_MS, usePresenceHeartbeat } from "@/lib/live/use-presence-heartbeat";

const api = vi.hoisted(() => ({ postPresence: vi.fn(), leavePresence: vi.fn() }));

vi.mock("@/lib/live/live-api", () => ({
  postPresence: api.postPresence,
  leavePresence: api.leavePresence,
}));

function setVisibility(state: "visible" | "hidden") {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => state });
}

function mount(conversationId: string, state: PresenceState) {
  return renderHook(
    (p: { id: string; state: PresenceState }) => usePresenceHeartbeat(p.id, p.state),
    {
      initialProps: { id: conversationId, state },
    },
  );
}

beforeEach(() => {
  vi.useFakeTimers();
  api.postPresence.mockReset().mockResolvedValue(undefined);
  api.leavePresence.mockReset().mockResolvedValue(undefined);
  setVisibility("visible");
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("usePresenceHeartbeat", () => {
  it("sends viewing at once and then every 15 seconds", () => {
    mount("c-1", "viewing");
    expect(api.postPresence).toHaveBeenCalledTimes(1);
    expect(api.postPresence).toHaveBeenLastCalledWith("c-1", "viewing");
    vi.advanceTimersByTime(PRESENCE_INTERVAL_MS);
    expect(api.postPresence).toHaveBeenCalledTimes(2);
    vi.advanceTimersByTime(PRESENCE_INTERVAL_MS * 2);
    expect(api.postPresence).toHaveBeenCalledTimes(4);
  });

  it("beats every 15 seconds, not faster", () => {
    expect(PRESENCE_INTERVAL_MS).toBe(15_000);
    mount("c-1", "viewing");
    vi.advanceTimersByTime(PRESENCE_INTERVAL_MS - 1);
    expect(api.postPresence).toHaveBeenCalledTimes(1);
  });

  it("sends replying straight away when the person starts typing", () => {
    const { rerender } = mount("c-1", "viewing");
    rerender({ id: "c-1", state: "replying" });
    expect(api.postPresence).toHaveBeenCalledTimes(2);
    expect(api.postPresence).toHaveBeenLastCalledWith("c-1", "replying");
    vi.advanceTimersByTime(PRESENCE_INTERVAL_MS);
    expect(api.postPresence).toHaveBeenLastCalledWith("c-1", "replying");
  });

  it("beats for the new conversation when another one is opened", () => {
    const { rerender } = mount("c-1", "viewing");
    rerender({ id: "c-2", state: "viewing" });
    expect(api.postPresence).toHaveBeenLastCalledWith("c-2", "viewing");
    api.postPresence.mockClear();
    vi.advanceTimersByTime(PRESENCE_INTERVAL_MS);
    expect(api.postPresence.mock.calls.map((c) => c[0])).toEqual(["c-2"]);
  });

  it("sends nothing while the tab is hidden and beats once when it is visible again", () => {
    setVisibility("hidden");
    mount("c-1", "viewing");
    vi.advanceTimersByTime(PRESENCE_INTERVAL_MS * 3);
    expect(api.postPresence).not.toHaveBeenCalled();
    setVisibility("visible");
    document.dispatchEvent(new Event("visibilitychange"));
    expect(api.postPresence).toHaveBeenCalledTimes(1);
  });

  it("ignores a failed beat and keeps beating", async () => {
    api.postPresence.mockRejectedValue(new Error("down"));
    mount("c-1", "viewing");
    await vi.advanceTimersByTimeAsync(PRESENCE_INTERVAL_MS * 2);
    expect(api.postPresence).toHaveBeenCalledTimes(3);
  });

  it("tells the backend it left when the conversation closes or another one opens", () => {
    const { rerender, unmount } = mount("c-1", "viewing");
    expect(api.leavePresence).not.toHaveBeenCalled();
    rerender({ id: "c-2", state: "viewing" });
    expect(api.leavePresence).toHaveBeenLastCalledWith("c-1");
    unmount();
    expect(api.leavePresence).toHaveBeenLastCalledWith("c-2");
  });

  it("does not leave when the state only changes from viewing to replying", () => {
    const { rerender } = mount("c-1", "viewing");
    rerender({ id: "c-1", state: "replying" });
    expect(api.leavePresence).not.toHaveBeenCalled();
  });

  it("ignores a failed leave call", async () => {
    api.leavePresence.mockRejectedValue(new Error("down"));
    const { unmount } = mount("c-1", "viewing");
    unmount();
    await vi.advanceTimersByTimeAsync(0);
    expect(api.leavePresence).toHaveBeenCalledTimes(1);
  });

  it("stops on unmount: no timer, no listener, no more beats", () => {
    const { unmount } = mount("c-1", "viewing");
    api.postPresence.mockClear();
    unmount();
    expect(vi.getTimerCount()).toBe(0);
    vi.advanceTimersByTime(PRESENCE_INTERVAL_MS * 3);
    document.dispatchEvent(new Event("visibilitychange"));
    expect(api.postPresence).not.toHaveBeenCalled();
  });
});
