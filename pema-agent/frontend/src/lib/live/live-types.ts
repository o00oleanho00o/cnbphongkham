// Types of live events and presence come from the generated client (`Schemas[...]`, backend
// `pema_contracts/live.py`):
//
//   GET    /api/v1/events                            SSE; each event is JSON `{type, id}`; no message text
//   POST   /api/v1/conversations/{id}/presence       heartbeat, body `{state: "viewing" | "replying"}`
//   DELETE /api/v1/conversations/{id}/presence       I left the conversation
//   `viewers: [{user_id, name, state}]` in a conversation (list and detail), the caller excluded
//
// The `parse*` helpers below stay: an SSE `data:` line and a `viewers` field are untrusted runtime input.
// STILL TEMPORARY: `AssignableStaff` and `GET /api/v1/staff/assignable` (another package owns that route; its
// entry in `PENDING_CONTRACT` of `mock/contract.test.ts` goes when it lands).
import type { Schemas } from "@/lib/api";

export type LiveEventType = Schemas["LiveEventType"];

/** Every generated event type, so a type added on the backend fails `tsc` here until it is handled. */
const EVENT_TYPE_SET: Record<LiveEventType, true> = {
  "inbox.changed": true,
  "tasks.changed": true,
  "review.changed": true,
  "presence.changed": true,
};

/** What changed, never the content: `id` is the object (conversation, task, review item) or null for "some". */
export type LiveEvent = { type: LiveEventType; id: string | null };

export type PresenceState = Schemas["PresenceState"];

export type PresenceViewer = Schemas["PresenceViewer"];

export type AssignableStaff = { id: string; name: string; role: Schemas["Role"] };

const PRESENCE_STATES: Record<PresenceState, true> = { viewing: true, replying: true };
const ROLES: readonly string[] = ["owner", "manager", "doctor", "cs_staff", "reception", "patient"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isLiveEventType(value: unknown): value is LiveEventType {
  return typeof value === "string" && Object.hasOwn(EVENT_TYPE_SET, value);
}

/** One SSE `data:` payload. Unknown types, heartbeats and malformed JSON are ignored (null). */
export function parseLiveEvent(data: string): LiveEvent | null {
  try {
    const parsed: unknown = JSON.parse(data);
    if (!isRecord(parsed) || !isLiveEventType(parsed.type)) return null;
    return { type: parsed.type, id: typeof parsed.id === "string" ? parsed.id : null };
  } catch {
    return null;
  }
}

function isViewer(value: unknown): value is PresenceViewer {
  return (
    isRecord(value) &&
    typeof value.user_id === "string" &&
    typeof value.name === "string" &&
    typeof value.state === "string" &&
    Object.hasOwn(PRESENCE_STATES, value.state)
  );
}

/** `viewers` of a conversation object (list row or detail); missing or malformed means nobody. */
export function viewersOf(conversation: unknown): PresenceViewer[] {
  if (!isRecord(conversation) || !Array.isArray(conversation.viewers)) return [];
  const viewers: unknown[] = conversation.viewers;
  return viewers.filter(isViewer);
}

function isAssignable(value: unknown): value is AssignableStaff {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.name === "string" &&
    typeof value.role === "string" &&
    ROLES.includes(value.role)
  );
}

export function parseAssignableStaff(value: unknown): AssignableStaff[] {
  if (!Array.isArray(value)) return [];
  const rows: unknown[] = value;
  return rows.filter(isAssignable);
}
