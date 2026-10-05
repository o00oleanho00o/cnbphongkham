// ported from: web/src/dashboard-api-client.ts
//
// Deviations: the hand-written `request()` wrappers and the ~100 hand-written types became the typed
// `openapi-fetch` client over `schema.d.ts` (generated from backend/apps/api/openapi.json). Auth is the
// BE's httpOnly session cookie (first-party through the Next `/api` rewrite), so there is no token in
// JS. Errors are the BE's `ErrorResponse` (`code` + Vietnamese `message`, never PII) turned into an
// `ApiError`; a 401 outside `/auth/` sends the browser to `/login` exactly like the original.
import createClient from "openapi-fetch";

import type { ErrorCode } from "./index";
import type { paths } from "./schema";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code?: ErrorCode,
    public requestId?: string | null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Typed client. Paths already carry the `/api/v1` prefix, so the base URL is the page origin. */
export const http = createClient<paths>({ baseUrl: "", credentials: "include" });

type MaybeResult<T> = { data?: T; error?: unknown; response: Response };

function redirectToLogin(): void {
  if (typeof window === "undefined") return;
  // Outside the React tree there is no router; a full navigation also drops stale client state.
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- no router here
  if (window.location.pathname !== "/login") window.location.href = "/login";
}

/** FastAPI validation errors (`{detail: [...]}`) and anything else that is not our ErrorResponse. */
function messageFromUnknown(error: unknown, status: number): string {
  if (error && typeof error === "object") {
    const body = error as { error?: { message?: string }; detail?: unknown };
    if (body.error?.message) return body.error.message;
    if (typeof body.detail === "string") return body.detail;
  }
  return `Lỗi ${status}`;
}

/**
 * Await an openapi-fetch call and return its body, or throw `ApiError`. Empty bodies (204, DELETE)
 * resolve to `undefined`, which is why `T` is whatever the operation declares.
 */
export async function unwrap<T>(promise: Promise<MaybeResult<T>>): Promise<T> {
  let result: MaybeResult<T>;
  try {
    result = await promise;
  } catch {
    throw new ApiError(0, "Không kết nối được server");
  }
  const { data, error, response } = result;
  if (response.status === 401 && !new URL(response.url, "http://x").pathname.includes("/auth/")) {
    redirectToLogin();
    throw new ApiError(401, "Chưa đăng nhập", "unauthenticated");
  }
  if (!response.ok || error !== undefined) {
    const body = error as { error?: { code?: ErrorCode; request_id?: string | null } } | undefined;
    throw new ApiError(
      response.status,
      messageFromUnknown(error, response.status),
      body?.error?.code,
      body?.error?.request_id,
    );
  }
  return data as T;
}

/** One key per user action; reuse it when retrying the same action (BE returns the first result). */
export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

/** Readable message for a caught value in `catch (e)` blocks. */
export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : "Có lỗi xảy ra";
}
