/**
 * HMAC authentication of the bridge wire protocol, in BOTH directions (API -> bridge requests and
 * bridge -> API events).
 *
 * New module (no TS original). Signature = lowercase hex HMAC-SHA256(secret, `${timestamp}.${rawBody}`)
 * with the timestamp in unix seconds sent as `X-Pema-Timestamp` and the signature as `X-Pema-Signature`.
 * A request without a body signs the empty string. A request is rejected when the signature does not
 * match (constant-time compare) or when |now - timestamp| > 300 s.
 */
import { createHmac, timingSafeEqual } from "node:crypto";

export const TIMESTAMP_HEADER = "X-Pema-Timestamp";
export const SIGNATURE_HEADER = "X-Pema-Signature";
/** Largest clock difference accepted between the two sides, in seconds. */
export const MAX_CLOCK_SKEW_SECONDS = 300;

export type RawBody = Uint8Array | string;

export type SignedHeaders = Record<string, string>;

export function computeSignature(secret: string, timestamp: string, body: RawBody): string {
  return createHmac("sha256", secret)
    .update(`${timestamp}.`)
    .update(typeof body === "string" ? Buffer.from(body, "utf8") : body)
    .digest("hex");
}

export function signedHeaders(
  secret: string,
  body: RawBody,
  nowSeconds: number = Math.floor(Date.now() / 1000),
): SignedHeaders {
  const timestamp = String(nowSeconds);
  return {
    [TIMESTAMP_HEADER]: timestamp,
    [SIGNATURE_HEADER]: computeSignature(secret, timestamp, body),
  };
}

export type VerifyFailure =
  "missing_headers" | "bad_timestamp" | "stale_timestamp" | "bad_signature";

export type VerifyResult = { ok: true } | { ok: false; reason: VerifyFailure };

const TIMESTAMP_PATTERN = /^\d{1,12}$/;
const SIGNATURE_PATTERN = /^[0-9a-f]{64}$/;

export type VerifyInput = {
  secret: string;
  timestamp: string | null | undefined;
  signature: string | null | undefined;
  body: RawBody;
  nowSeconds: number;
};

function constantTimeEqualHex(expected: string, received: string): boolean {
  const left = Buffer.from(expected, "hex");
  const right = Buffer.from(received, "hex");
  return left.length === right.length && timingSafeEqual(left, right);
}

export function verifySignature(input: VerifyInput): VerifyResult {
  const { secret, timestamp, signature, body, nowSeconds } = input;
  if (!timestamp || !signature) return { ok: false, reason: "missing_headers" };
  if (!TIMESTAMP_PATTERN.test(timestamp)) return { ok: false, reason: "bad_timestamp" };
  if (Math.abs(nowSeconds - Number(timestamp)) > MAX_CLOCK_SKEW_SECONDS) {
    return { ok: false, reason: "stale_timestamp" };
  }
  // Lowercase hex only, exactly 64 characters: anything else cannot be a valid signature.
  const received = signature.toLowerCase();
  if (!SIGNATURE_PATTERN.test(received)) return { ok: false, reason: "bad_signature" };
  const expected = computeSignature(secret, timestamp, body);
  if (!constantTimeEqualHex(expected, received)) return { ok: false, reason: "bad_signature" };
  return { ok: true };
}
