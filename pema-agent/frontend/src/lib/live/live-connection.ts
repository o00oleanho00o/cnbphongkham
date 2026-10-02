// The browser side of `GET /api/v1/events` (server-sent events): a connection that tells the screens WHAT
// changed (never the content, they reload their own list through the normal API, so permissions and
// filters stay the backend's), reconnects by itself, and when the stream stays down for more than
// FALLBACK_AFTER_MS falls back to a plain refresh every POLL_EVERY_MS until it is back.
//
// Plain class, no React: the hook (use-live-events.ts) is a thin wrapper and the tests drive this directly
// with a fake EventSource and fake timers.
import { parseLiveEvent, type LiveEvent, type LiveEventType } from "@/lib/live/live-types";

export const EVENTS_URL = "/api/v1/events";
/** The stream has been down this long: stop waiting for it and poll. */
export const FALLBACK_AFTER_MS = 10_000;
/** Refresh period while the stream is down. */
export const POLL_EVERY_MS = 30_000;
/** Events that arrive within this window are handed over together (one reload, not ten). */
export const COALESCE_MS = 250;
/** Our own reconnect delays when the browser gave up (readyState CLOSED); the last one repeats. */
export const RECONNECT_DELAYS_MS: readonly number[] = [1_000, 2_000, 4_000, 8_000, 10_000];

export type LiveMode = "connecting" | "live" | "polling";

/** The part of `EventSource` we use, so a test can stand in for it. */
export type EventSourceLike = {
  readonly readyState: number;
  onopen: ((event: Event) => void) | null;
  onmessage: ((event: MessageEvent<string>) => void) | null;
  onerror: ((event: Event) => void) | null;
  close: () => void;
};

const READY_STATE_CLOSED = 2;

export type LiveConnectionOptions = {
  /** Only these event types reach `onEvent`; omitted means all. */
  types?: readonly LiveEventType[];
  onEvent: (event: LiveEvent) => void;
  /** The stream was down and came back, or the fallback timer fired: reload what you show. */
  onRefresh: () => void;
  onMode?: (mode: LiveMode) => void;
  url?: string;
  createSource?: (url: string) => EventSourceLike;
};

function defaultCreateSource(url: string): EventSourceLike {
  return new EventSource(url, { withCredentials: true });
}

export class LiveConnection {
  private source: EventSourceLike | null = null;
  private mode: LiveMode = "connecting";
  private closed = false;
  private wasDown = false;
  private attempt = 0;
  private downTimer: ReturnType<typeof setTimeout> | null = null;
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private flushTimer: ReturnType<typeof setTimeout> | null = null;
  private pending = new Map<string, LiveEvent>();

  constructor(private readonly options: LiveConnectionOptions) {}

  start(): void {
    this.connect();
  }

  close(): void {
    this.closed = true;
    this.closeSource();
    this.clearDownTimer();
    this.stopPolling();
    this.clearRetryTimer();
    this.clearFlushTimer();
    this.pending.clear();
  }

  private connect(): void {
    if (this.closed) return;
    const create = this.options.createSource ?? defaultCreateSource;
    const source = create(this.options.url ?? EVENTS_URL);
    this.source = source;
    source.onopen = () => this.handleOpen(source);
    source.onmessage = (event) => this.handleMessage(source, event.data);
    source.onerror = () => this.handleError(source);
  }

  private closeSource(): void {
    if (!this.source) return;
    this.source.onopen = null;
    this.source.onmessage = null;
    this.source.onerror = null;
    this.source.close();
    this.source = null;
  }

  private setMode(next: LiveMode): void {
    if (this.mode === next) return;
    this.mode = next;
    this.options.onMode?.(next);
  }

  private handleOpen(source: EventSourceLike): void {
    if (source !== this.source) return;
    this.attempt = 0;
    this.clearDownTimer();
    this.clearRetryTimer();
    this.stopPolling();
    this.setMode("live");
    if (this.wasDown) {
      // Events sent while we were away are gone; one reload brings the screen up to date.
      this.wasDown = false;
      this.options.onRefresh();
    }
  }

  private handleMessage(source: EventSourceLike, data: string): void {
    if (source !== this.source) return;
    const event = parseLiveEvent(data);
    if (!event) return;
    const wanted = this.options.types;
    if (wanted && !wanted.includes(event.type)) return;
    this.pending.set(`${event.type}:${event.id ?? ""}`, event);
    if (this.flushTimer) return;
    this.flushTimer = setTimeout(() => this.flush(), COALESCE_MS);
  }

  private flush(): void {
    this.flushTimer = null;
    const batch = [...this.pending.values()];
    this.pending.clear();
    if (this.closed) return;
    batch.forEach((event) => this.options.onEvent(event));
  }

  private handleError(source: EventSourceLike): void {
    if (source !== this.source) return;
    this.wasDown = true;
    if (this.mode === "live") this.setMode("connecting");
    if (!this.downTimer && this.mode !== "polling") {
      this.downTimer = setTimeout(() => this.startPolling(), FALLBACK_AFTER_MS);
    }
    // While readyState is CONNECTING the browser retries by itself; CLOSED means it gave up.
    if (source.readyState === READY_STATE_CLOSED) this.scheduleReconnect();
  }

  private scheduleReconnect(): void {
    if (this.retryTimer || this.closed) return;
    this.closeSource();
    const delay =
      RECONNECT_DELAYS_MS[Math.min(this.attempt, RECONNECT_DELAYS_MS.length - 1)] ??
      FALLBACK_AFTER_MS;
    this.attempt += 1;
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null;
      this.connect();
    }, delay);
  }

  private startPolling(): void {
    this.downTimer = null;
    if (this.closed) return;
    this.setMode("polling");
    this.pollTimer = setInterval(() => this.options.onRefresh(), POLL_EVERY_MS);
  }

  private stopPolling(): void {
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.pollTimer = null;
  }

  private clearDownTimer(): void {
    if (this.downTimer) clearTimeout(this.downTimer);
    this.downTimer = null;
  }

  private clearRetryTimer(): void {
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.retryTimer = null;
  }

  private clearFlushTimer(): void {
    if (this.flushTimer) clearTimeout(this.flushTimer);
    this.flushTimer = null;
  }
}
