// The rules the agent's sessions, trace and usage are shown by.
import { describe, expect, it } from "vitest";

import {
  detailText,
  errorLabel,
  eventLabel,
  formatDuration,
  listPath,
  peopleByChannel,
  personKey,
  sessionHref,
  sessionTitle,
  stopLabel,
  tracesOfSessionHref,
  usageTotals,
} from "./activity";

describe("formatDuration", () => {
  it("shows_milliseconds_seconds_and_minutes", () => {
    expect(formatDuration(320)).toBe("320 ms");
    expect(formatDuration(1500)).toBe("1,5 s");
    expect(formatDuration(125_000)).toBe("2 phút 5 s");
  });
});

describe("words", () => {
  it("name_how_a_turn_ended_and_why_it_failed_and_keep_an_unknown_code", () => {
    expect(stopLabel("completed")).toBe("Xong");
    expect(stopLabel("deadline")).toBe("Quá thời gian");
    expect(stopLabel("new_stop")).toBe("new_stop");
    expect(errorLabel(null)).toBe("");
    expect(errorLabel("rate_limit")).toBe("Nhà cung cấp giới hạn số lần gọi");
    expect(errorLabel("odd")).toBe("odd");
    expect(eventLabel("tool_call")).toBe("Gọi tool");
  });
});

describe("listPath", () => {
  it("leaves_out_the_empty_false_and_zero_parameters_and_encodes_the_rest", () => {
    expect(listPath("/v1/x", { channel: "", q: "", page: 0, errors_only: false })).toBe("/v1/x");
    expect(listPath("/v1/x", { channel: "zalo-a", q: "a b&c", page: 2, errors_only: true })).toBe(
      "/v1/x?channel=zalo-a&q=a%20b%26c&page=2&errors_only=true",
    );
  });
});

describe("links between the pages", () => {
  it("carry_the_session_id_encoded", () => {
    expect(sessionHref("a:b:c:0")).toBe("/admin/agent/sessions?session=a%3Ab%3Ac%3A0");
    expect(tracesOfSessionHref("a:b:c:0")).toBe("/admin/agent/traces?session=a%3Ab%3Ac%3A0");
  });
});

describe("usageTotals", () => {
  it("adds_turns_failed_turns_and_tokens_of_the_days", () => {
    const day = (turns: number, failed: number, input: number, output: number) => ({
      day: "2026-10-10",
      turns,
      failed,
      input_tokens: input,
      output_tokens: output,
    });

    expect(usageTotals([day(3, 1, 100, 10), day(2, 0, 50, 5)])).toEqual({
      turns: 5,
      failed: 1,
      tokens: 165,
    });
    expect(usageTotals([])).toEqual({ turns: 0, failed: 0, tokens: 0 });
  });
});

describe("sessionTitle and detailText", () => {
  it("name_a_chat_by_its_user_else_its_id_and_write_the_metadata_of_a_step", () => {
    expect(sessionTitle({ user_id: "u-1", session_id: "s" })).toBe("u-1");
    expect(sessionTitle({ user_id: null, session_id: "s" })).toBe("s");
    expect(detailText({ size: 12, args: { q: "x" } })).toBe('size: 12 · args: {"q":"x"}');
  });
});

describe("peopleByChannel", () => {
  it("lists_each_person_once_under_their_channel_and_skips_rows_without_either", () => {
    const found = peopleByChannel([
      { channel: "zalo-a", user_id: "u1" },
      { channel: "zalo-a", user_id: "u1" },
      { channel: "zalo-a", user_id: "u2" },
      { channel: "http", user_id: "u1" },
      { channel: null, user_id: "u3" },
      { channel: "zalo-a", user_id: null },
    ]);

    expect([...found]).toEqual([
      ["zalo-a", ["u1", "u2"]],
      ["http", ["u1"]],
    ]);
  });

  it("keeps_the_same_user_id_on_two_channels_apart", () => {
    expect(personKey("zalo-a", "u1")).not.toBe(personKey("http", "u1"));
  });
});
