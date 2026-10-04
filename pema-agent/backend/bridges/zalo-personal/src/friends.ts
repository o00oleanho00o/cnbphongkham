// ported from: src/server/routes/friend-routes.ts (the `/list` projection) and
// src/zalo/friend-event-handler.ts (the event kinds). The pending-request store and the auto-accept
// logic of the original run in the Python API; the bridge only normalises what it sees.
import { FriendEventType, type FriendEvent } from "zca-js";
import type { FriendEventKind } from "./event-publisher.js";

export type FriendSummary = {
  userId: string;
  displayName: string | undefined;
  zaloName: string | undefined;
};

/**
 * CHỈ trả field UI cần. getAllFriends() trả User đầy đủ (có cả phoneNumber,
 * dob...) - đẩy nguyên ra ngoài là lộ PII của bạn bè không cần thiết.
 */
export function summarizeFriends(list: unknown): FriendSummary[] {
  const friends = (Array.isArray(list) ? list : []) as Array<{
    userId: string;
    displayName?: string;
    zaloName?: string;
  }>;
  return friends.map((friend) => ({
    userId: friend.userId,
    displayName: friend.displayName,
    zaloName: friend.zaloName,
  }));
}

/** Map by enum NAME so the numeric values of `FriendEventType` never leak to the API. */
const KIND_BY_ENUM_NAME: Readonly<Record<string, FriendEventKind>> = {
  ADD: "add",
  REMOVE: "remove",
  REQUEST: "request",
  UNDO_REQUEST: "undo_request",
  REJECT_REQUEST: "reject_request",
};

export type NormalizedFriendEvent = {
  kind: FriendEventKind;
  thread_id: string;
  is_self: boolean;
  data: unknown;
};

export function normalizeFriendEvent(event: FriendEvent): NormalizedFriendEvent {
  const enumName = FriendEventType[event.type] ?? "";
  const kind = Object.hasOwn(KIND_BY_ENUM_NAME, enumName) ? KIND_BY_ENUM_NAME[enumName] : undefined;
  return {
    kind: kind ?? "other",
    thread_id: event.threadId,
    is_self: event.isSelf,
    data: event.data,
  };
}
