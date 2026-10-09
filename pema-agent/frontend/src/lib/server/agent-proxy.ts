// Pema addition (plan C, docs/HANDOFF-agent-v2.md): the same-origin proxy from the browser to the agent service.
//
// The browser calls `/agent/v1/**` (the agent's API) and `/agent/ui/**` (the pages its plugins ship) with its
// clinic session cookie. This server asks the clinic API for a short agent token with that cookie, which is
// also the sign-in and permission check (`admin.agents`), drops the cookie, sends the token as
// `Authorization: Bearer` and streams the answer back. The browser never holds an agent token and the agent
// never sees the cookie. A token is kept per session until shortly before it expires, so the calls of one page
// cost one token request. The header and path rules are those of `api-proxy.ts`.

import { createHash } from "node:crypto";

import {
  apiBaseUrl,
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
const TOKEN_PATH = "/api/v1/auth/agent-token";
/** A token is used only while it has this long left, so it cannot expire on the way. */
const MARGIN_MS = 20_000;
const MAX_CACHED = 500;
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
  const baseUrl = parseHttpUrl(base);
  if (!baseUrl) return BAD_CONFIG;
  const rest = pathname.startsWith(`${AGENT_PREFIX}/`) ? pathname.slice(AGENT_PREFIX.length) : "";
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

/** The clinic session cookie's value, or null. */
export function sessionOf(cookieHeader: string | null): string | null {
  for (const part of (cookieHeader ?? "").split(";")) {
    const [name, ...value] = part.trim().split("=");
    if (name === SESSION_COOKIE) return value.join("=") || null;
  }
  return null;
}

export type TokenResult = { ok: true; token: string } | { ok: false; response: Response };

interface Cached {
  token: string;
  expiresAt: number;
}

interface TokenAnswer {
  token: string;
  expires_at: string;
}

function isTokenAnswer(value: unknown): value is TokenAnswer {
  if (typeof value !== "object" || value === null) return false;
  const { token, expires_at: expiresAt } = value as Record<string, unknown>;
  return typeof token === "string" && token !== "" && typeof expiresAt === "string";
}

/** Agent tokens per clinic session, asked of the clinic API with the session cookie. */
export class AgentTokens {
  private readonly cached = new Map<string, Cached>();
  private readonly pending = new Map<string, Promise<TokenResult>>();

  constructor(private readonly now: () => number = Date.now) {}

  async get(session: string, env: Env, fetchImpl: typeof fetch): Promise<TokenResult> {
    const key = createHash("sha256").update(session).digest("hex");
    const found = this.cached.get(key);
    if (found && found.expiresAt - this.now() > MARGIN_MS) return { ok: true, token: found.token };
    const running = this.pending.get(key);
    if (running) return running;
    const asked = this.ask(key, session, env, fetchImpl).finally(() => this.pending.delete(key));
    this.pending.set(key, asked);
    return asked;
  }

  forget(session: string): void {
    this.cached.delete(createHash("sha256").update(session).digest("hex"));
  }

  private async ask(
    key: string,
    session: string,
    env: Env,
    fetchImpl: typeof fetch,
  ): Promise<TokenResult> {
    let answer: Response;
    try {
      answer = await fetchImpl(`${apiBaseUrl(env).replace(/\/+$/, "")}${TOKEN_PATH}`, {
        method: "POST",
        headers: { cookie: `${SESSION_COOKIE}=${session}`, accept: "application/json" },
        cache: "no-store",
      });
    } catch {
      return {
        ok: false,
        response: errorResponse(502, "internal", "Không kết nối được máy chủ API."),
      };
    }
    if (answer.status === 401 || answer.status === 403) {
      // The API's own words: not signed in, or no right to manage the agent.
      return {
        ok: false,
        response: new Response(answer.body, {
          status: answer.status,
          headers: { "content-type": "application/json", "cache-control": "no-store" },
        }),
      };
    }
    const body: unknown = answer.ok ? await answer.json().catch(() => null) : null;
    const expiresAt = isTokenAnswer(body) ? Date.parse(body.expires_at) : Number.NaN;
    if (!isTokenAnswer(body) || Number.isNaN(expiresAt)) {
      return {
        ok: false,
        response: errorResponse(502, "internal", "Không lấy được quyền truy cập dịch vụ agent."),
      };
    }
    this.keep(key, { token: body.token, expiresAt });
    return { ok: true, token: body.token };
  }

  private keep(key: string, entry: Cached): void {
    this.cached.set(key, entry);
    if (this.cached.size <= MAX_CACHED) return;
    const now = this.now();
    for (const [name, cached] of this.cached) {
      if (cached.expiresAt <= now) this.cached.delete(name);
    }
    const oldest = this.cached.keys().next();
    if (this.cached.size > MAX_CACHED && !oldest.done) this.cached.delete(oldest.value);
  }
}

const sharedTokens = new AgentTokens();

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
  const env = options.env ?? process.env;
  const fetchImpl = options.fetchImpl ?? fetch;
  const tokens = options.tokens ?? sharedTokens;
  const base = agentBaseUrl(env);
  const incoming = new URL(request.url);
  const resolved = resolveAgentUpstream(incoming.pathname, incoming.search, base);
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
    return errorResponse(502, "internal", "Không kết nối được dịch vụ agent.");
  }
  if (upstream.status === 401) tokens.forget(session);

  const out = responseHeadersFromUpstream(upstream, new URL(base));
  out.delete("set-cookie");
  const location = out.get("location");
  if (location?.startsWith("/") && !location.startsWith("//")) {
    out.set("location", `${AGENT_PREFIX}${location}`);
  }
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: out,
  });
}
