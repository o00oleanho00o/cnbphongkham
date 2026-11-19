// Sign-in of the agent dashboard, answered by this server (there is no CRM behind it): the four session routes the
// screens already call (`POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, `POST /api/v1/auth/password`,
// `GET /api/v1/me`) are turned into calls to the agent's plugin `web`. Its login token is kept in the httpOnly cookie
// `pema_session`, so the browser's script never reads it; the agent and connector proxies send it on as
// `Authorization: Bearer`. The first sign-in on an agent without an account creates the account, as the plugin's own
// page does on its first visit. Any other `/api/v1` path answers 404.

import { agentBaseUrl } from "@/lib/server/agent-proxy";
import { type Env, errorResponse } from "@/lib/server/api-proxy";

const SESSION_COOKIE = "pema_session";
/** What an agent login may open on these screens: all of it (the plugin has one kind of account, the admin). */
const PERMISSIONS = ["admin.agents", "kb.read", "kb.manage", "admin.model", "admin.tools", "admin.usage"];

interface AgentSession {
  token: string;
  expires_at: string;
  email: string;
}

function isAgentSession(value: unknown): value is AgentSession {
  if (typeof value !== "object" || value === null) return false;
  const { token, expires_at: expiresAt, email } = value as Record<string, unknown>;
  return typeof token === "string" && token !== "" && typeof expiresAt === "string" && typeof email === "string";
}

function sessionToken(request: Request): string | null {
  for (const part of (request.headers.get("cookie") ?? "").split(";")) {
    const [name, ...value] = part.trim().split("=");
    if (name === SESSION_COOKIE) return value.join("=") || null;
  }
  return null;
}

/** Secure unless PEMA_SESSION_COOKIE_SECURE=false (plain HTTP over a private network); localhost counts as secure. */
function cookie(env: Env, value: string, maxAgeS: number): string {
  const secure = env.PEMA_SESSION_COOKIE_SECURE?.trim().toLowerCase() === "false" ? "" : "; Secure";
  return `${SESSION_COOKIE}=${value}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${maxAgeS}${secure}`;
}

function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store", ...headers },
  });
}

/** The agent's words for a refusal (FastAPI's `detail`), or a fallback. */
async function refusal(answer: Response, fallback: string): Promise<Response> {
  const body: unknown = await answer.json().catch(() => null);
  const detail = typeof body === "object" && body !== null ? (body as Record<string, unknown>).detail : undefined;
  const code = answer.status === 401 ? "unauthenticated" : answer.status === 429 ? "rate_limited" : "refused";
  return errorResponse(answer.status, code, typeof detail === "string" ? detail : fallback);
}

async function callAgent(
  env: Env,
  fetchImpl: typeof fetch,
  path: string,
  init: { method: "GET" | "POST"; token?: string; body?: unknown },
): Promise<Response | null> {
  const headers: Record<string, string> = { accept: "application/json" };
  if (init.token) headers.authorization = `Bearer ${init.token}`;
  if (init.body !== undefined) headers["content-type"] = "application/json";
  try {
    return await fetchImpl(`${agentBaseUrl(env).replace(/\/+$/, "")}${path}`, {
      method: init.method,
      headers,
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      cache: "no-store",
    });
  } catch {
    return null;
  }
}

const UNREACHABLE = () => errorResponse(502, "internal", "Không kết nối được dịch vụ agent.");

/** A good session answer of the agent becomes the cookie. */
async function signedIn(answer: Response, env: Env, now: number): Promise<Response> {
  const body: unknown = await answer.json().catch(() => null);
  if (!isAgentSession(body)) return errorResponse(502, "internal", "Dịch vụ agent trả lời không đúng dạng.");
  const maxAge = Math.max(0, Math.floor((Date.parse(body.expires_at) - now) / 1000));
  return json(200, { email: body.email }, { "set-cookie": cookie(env, body.token, maxAge) });
}

async function login(request: Request, env: Env, fetchImpl: typeof fetch, now: number): Promise<Response> {
  const credentials: unknown = await request.json().catch(() => null);
  const state = await callAgent(env, fetchImpl, "/v1/hooks/web/state", { method: "GET" });
  if (!state?.ok) return UNREACHABLE();
  const { needs_setup: needsSetup } = (await state.json().catch(() => ({}))) as { needs_setup?: unknown };
  const path = needsSetup === true ? "/v1/hooks/web/setup" : "/v1/hooks/web/login";
  const answer = await callAgent(env, fetchImpl, path, { method: "POST", body: credentials });
  if (!answer) return UNREACHABLE();
  if (!answer.ok) return refusal(answer, "Sai email hoặc mật khẩu.");
  return signedIn(answer, env, now);
}

async function me(request: Request, env: Env, fetchImpl: typeof fetch): Promise<Response> {
  const token = sessionToken(request);
  if (!token) return errorResponse(401, "unauthenticated", "Bạn cần đăng nhập.");
  const answer = await callAgent(env, fetchImpl, "/v1/plugins/web/me", { method: "GET", token });
  if (!answer) return UNREACHABLE();
  if (!answer.ok) return refusal(answer, "Bạn cần đăng nhập.");
  const { email } = (await answer.json().catch(() => ({}))) as { email?: unknown };
  const name = typeof email === "string" ? email : "";
  return json(200, {
    user: { id: name, clinic_id: "", clinic_name: "Agent", display_name: name, role: "owner" },
    permissions: PERMISSIONS,
  });
}

async function changePassword(request: Request, env: Env, fetchImpl: typeof fetch, now: number): Promise<Response> {
  const token = sessionToken(request);
  if (!token) return errorResponse(401, "unauthenticated", "Bạn cần đăng nhập.");
  const body: unknown = await request.json().catch(() => null);
  const answer = await callAgent(env, fetchImpl, "/v1/plugins/web/password", { method: "POST", token, body });
  if (!answer) return UNREACHABLE();
  if (!answer.ok) return refusal(answer, "Không đổi được mật khẩu.");
  return signedIn(answer, env, now);
}

function logout(env: Env): Response {
  return new Response(null, { status: 204, headers: { "set-cookie": cookie(env, "", 0), "cache-control": "no-store" } });
}

export interface AuthOptions {
  env?: Env;
  fetchImpl?: typeof fetch;
  now?: number;
}

/** Answers `/api/v1/**`: the session routes above, 404 for anything else. */
export async function answerAuth(request: Request, options: AuthOptions = {}): Promise<Response> {
  const env = options.env ?? process.env;
  const fetchImpl = options.fetchImpl ?? fetch;
  const now = options.now ?? Date.now();
  const { pathname } = new URL(request.url);
  const route = `${request.method} ${pathname.replace(/\/+$/, "")}`;
  if (route === "POST /api/v1/auth/login") return login(request, env, fetchImpl, now);
  if (route === "POST /api/v1/auth/logout") return logout(env);
  if (route === "POST /api/v1/auth/password") return changePassword(request, env, fetchImpl, now);
  if (route === "GET /api/v1/me") return me(request, env, fetchImpl);
  return errorResponse(404, "not_found", "Không tìm thấy đường dẫn này.");
}
