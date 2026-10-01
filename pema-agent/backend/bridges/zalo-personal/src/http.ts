/**
 * HTTP helpers of the bridge: response envelope, error mapping and body validation.
 *
 * New module (no TS original). Success is `{ok:true, ...}`; failure is `{ok:false, error:{kind, message,
 * code?}}` with `kind` from `ErrorKind`. A zca-js `ZaloApiError` carries a numeric `code` (the Zalo server
 * answered and refused: `zalo_rejected`); an error without one is a transport failure (`transport`), the
 * same distinction as `laLoiMayChuTuChoi` in the original `send-reply-in-parts.ts`.
 */
import type { Context } from "hono";
import type { z } from "zod";
import { toJson } from "./json.js";
import { laLoiMayChuTuChoi } from "./zalo-send.js";

export type AppEnv = { Variables: { rawBody: Uint8Array } };
export type AppContext = Context<AppEnv>;

export type ErrorKind =
  | "zalo_rejected"
  | "transport"
  | "bridge_disabled"
  | "kill_switch"
  | "rate_limited"
  | "blocked"
  | "not_running"
  | "bad_request"
  | "unauthorized";

const STATUS_BY_KIND: Readonly<Record<ErrorKind, number>> = {
  zalo_rejected: 502,
  transport: 502,
  bridge_disabled: 503,
  kill_switch: 409,
  rate_limited: 429,
  blocked: 409,
  not_running: 409,
  bad_request: 422,
  unauthorized: 401,
};

export function jsonResponse(status: number, body: unknown): Response {
  return new Response(toJson(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

export function ok(body: Record<string, unknown> = {}): Response {
  return jsonResponse(200, { ok: true, ...body });
}

export type FailOptions = { code?: number; status?: number };

export function fail(kind: ErrorKind, message: string, options: FailOptions = {}): Response {
  return jsonResponse(options.status ?? STATUS_BY_KIND[kind], {
    ok: false,
    error: { kind, message, ...(options.code === undefined ? {} : { code: options.code }) },
  });
}

const MAX_MESSAGE_LENGTH = 300;

/** Map a thrown zca-js error to the envelope (HTTP 502 for both kinds). */
export function failFromThrown(err: unknown): Response {
  const message =
    err instanceof Error && err.message ? err.message.slice(0, MAX_MESSAGE_LENGTH) : "Zalo request failed";
  if (laLoiMayChuTuChoi(err)) {
    return fail("zalo_rejected", message, { code: (err as { code: number }).code });
  }
  return fail("transport", message);
}

export type Parsed<T> = { ok: true; data: T } | { ok: false; response: Response };

/** Only the paths and rules of the failed fields: a value may be a secret and is never echoed. */
function describeIssues(error: z.ZodError): string {
  return error.issues
    .slice(0, 5)
    .map((issue) => `${issue.path.join(".") || "body"}: ${issue.message}`)
    .join("; ");
}

export function parseJsonBody<T>(c: AppContext, schema: z.ZodType<T>): Parsed<T> {
  const raw = c.get("rawBody");
  const text = new TextDecoder().decode(raw);
  const value = parseJsonText(text);
  if (!value.ok) return { ok: false, response: fail("bad_request", "Body is not valid JSON", { status: 400 }) };
  const result = schema.safeParse(value.value);
  if (!result.success) {
    return { ok: false, response: fail("bad_request", describeIssues(result.error)) };
  }
  return { ok: true, data: result.data };
}

function parseJsonText(text: string): { ok: true; value: unknown } | { ok: false } {
  try {
    return { ok: true, value: JSON.parse(text === "" ? "{}" : text) as unknown };
  } catch {
    return { ok: false };
  }
}

export function parseQuery<T>(c: AppContext, schema: z.ZodType<T>): Parsed<T> {
  const result = schema.safeParse(c.req.query());
  if (!result.success) {
    return { ok: false, response: fail("bad_request", describeIssues(result.error)) };
  }
  return { ok: true, data: result.data };
}
