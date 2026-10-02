// Calls of the live package. Presence goes through the typed client (`http`, generated from the OpenAPI) and
// `unwrap`, so a 401 still sends the browser to /login and an error is the BE's Vietnamese `ApiError`.
// (`GET /api/v1/staff/assignable` is in the generated client now: see `lib/staff/`.)
import { http, unwrap } from "@/lib/api/client";

import type { PresenceState } from "@/lib/live/live-types";

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
