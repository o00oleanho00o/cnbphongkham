// The `api` of the plugin SDK (plan C): the agent dashboard's `lib/api.ts` contract on the clinic web. Plugin code
// passes the agent's own paths (`/v1/...`, `/ui/...`); every call goes same-origin to `/agent<path>` with the
// session cookie, and the server-side proxy (`src/lib/server/agent-proxy.ts`) adds the agent token. Errors keep
// the server's words: the gateway and the clinic API answer `{error: {message}}`, plugin routes `{detail}`.
import { redirectToLogin } from "@/lib/api/client";

export const AGENT_PREFIX = "/agent";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly payload?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface Api {
  request<T>(method: Method, path: string, body?: unknown): Promise<T>;
  get<T>(path: string): Promise<T>;
  post<T>(path: string, body?: unknown): Promise<T>;
  put<T>(path: string, body?: unknown): Promise<T>;
  patch<T>(path: string, body?: unknown): Promise<T>;
  del<T>(path: string): Promise<T>;
}

function fieldMessages(detail: unknown[]): string {
  return detail
    .map((item: unknown) =>
      typeof item === "object" && item !== null ? (item as { msg?: unknown }).msg : undefined,
    )
    .filter((msg): msg is string => typeof msg === "string")
    .join("; ");
}

/** The message of an error answer: `{error: {message}}`, `{detail: "..."}` or the field errors of a 422. */
export function errorText(payload: unknown, status: number): string {
  if (typeof payload !== "object" || payload === null) return `Lỗi ${status}`;
  const { error, detail } = payload as { error?: unknown; detail?: unknown };
  const message =
    typeof error === "object" && error !== null ? (error as { message?: unknown }).message : null;
  if (typeof message === "string") return message;
  if (typeof detail === "string") return detail;
  const fields = Array.isArray(detail) ? fieldMessages(detail) : "";
  return fields || `Lỗi ${status}`;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

export interface AgentApiOptions {
  fetcher?: typeof fetch;
  /** A 401: the clinic session ended (the proxy found no session or the API refused it). */
  onUnauthorized?: () => void;
}

export function createAgentApi({
  fetcher = (...args) => fetch(...args),
  onUnauthorized = redirectToLogin,
}: AgentApiOptions = {}): Api {
  async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    let response: Response;
    try {
      response = await fetcher(`${AGENT_PREFIX}${path}`, {
        method,
        headers,
        credentials: "same-origin",
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throw new ApiError(0, "Không kết nối được máy chủ.");
    }
    const text = await response.text();
    const payload: unknown = text ? safeJson(text) : undefined;
    if (response.ok) return payload as T;
    if (response.status === 401) onUnauthorized();
    throw new ApiError(response.status, errorText(payload, response.status), payload);
  }
  return {
    request,
    get: (path) => request("GET", path),
    post: (path, body) => request("POST", path, body),
    put: (path, body) => request("PUT", path, body),
    patch: (path, body) => request("PATCH", path, body),
    del: (path) => request("DELETE", path),
  };
}

export const agentApi = createAgentApi();
