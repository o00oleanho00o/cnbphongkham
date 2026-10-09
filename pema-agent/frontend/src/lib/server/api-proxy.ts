// Pema addition (no zalo-agent original): the same-origin proxy from the browser to the API.
//
// Why a route handler and not `rewrites()` in next.config.ts: Next.js evaluates `rewrites()` at BUILD time and
// bakes the result into the standalone server, so the API address had to be a Docker build argument and a new
// address meant a new image. This module reads `PEMA_API_INTERNAL_URL` on EVERY request, so one image runs
// against any API address. The browser still talks only to its own origin: the session cookie stays
// first-party and there is no CORS.
//
// Rules, in order of importance:
//   1. Only `/api/v1/**` is forwarded (and `/healthz`). A path with `.`/`..` segments (also percent-encoded),
//      an encoded slash, a backslash or a NUL is refused, so the proxy cannot be pointed at another API route.
//   2. Hop-by-hop headers are never forwarded in either direction (RFC 9110 section 7.6.1), nor are the
//      forwarding headers a client can forge (`x-forwarded-*`, `forwarded`, `x-real-ip`): the API decides
//      the client address from its own socket peer (see backend `client_ip.py`).
//   3. Method, query, headers, cookies and body go through as they are; the body and the response are streamed
//      (no buffering, no caching). Every `Set-Cookie` of the answer is kept as its own header.

/** The slice of `process.env` this module reads; tests pass a plain object. */
export type Env = Readonly<Record<string, string | undefined>>;

export const API_PREFIX = "/api/v1/";
export const HEALTH_PATH = "/healthz";
const DEFAULT_API_URL = "http://127.0.0.1:8000";

/** Hop-by-hop headers (RFC 9110 section 7.6.1) plus `host` (set from the upstream URL by fetch). */
const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "proxy-connection",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

/** Headers a client can send to forge its address or origin; the API must not see them from the browser. */
const FORGEABLE = new Set([
  "host",
  "forwarded",
  "x-forwarded-for",
  "x-forwarded-host",
  "x-forwarded-proto",
  "x-forwarded-port",
  "x-real-ip",
]);

const BODYLESS_METHODS = new Set(["GET", "HEAD"]);

/** The address of the API, read now (not at build time). `PEMA_API_INTERNAL_URL` wins over `PEMA_API_URL`. */
export function apiBaseUrl(env: Env = process.env): string {
  const configured = env.PEMA_API_INTERNAL_URL?.trim() || env.PEMA_API_URL?.trim();
  return configured || DEFAULT_API_URL;
}

export type UpstreamResolution =
  { ok: true; url: URL } | { ok: false; status: 400 | 404 | 502; message: string };

/** True when one decoded path segment could move the request outside the intended path. */
export function isUnsafeSegment(decoded: string): boolean {
  return (
    decoded === "." ||
    decoded === ".." ||
    decoded.includes("/") ||
    decoded.includes("\\") ||
    decoded.includes("\0")
  );
}

/** One percent-decoded path segment, or null when it is not valid percent-encoding. */
export function decodeSegment(segment: string): string | null {
  try {
    return decodeURIComponent(segment);
  } catch {
    return null;
  }
}

export function parseHttpUrl(value: string): URL | null {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url : null;
  } catch {
    return null;
  }
}

const BAD_CONFIG: UpstreamResolution = {
  ok: false,
  status: 502,
  message: "Địa chỉ API chưa được cấu hình đúng.",
};
const BAD_PATH: UpstreamResolution = { ok: false, status: 400, message: "Đường dẫn không hợp lệ." };
const NOT_FOUND: UpstreamResolution = {
  ok: false,
  status: 404,
  message: "Không tìm thấy đường dẫn.",
};

/**
 * Turn the path the browser asked for into the upstream URL, or say why not. `pathname` is the raw
 * (still percent-encoded) path of the incoming request; it is forwarded as it is once it is proven safe.
 */
export function resolveUpstream(
  pathname: string,
  search: string,
  base: string,
): UpstreamResolution {
  const baseUrl = parseHttpUrl(base);
  if (!baseUrl) return BAD_CONFIG;
  if (pathname !== HEALTH_PATH && !pathname.startsWith(API_PREFIX)) return NOT_FOUND;

  const decodedSegments = pathname.split("/").slice(1).map(decodeSegment);
  const unsafe = decodedSegments.some((segment) => segment === null || isUnsafeSegment(segment));
  if (unsafe) return BAD_PATH;

  // The base may carry a path prefix of its own (API behind a sub-path); keep it and add ours.
  const prefix = baseUrl.pathname.replace(/\/+$/, "");
  const url = new URL(`${prefix}${pathname}${search}`, baseUrl.origin);
  // Belt and braces: whatever the URL parser did with the path, the result must still be under the API prefix
  // (or the health path) of the same origin.
  const stillInside =
    url.origin === baseUrl.origin &&
    (url.pathname === `${prefix}${HEALTH_PATH}` ||
      url.pathname.startsWith(`${prefix}${API_PREFIX}`));
  return stillInside ? { ok: true, url } : BAD_PATH;
}

