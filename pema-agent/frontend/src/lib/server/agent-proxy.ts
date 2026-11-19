// The same-origin proxy from the browser to the agent service.
//
// The browser calls `/agent/v1/**` (the agent's API) and `/agent/ui/**` (the pages its plugins ship) with its session
// cookie, which holds the agent's own login token (`agent-auth.ts` sets it). This server drops the cookie, sends the
// token as `Authorization: Bearer` and streams the answer back; the agent checks it. The header and path rules are
// those of `api-proxy.ts`.

import {
  decodeSegment,
  type Env,
  errorResponse,
  isUnsafeSegment,
  parseHttpUrl,
  requestHeadersForUpstream,
  responseHeadersFromUpstream,
} from "@/lib/server/api-proxy";

export const AGENT_PREFIX = "/agent";
const FORWARDED = ["/v1/", "/ui/"];
const DEFAULT_AGENT_URL = "http://127.0.0.1:8088";
const SESSION_COOKIE = "pema_session";
const BODYLESS_METHODS = new Set(["GET", "HEAD"]);

/** The address of the agent service, read now (not at build time). */
export function agentBaseUrl(env: Env = process.env): string {
  return env.PEMA_AGENT_INTERNAL_URL?.trim() || DEFAULT_AGENT_URL;
}

export type AgentUpstream =
  { ok: true; url: URL } | { ok: false; status: 400 | 404 | 502; message: string };

const BAD_CONFIG: AgentUpstream = {
  ok: false,
  status: 502,
  message: "Địa chỉ dịch vụ agent chưa được cấu hình đúng.",
};
const BAD_PATH: AgentUpstream = { ok: false, status: 400, message: "Đường dẫn không hợp lệ." };
const NOT_FOUND: AgentUpstream = { ok: false, status: 404, message: "Không tìm thấy đường dẫn." };

/** `/agent/v1/x` → `<agent>/v1/x`; only the agent's API and plugin pages, never a path that climbs out. */
export function resolveAgentUpstream(
  pathname: string,
  search: string,
  base: string,
): AgentUpstream {
  return resolveUnder(AGENT_PREFIX, pathname, search, base);
}

/** The same for any service the clinic web fronts: `<prefix>/v1/x` → `<base>/v1/x` (connectors reuse it). */
export function resolveUnder(
  prefixPath: string,
  pathname: string,
  search: string,
  base: string,
): AgentUpstream {
  const baseUrl = parseHttpUrl(base);
  if (!baseUrl) return BAD_CONFIG;
  const rest = pathname.startsWith(`${prefixPath}/`) ? pathname.slice(prefixPath.length) : "";
  if (!FORWARDED.some((prefix) => rest.startsWith(prefix))) return NOT_FOUND;

  const segments = rest.split("/").slice(1).map(decodeSegment);
  if (segments.some((segment) => segment === null || isUnsafeSegment(segment))) return BAD_PATH;

  const prefix = baseUrl.pathname.replace(/\/+$/, "");
  const url = new URL(`${prefix}${rest}${search}`, baseUrl.origin);
  const stillInside =
    url.origin === baseUrl.origin &&
    FORWARDED.some((allowed) => url.pathname.startsWith(`${prefix}${allowed}`));
  return stillInside ? { ok: true, url } : BAD_PATH;
}

/** The session cookie's value (the agent's login token), or null. */
export function sessionOf(cookieHeader: string | null): string | null {
  for (const part of (cookieHeader ?? "").split(";")) {
    const [name, ...value] = part.trim().split("=");
    if (name === SESSION_COOKIE) return value.join("=") || null;
  }
  return null;
}

export type TokenResult = { ok: true; token: string } | { ok: false; response: Response };

/** The token of a session is the session cookie itself: the agent's login token. */
export class AgentTokens {
  async get(session: string, _env: Env, _fetchImpl: typeof fetch): Promise<TokenResult> {
    return { ok: true, token: session };
  }

  forget(_session: string): void {}
}

export const sharedTokens = new AgentTokens();

export interface AgentForwardOptions {
  env?: Env;
  fetchImpl?: typeof fetch;
  tokens?: AgentTokens;
}

/** Forward one request to the agent service as the signed-in staff member and stream its answer back. */
export async function forwardToAgent(
  request: Request,
  options: AgentForwardOptions = {},
): Promise<Response> {
  const base = agentBaseUrl(options.env ?? process.env);
  const incoming = new URL(request.url);
  const resolved = resolveAgentUpstream(incoming.pathname, incoming.search, base);
  return forwardResolved(request, resolved, { base, prefixPath: AGENT_PREFIX }, options);
}

/**
 * Forward a request whose upstream is resolved: the session cookie becomes the bearer token, the cookie is dropped and the answer streams back. `prefixPath` is what the browser sees in
 * front of the upstream's own paths (a relative `Location` gets it back).
 */
export async function forwardResolved(
  request: Request,
  resolved: AgentUpstream,
  where: { base: string; prefixPath: string; label?: string },
  options: AgentForwardOptions = {},
): Promise<Response> {
  const env = options.env ?? process.env;
  const fetchImpl = options.fetchImpl ?? fetch;
  const tokens = options.tokens ?? sharedTokens;
  const { base, prefixPath } = where;
  if (!resolved.ok) {
    const code =
      resolved.status === 404
        ? "not_found"
        : resolved.status === 400
          ? "validation_failed"
          : "internal";
    return errorResponse(resolved.status, code, resolved.message);
  }

  const session = sessionOf(request.headers.get("cookie"));
  if (!session) return errorResponse(401, "unauthenticated", "Bạn cần đăng nhập.");
  const token = await tokens.get(session, env, fetchImpl);
  if (!token.ok) return token.response;

  const headers = requestHeadersForUpstream(request.headers);
  headers.delete("cookie");
  headers.set("authorization", `Bearer ${token.token}`);
  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers,
    redirect: "manual",
    cache: "no-store",
    signal: request.signal,
  };
  if (!BODYLESS_METHODS.has(request.method) && request.body) {
    init.body = request.body;
    init.duplex = "half";
  }

  let upstream: Response;
  try {
    upstream = await fetchImpl(resolved.url, init);
  } catch {
    return errorResponse(502, "internal", `Không kết nối được ${where.label ?? "dịch vụ agent"}.`);
  }
  if (upstream.status === 401) tokens.forget(session);

  const out = responseHeadersFromUpstream(upstream, new URL(base));
  out.delete("set-cookie");
  const location = out.get("location");
  if (location?.startsWith("/") && !location.startsWith("//")) {
    out.set("location", `${prefixPath}${location}`);
  }
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: out,
  });
}
