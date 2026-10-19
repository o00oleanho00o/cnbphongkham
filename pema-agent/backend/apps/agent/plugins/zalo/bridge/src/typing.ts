/**
 * "The person is typing", from zca-js' `typing` event, for the API.
 *
 * New module (no TS original). Zalo repeats the event every moment while someone types and the API only needs
 * to know the person is still at it, so one event per person per `TYPING_MIN_GAP_MS` goes out. Only one-to-one
 * chats matter: the agent waits a little longer for the rest of a burst of messages, and nothing is stored.
 */
import { ThreadType } from "zca-js";
import type { Typing } from "zca-js";
import type { BridgeEvent } from "./event-publisher.js";

export const TYPING_MIN_GAP_MS = 2_000;
/** Past this many remembered people the ones whose gap is over are forgotten. */
const REMEMBERED_PEOPLE = 1_000;

export type TypingFilter = (typing: Typing) => BridgeEvent | null;

export function createTypingFilter(now: () => number): TypingFilter {
  const lastSent = new Map<string, number>();

  const forgetOld = (at: number): void => {
    if (lastSent.size <= REMEMBERED_PEOPLE) return;
    lastSent.forEach((sentAt, threadId) => {
      if (at - sentAt >= TYPING_MIN_GAP_MS) lastSent.delete(threadId);
    });
  };

  const isRepeat = (threadId: string, at: number): boolean => {
    const previous = lastSent.get(threadId);
    return previous !== undefined && at - previous < TYPING_MIN_GAP_MS;
  };

  return (typing) => {
    if (typing.type !== ThreadType.User) return null;
    const at = now();
    if (isRepeat(typing.threadId, at)) return null;
    forgetOld(at);
    lastSent.set(typing.threadId, at);
    return { type: "typing", thread_id: typing.threadId, is_group: false };
  };
}
