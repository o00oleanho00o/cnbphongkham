// Types of live events come from the generated client (`Schemas[...]`, backend `pema_contracts/live.py`):
//
//   GET    /api/v1/events                            SSE; each event is JSON `{type, id}`; no message text
//                                                    (`appointments.changed`: id is the appointment; `tasks.changed`: the task)
//
// The `parse*` helper below stays: an SSE `data:` line is untrusted runtime input.
// (`GET /api/v1/staff/assignable` is not here: it is in the generated client, see `lib/staff/`.)
import type { Schemas } from "@/lib/api";

export type LiveEventType = Schemas["LiveEventType"];

/** Every generated event type, so a type added on the backend fails `tsc` here until it is handled. */
const EVENT_TYPE_SET: Record<LiveEventType, true> = {
  "tasks.changed": true,
  "appointments.changed": true,
};

/** What changed, never the content: `id` is the object (appointment, task) or null for "some". */
export type LiveEvent = { type: LiveEventType; id: string | null };

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
