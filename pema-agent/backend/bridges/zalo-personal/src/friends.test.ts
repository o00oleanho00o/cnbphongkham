// Tests of the friend projection and the friend-event normalisation (ported behaviour of
// friend-routes.ts `/list` and the event kinds of friend-event-handler.ts).
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { FriendEventType } from "zca-js";
import { normalizeFriendEvent, summarizeFriends } from "./friends.js";
import { fakeFriendEvent } from "./test-support.js";

describe("summarizeFriends", () => {
  it("only_user_id_display_name_and_zalo_name_are_kept", () => {
    const result = summarizeFriends([
      { userId: "1", displayName: "A", zaloName: "a", phoneNumber: "0900000000", dob: "x", avatar: "y" },
    ]);
    assert.deepEqual(result, [{ userId: "1", displayName: "A", zaloName: "a" }]);
    assert.deepEqual(Object.keys(result[0] ?? {}).toSorted(), ["displayName", "userId", "zaloName"]);
  });

  it("anything_that_is_not_a_list_gives_an_empty_list", () => {
    assert.deepEqual(summarizeFriends(null), []);
    assert.deepEqual(summarizeFriends({ not: "a list" }), []);
  });
});

describe("normalizeFriendEvent", () => {
  const cases: Array<[FriendEventType, string]> = [
    [FriendEventType.ADD, "add"],
    [FriendEventType.REMOVE, "remove"],
    [FriendEventType.REQUEST, "request"],
    [FriendEventType.UNDO_REQUEST, "undo_request"],
    [FriendEventType.REJECT_REQUEST, "reject_request"],
    [FriendEventType.BLOCK, "other"],
    [FriendEventType.SEEN_FRIEND_REQUEST, "other"],
    [FriendEventType.PIN_CREATE, "other"],
    [FriendEventType.UNKNOWN, "other"],
  ];

  cases.forEach(([type, kind]) => {
    it(`the_kind_of_${FriendEventType[type]?.toLowerCase()}_is_${kind}`, () => {
      assert.equal(normalizeFriendEvent(fakeFriendEvent(type)).kind, kind);
    });
  });

  it("thread_id_is_self_flag_and_data_are_carried_over", () => {
    const event = { type: FriendEventType.REQUEST, threadId: "2000001", isSelf: true, data: { fromUid: "2000001" } };
    const normalized = normalizeFriendEvent(event as never); // synthetic request payload
    assert.deepEqual(normalized, {
      kind: "request",
      thread_id: "2000001",
      is_self: true,
      data: { fromUid: "2000001" },
    });
  });

  it("the_numeric_value_of_the_enum_never_appears_in_the_normalised_event", () => {
    const normalized = normalizeFriendEvent(fakeFriendEvent(FriendEventType.REQUEST));
    assert.equal(Object.values(normalized).includes(FriendEventType.REQUEST), false);
  });
});
