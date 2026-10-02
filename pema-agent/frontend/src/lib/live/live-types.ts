// TEMPORARY LOCAL TYPES. The backend contract for several people working at the same time (live events,
// presence) is not in `src/lib/api/schema.d.ts` yet (it is generated from `backend/apps/api/openapi.json`).
// These types mirror the agreed contract; the integration package replaces them with the generated ones
// (`Schemas["..."]`) once the routes exist, and `parse*` below can then go.
//
//   GET  /api/v1/events                              SSE; each event is JSON `{type, id}`; no message text
//   POST /api/v1/conversations/{id}/presence         body `{state: "viewing" | "replying"}`
//   `viewers: [{user_id, name, state}]` in a conversation (list and detail), the caller excluded
// (`GET /api/v1/staff/assignable` left this file: it is in the generated client, see `lib/staff/`.)

export const LIVE_EVENT_TYPES = [
  "inbox.changed",
  "tasks.changed",
  "review.changed",
  "presence.changed",
] as const;

export type LiveEventType = (typeof LIVE_EVENT_TYPES)[number];

/** What changed, never the content: `id` is the object (conversation, task, review item) or null for "some". */
export type LiveEvent = { type: LiveEventType; id: string | null };

export type PresenceState = "viewing" | "replying";

export type PresenceViewer = { user_id: string; name: string; state: PresenceState };

const PRESENCE_STATES: readonly string[] = ["viewing", "replying"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isLiveEventType(value: unknown): value is LiveEventType {
  return typeof value === "string" && (LIVE_EVENT_TYPES as readonly string[]).includes(value);
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
    PRESENCE_STATES.includes(value.state)
  );
}

/** `viewers` of a conversation object (list row or detail); missing or malformed means nobody. */
export function viewersOf(conversation: unknown): PresenceViewer[] {
  if (!isRecord(conversation) || !Array.isArray(conversation.viewers)) return [];
  const viewers: unknown[] = conversation.viewers;
  return viewers.filter(isViewer);
}
