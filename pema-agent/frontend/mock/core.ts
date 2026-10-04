// Mock backend for the Pema dashboard (package E). Serves the paths of
// backend/apps/api/openapi.json from memory with FICTIONAL data, so the frontend can be built and
// looked at while the real backend packages are still being written. It is not a second
// implementation of the business rules: real rules, permissions and audit live in the BE; here the
// role matrix only exists so the menu and the 403 states can be exercised.
import type { IncomingMessage, ServerResponse } from "node:http";

import type { components } from "../src/lib/api/schema";

export type Schemas = components["schemas"];
export type Permission = Schemas["Permission"];
export type ErrorCode = Schemas["ErrorCode"];
export type Role = Schemas["Role"];

export type Session = {
  id: string;
  userId: string;
  role: Role;
  permissions: readonly Permission[];
};

export type Ctx = {
  req: IncomingMessage;
  res: ServerResponse;
  params: Record<string, string>;
  query: URLSearchParams;
  session: Session | null;
  /** Parsed JSON body ({} when none) */
  body: unknown;
  /** Raw body for multipart uploads */
  raw: Buffer;
};

export type Reply = { status?: number; body?: unknown; headers?: Record<string, string> };
export type Handler = (ctx: Ctx) => Reply | Promise<Reply>;

type Route = {
  method: string;
  pattern: RegExp;
  keys: string[];
  template: string;
  permission: Permission | null;
  handler: Handler;
};

export class HttpError extends Error {
  constructor(
    public status: number,
    public code: ErrorCode,
    message: string,
  ) {
    super(message);
  }
}

export function fail(status: number, code: ErrorCode, message: string): never {
  throw new HttpError(status, code, message);
}

export class Router {
  readonly routes: Route[] = [];

  add(method: string, template: string, permission: Permission | null, handler: Handler): void {
    const keys: string[] = [];
    const source = template.replace(/\{([^}]+)\}/g, (_m, k: string) => {
      keys.push(k);
      return "([^/]+)";
    });
    this.routes.push({
      method,
      pattern: new RegExp(`^${source}$`),
      keys,
      template,
      permission,
      handler,
    });
  }

  get(t: string, p: Permission | null, h: Handler): void {
    this.add("GET", t, p, h);
  }
  post(t: string, p: Permission | null, h: Handler): void {
    this.add("POST", t, p, h);
  }
  put(t: string, p: Permission | null, h: Handler): void {
    this.add("PUT", t, p, h);
  }
  patch(t: string, p: Permission | null, h: Handler): void {
    this.add("PATCH", t, p, h);
  }
  delete(t: string, p: Permission | null, h: Handler): void {
    this.add("DELETE", t, p, h);
  }

  match(method: string, pathname: string): { route: Route; params: Record<string, string> } | null {
    for (const route of this.routes) {
      if (route.method !== method) continue;
      const m = route.pattern.exec(pathname);
      if (!m) continue;
      const params: Record<string, string> = {};
      route.keys.forEach((k, i) => {
        params[k] = decodeURIComponent(m[i + 1] ?? "");
      });
      return { route, params };
    }
    return null;
  }
}

export function errorBody(code: ErrorCode, message: string): Schemas["ErrorResponse"] {
  return { error: { code, message, request_id: `mock-${Date.now().toString(36)}` } };
}

export async function readBody(req: IncomingMessage): Promise<Buffer> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(chunk as Buffer);
  return Buffer.concat(chunks);
}

export function parseJson(raw: Buffer): unknown {
  if (raw.length === 0) return {};
  try {
    return JSON.parse(raw.toString("utf8"));
  } catch {
    return {};
  }
}

/** `Page_*` envelope used by the list endpoints. */
export function paginate<T>(items: T[], query: URLSearchParams) {
  const limit = clampInt(query.get("limit"), 50, 1, 200);
  const offset = clampInt(query.get("offset"), 0, 0, Number.MAX_SAFE_INTEGER);
  return { items: items.slice(offset, offset + limit), total: items.length, limit, offset };
}

export function clampInt(raw: string | null, fallback: number, min: number, max: number): number {
  const n = raw === null ? Number.NaN : Number.parseInt(raw, 10);
  if (Number.isNaN(n)) return fallback;
  return Math.min(max, Math.max(min, n));
}

/** Body field access without `any`: the mock trusts the frontend's typed client. */
export function bodyOf<T>(ctx: Ctx): T {
  return ctx.body as T;
}

let counter = 0;
export function uid(prefix = "id"): string {
  counter += 1;
  return `${prefix}-${Date.now().toString(36)}-${counter}`;
}

/** Deterministic fake uuid from a small integer, so seeded ids are stable between restarts. */
export function uuid(n: number, kind = 1): string {
  const hex = n.toString(16).padStart(12, "0");
  return `00000000-0000-4000-8${String(kind).padStart(3, "0")}-${hex}`;
}

export const MIN = 60_000;
export const HOUR = 3_600_000;
export const DAY = 86_400_000;

/** ISO string `ms` from now (negative = past), with the +07:00 offset the contract asks for. */
export function isoFromNow(ms: number): string {
  return toVn(new Date(Date.now() + ms));
}

export function toVn(d: Date): string {
  const shifted = new Date(d.getTime() + 7 * HOUR);
  return `${shifted.toISOString().slice(0, 19)}+07:00`;
}
