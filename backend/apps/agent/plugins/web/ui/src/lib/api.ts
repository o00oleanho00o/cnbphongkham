/**
 * Calls to the agent's gateway with the session's bearer token. Errors keep the server's own words: the
 * gateway answers `{error: {kind, message}}`, plugin routes `{detail}` (a list of field errors on 422).
 * A 401 on a signed-in call means the login ended: the session is dropped and the sign-in screen returns.
 */
import { getSession, setSession } from "./session";

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

export function errorText(payload: unknown, status: number): string {
  if (typeof payload === "object" && payload !== null) {
    const p = payload as Record<string, unknown>;
    const error = p.error as Record<string, unknown> | undefined;
    if (error && typeof error.message === "string") return error.message;
    if (typeof p.detail === "string") return p.detail;
    if (Array.isArray(p.detail)) {
      const parts = p.detail
        .map((item: unknown) => (item as { msg?: unknown }).msg)
        .filter((msg): msg is string => typeof msg === "string");
      if (parts.length) return parts.join("; ");
    }
  }
  return `Lỗi ${status}`;
}

export function createApi(fetcher: typeof fetch = (...args) => fetch(...args)): Api {
  async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
    const session = getSession();
    const headers: Record<string, string> = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (session) headers.Authorization = `Bearer ${session.token}`;
    const response = await fetcher(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await response.text();
    const payload: unknown = text ? safeJson(text) : undefined;
    if (!response.ok) {
      if (response.status === 401 && session) setSession(null);
      throw new ApiError(response.status, errorText(payload, response.status), payload);
    }
    return payload as T;
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

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export const api = createApi();
