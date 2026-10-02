// Calls of the live package. Presence goes through the typed client (`http`, generated from the OpenAPI) and
// `unwrap`, so a 401 still sends the browser to /login and an error is the BE's Vietnamese `ApiError`.
// STILL TEMPORARY: `GET /api/v1/staff/assignable` is not in the generated client yet (another package owns the
// route), so `fetchAssignableStaff` keeps a hand-written request.
import { http, unwrap } from "@/lib/api/client";

import {
  parseAssignableStaff,
  type AssignableStaff,
  type PresenceState,
} from "@/lib/live/live-types";

type RawResult = { data?: unknown; error?: unknown; response: Response };

async function rawGet(path: string, signal?: AbortSignal): Promise<RawResult> {
  const response = await fetch(path, { method: "GET", credentials: "include", signal });
  const text = await response.text();
  const parsed: unknown = text ? safeJson(text) : undefined;
  return response.ok ? { data: parsed, response } : { error: parsed, response };
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

/** `GET /api/v1/staff/assignable`: who a task or a conversation can be handed to. */
export async function fetchAssignableStaff(signal?: AbortSignal): Promise<AssignableStaff[]> {
  const data = await unwrap(rawGet("/api/v1/staff/assignable", signal));
  return parseAssignableStaff(data);
}

/** `POST /api/v1/conversations/{id}/presence`: "I am looking at / answering this". Best effort. */
export async function postPresence(conversationId: string, state: PresenceState): Promise<void> {
  await unwrap(
    http.POST("/api/v1/conversations/{conversation_id}/presence", {
      params: { path: { conversation_id: conversationId } },
      body: { state },
    }),
  );
}

/** `DELETE /api/v1/conversations/{id}/presence`: "I closed it", so colleagues stop seeing me at once. */
export async function leavePresence(conversationId: string): Promise<void> {
  await unwrap(
    http.DELETE("/api/v1/conversations/{conversation_id}/presence", {
      params: { path: { conversation_id: conversationId } },
    }),
  );
}