/** Names listed in the `Connection` header are hop-by-hop for this connection too. */
function connectionTokens(headers: Headers): Set<string> {
  const names = (headers.get("connection") ?? "")
    .split(",")
    .map((token) => token.trim().toLowerCase())
    .filter((name) => name !== "");
  return new Set(names);
}

/** Headers the proxy drops on the way to the API. `accept-encoding`: the API answers identity-encoded; asking
 * for gzip would only make fetch decode what we then re-label. */
function isDroppedRequestHeader(key: string, perConnection: Set<string>): boolean {
  return (
    HOP_BY_HOP.has(key) || FORGEABLE.has(key) || perConnection.has(key) || key === "accept-encoding"
  );
}

export function requestHeadersForUpstream(incoming: Headers): Headers {
  const perConnection = connectionTokens(incoming);
  const out = new Headers();
  incoming.forEach((value, name) => {
    if (isDroppedRequestHeader(name.toLowerCase(), perConnection)) return;
    out.append(name, value);
  });
  return out;
}

/** `origin` of the API turned into a relative `Location`, so a redirect does not send the browser to `api:8000`. */
function relativeLocation(location: string, base: URL): string {
  try {
    const target = new URL(location, base);
    if (target.origin === base.origin) return `${target.pathname}${target.search}${target.hash}`;
  } catch {
    // not a URL: leave it alone
  }
  return location;
}

/** `set-cookie` is appended one by one below (`forEach` would join them with a comma). Once fetch has decoded the
 * body, the length and encoding of the wire no longer describe it. */
function isDroppedResponseHeader(
  key: string,
  perConnection: Set<string>,
  decoded: boolean,
): boolean {
  if (key === "set-cookie") return true;
  if (HOP_BY_HOP.has(key) || perConnection.has(key)) return true;
  return decoded && (key === "content-encoding" || key === "content-length");
}

export function responseHeadersFromUpstream(upstream: Response, base: URL): Headers {
  const perConnection = connectionTokens(upstream.headers);
  const decoded = upstream.headers.has("content-encoding");
  const out = new Headers();
  upstream.headers.forEach((value, name) => {
    const key = name.toLowerCase();
    if (isDroppedResponseHeader(key, perConnection, decoded)) return;
    out.append(name, key === "location" ? relativeLocation(value, base) : value);
  });
  upstream.headers.getSetCookie().forEach((cookie) => out.append("set-cookie", cookie));
  return out;
}

export function errorResponse(status: number, code: string, message: string): Response {
  return Response.json(
    { error: { code, message, request_id: null } },
    { status, headers: { "cache-control": "no-store" } },
  );
}

export interface ForwardOptions {
  /** Defaults to the runtime environment; tests pass their own. */
  env?: Env;
  fetchImpl?: typeof fetch;
}

/** Forward one request to the API and stream its answer back. */
export async function forwardToApi(
  request: Request,
  options: ForwardOptions = {},
): Promise<Response> {
  const base = apiBaseUrl(options.env);
  const incoming = new URL(request.url);
  const resolved = resolveUpstream(incoming.pathname, incoming.search, base);
  if (!resolved.ok) {
    const code = resolved.status === 404 ? "not_found" : "validation_failed";
    return errorResponse(
      resolved.status,
      resolved.status === 502 ? "internal" : code,
      resolved.message,
    );
  }

  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers: requestHeadersForUpstream(request.headers),
    redirect: "manual",
    cache: "no-store",
    signal: request.signal,
  };
  if (!BODYLESS_METHODS.has(request.method) && request.body) {
    init.body = request.body;
    init.duplex = "half"; // required by undici to stream a request body
  }

  let upstream: Response;
  try {
    upstream = await (options.fetchImpl ?? fetch)(resolved.url, init);
  } catch {
    // The reason (host, port) stays out of the answer and out of the log: it is infrastructure detail.
    return errorResponse(502, "internal", "Không kết nối được máy chủ API.");
  }

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeadersFromUpstream(upstream, new URL(base)),
  });
}
