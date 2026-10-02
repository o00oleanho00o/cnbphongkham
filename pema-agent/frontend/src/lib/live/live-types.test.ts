import { describe, expect, it } from "vitest";

import { parseLiveEvent, viewersOf } from "@/lib/live/live-types";

describe("parseLiveEvent", () => {
  it("reads type and object id", () => {
    expect(parseLiveEvent('{"type":"inbox.changed","id":"c-1"}')).toEqual({
      type: "inbox.changed",
      id: "c-1",
    });
  });

  it("accepts the four agreed types and keeps a missing id as null", () => {
    const types = ["inbox.changed", "tasks.changed", "review.changed", "presence.changed"];
    types.forEach((type) => {
      expect(parseLiveEvent(JSON.stringify({ type }))).toEqual({ type, id: null });
    });
  });

  it("ignores unknown types, non-objects and malformed JSON", () => {
    expect(parseLiveEvent('{"type":"patient.changed","id":"p"}')).toBeNull();
    expect(parseLiveEvent("[]")).toBeNull();
    expect(parseLiveEvent('"inbox.changed"')).toBeNull();
    expect(parseLiveEvent("{oops")).toBeNull();
  });

  it("does not carry any other field (events never hold message text)", () => {
    const event = parseLiveEvent('{"type":"inbox.changed","id":"c-1","text":"Xin chào"}');
    expect(event).toEqual({ type: "inbox.changed", id: "c-1" });
  });
});

describe("viewersOf", () => {
  it("returns the well-formed viewers of a conversation", () => {
    const viewers = [{ user_id: "u-1", name: "Lan", state: "viewing" }];
    expect(viewersOf({ id: "c", viewers })).toEqual(viewers);
  });

  it("is empty when the field is missing, not a list, or holds bad rows", () => {
    expect(viewersOf({ id: "c" })).toEqual([]);
    expect(viewersOf({ viewers: "Lan" })).toEqual([]);
    expect(viewersOf(undefined)).toEqual([]);
    expect(
      viewersOf({
        viewers: [
          { user_id: "u-1", name: "Lan", state: "typing" },
          { user_id: 2, name: "Hà", state: "viewing" },
          { user_id: "u-3", name: "Mai", state: "replying" },
        ],
      }),
    ).toEqual([{ user_id: "u-3", name: "Mai", state: "replying" }]);
  });
});
