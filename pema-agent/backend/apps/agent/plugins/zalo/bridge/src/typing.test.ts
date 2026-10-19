import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createTypingFilter, TYPING_MIN_GAP_MS } from "./typing.js";
import { fakeGroupTyping, fakeUserTyping } from "./test-support.js";

describe("typing filter", () => {
  it("a_person_typing_in_a_one_to_one_chat_becomes_one_event_with_the_thread_id", () => {
    const filter = createTypingFilter(() => 1_000);

    assert.deepEqual(filter(fakeUserTyping("2000007")), {
      type: "typing",
      thread_id: "2000007",
      is_group: false,
    });
  });

  it("typing_in_a_group_is_left_out", () => {
    const filter = createTypingFilter(() => 1_000);

    assert.equal(filter(fakeGroupTyping()), null);
  });

  it("the_same_person_is_reported_once_per_gap_and_again_after_it", () => {
    const clock = { at: 10_000 };
    const filter = createTypingFilter(() => clock.at);

    const first = filter(fakeUserTyping("a"));
    clock.at += TYPING_MIN_GAP_MS - 1;
    const repeat = filter(fakeUserTyping("a"));
    clock.at += 1;
    const later = filter(fakeUserTyping("a"));

    assert.notEqual(first, null);
    assert.equal(repeat, null);
    assert.notEqual(later, null);
  });

  it("two_people_do_not_hold_each_other_back", () => {
    const filter = createTypingFilter(() => 1_000);

    assert.notEqual(filter(fakeUserTyping("a")), null);
    assert.notEqual(filter(fakeUserTyping("b")), null);
  });
});
