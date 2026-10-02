// `GET /api/v1/staff/assignable`: the colleagues a task or a conversation can be handed to. Any signed-in staff
// member may call it; the BE lists only ACTIVE staff whose role can work conversations and CRM tasks, with `id`,
// `name` and `role` and nothing else, and checks the same rule again when the assignee is saved.
//
// The Inbox mounts one thread view per conversation (`key={selectedId}`), so switching conversations would call the
// route every time (it is limited to 60 a minute per user). The answer is therefore shared for a minute; a failed
// call is never kept, and `invalidateAssignableStaff` drops it (the picker's "Thử lại" button).
import type { Schemas } from "@/lib/api";
import { http, unwrap } from "@/lib/api/client";

export type AssignableStaff = Schemas["AssignableStaffOut"];

export const ASSIGNABLE_STAFF_TTL_MS = 60_000;

type Shared = { at: number; request: Promise<AssignableStaff[]> };

/** One slot for the whole page; a holder object because the answer is replaced, never mutated. */
const cache: { current: Shared | null } = { current: null };

export function invalidateAssignableStaff(): void {
  cache.current = null;
}

function abortError(): Error {
  const error = new Error("aborted");
  error.name = "AbortError";
  return error;
}

/** The caller's own cancellation must not cancel the request other callers are waiting on. */
function waitFor<T>(request: Promise<T>, signal?: AbortSignal): Promise<T> {
  if (!signal) return request;
  return new Promise<T>((resolve, reject) => {
    if (signal.aborted) {
      reject(abortError());
      return;
    }
    const onAbort = () => reject(abortError());
    signal.addEventListener("abort", onAbort, { once: true });
    request.then(
      (value) => {
        signal.removeEventListener("abort", onAbort);
        resolve(value);
      },
      (error: unknown) => {
        signal.removeEventListener("abort", onAbort);
        reject(error instanceof Error ? error : new Error(String(error)));
      },
    );
  });
}

function startRequest(): Shared {
  const request: Promise<AssignableStaff[]> = unwrap(http.GET("/api/v1/staff/assignable")).catch(
    (error: unknown) => {
      if (cache.current?.request === request) cache.current = null;
      throw error;
    },
  );
  return { at: Date.now(), request };
}

function isFresh(entry: Shared | null): entry is Shared {
  return entry !== null && Date.now() - entry.at <= ASSIGNABLE_STAFF_TTL_MS;
}

export function fetchAssignableStaff(signal?: AbortSignal): Promise<AssignableStaff[]> {
  const entry = isFresh(cache.current) ? cache.current : startRequest();
  cache.current = entry;
  return waitFor(entry.request, signal);
}
