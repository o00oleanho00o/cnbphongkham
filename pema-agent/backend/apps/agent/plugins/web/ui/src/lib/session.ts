/** The signed-in admin: the JWT the web plugin issued, kept in this browser until it expires or is refused. */

export interface Session {
  token: string;
  email: string;
  expiresAt: string;
}

const KEY = "pema-agent.session";
const listeners = new Set<() => void>();
let current: Session | null | undefined;

function read(): Session | null {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(KEY) ?? "null");
    if (!isSession(parsed) || Date.parse(parsed.expiresAt) <= Date.now()) return null;
    return parsed;
  } catch {
    return null;
  }
}

function isSession(value: unknown): value is Session {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.token === "string" && typeof v.email === "string" && typeof v.expiresAt === "string";
}

export function getSession(): Session | null {
  if (current === undefined) current = read();
  if (current && Date.parse(current.expiresAt) <= Date.now()) current = null;
  return current;
}

export function setSession(session: Session | null): void {
  current = session;
  if (session) localStorage.setItem(KEY, JSON.stringify(session));
  else localStorage.removeItem(KEY);
  listeners.forEach((listener) => listener());
}

export function subscribeSession(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
