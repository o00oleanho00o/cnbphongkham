// TEMPORARY: calls for routes that are not in the generated client yet (see live-types.ts). They go through
// `unwrap`, so a 401 still sends the browser to /login and an error is the BE's Vietnamese `ApiError`.
// The integration package replaces them with `http.GET/POST` of the typed client.
import { unwrap } from "@/lib/api/client";

import {
  parseAssignableStaff,
  type AssignableStaff,
  type PresenceState,
} from "@/lib/live/live-types";

type RawResult = { data?: unknown; error?: unknown; response: Response };

async function rawRequest(
  method: "GET" | "POST",
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<RawResult> {
  const response = await fetch(path, {
    method,
    credentials: "include",
    signal,
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
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
  const data = await unwrap(rawRequest("GET", "/api/v1/staff/assignable", undefined, signal));
  return parseAssignableStaff(data);
}

/** `POST /api/v1/conversations/{id}/presence`: "I am looking at / answering this". Best effort. */
export async function postPresence(conversationId: string, state: PresenceState): Promise<void> {
  const path = `/api/v1/conversations/${encodeURIComponent(conversationId)}/presence`;
  await unwrap(rawRequest("POST", path, { state }));
}
