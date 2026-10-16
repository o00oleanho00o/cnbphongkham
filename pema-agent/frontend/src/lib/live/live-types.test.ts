import { describe, expect, it } from "vitest";

import { parseLiveEvent } from "@/lib/live/live-types";

describe("parseLiveEvent", () => {
  it("reads type and object id", () => {
    expect(parseLiveEvent('{"type":"tasks.changed","id":"t-1"}')).toEqual({
      type: "tasks.changed",
      id: "t-1",
    });
  });

  it("accepts the two agreed types and keeps a missing id as null", () => {
    const types = ["tasks.changed", "appointments.changed"];
    types.forEach((type) => {
      expect(parseLiveEvent(JSON.stringify({ type }))).toEqual({ type, id: null });
    });
  });

  it("ignores unknown types, events of removed features, non-objects and malformed JSON", () => {
    expect(parseLiveEvent('{"type":"patient.changed","id":"p"}')).toBeNull();
    expect(parseLiveEvent('{"type":"inbox.changed","id":"c"}')).toBeNull();
    expect(parseLiveEvent("[]")).toBeNull();
    expect(parseLiveEvent('"tasks.changed"')).toBeNull();
    expect(parseLiveEvent("{oops")).toBeNull();
  });

  it("does not carry any other field (events never hold message text)", () => {
    const event = parseLiveEvent('{"type":"tasks.changed","id":"t-1","text":"Xin chào"}');
    expect(event).toEqual({ type: "tasks.changed", id: "t-1" });
  });
});
