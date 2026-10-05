/**
 * Events bridge -> API: signed JSON, fire-and-forget with 3 retries and exponential backoff, never
 * blocking the listener.
 *
 * New module (no TS original: the original called its handlers in-process). The payload can hold
 * personal content (message text, names), so NOTHING of it is ever logged: only the event type, the
 * attempt number and the HTTP status. Events of one account are delivered in order (a slow API delays
 * that account's later events, not the listener, which only enqueues); the queue is bounded and drops
 * the oldest event when the API stays down.
 */
import { signedHeaders } from "./auth.js";
import { toJson } from "./json.js";
import { createLogger, errorInfo } from "./logger.js";
import type { Credential } from "./zalo-types.js";

const log = createLogger("event-publisher");

export type AccountStateEventState =
  "connected" | "disconnected" | "session_dead" | "logged_out" | "blocked";

export type FriendEventKind =
  "add" | "remove" | "request" | "undo_request" | "reject_request" | "other";

export type BridgeEvent =
  | { type: "message"; self_id: string; message: unknown }
  | {
      type: "friend_event";
      event: { kind: FriendEventKind; thread_id: string; is_self: boolean; data: unknown };
    }
  | { type: "credential_updated"; credential: Credential }
  | { type: "account_state"; state: AccountStateEventState; reason: string };

export type EventTarget = { accountId: string };

/** `publish` never throws and never waits: it only enqueues. */
export type EventPublisher = {
  publish(target: EventTarget, event: BridgeEvent): void;
};

export class NullEventPublisher implements EventPublisher {
  publish(): void {
    /* disabled bridge or no API: nothing to deliver */
  }
}

export type HttpEventPublisherOptions = {
  secret: string;
  apiBaseUrl: string;
  fetchImpl?: typeof fetch;
  /** Retries after the first attempt (default 3). */
  retries?: number;
  /** Delay before retry n is `baseDelayMs * 2 ** n` (default 500 ms: 0.5 s, 1 s, 2 s). */
  baseDelayMs?: number;
  timeoutMs?: number;
  maxQueuePerAccount?: number;
  sleep?: (ms: number) => Promise<void>;
  nowSeconds?: () => number;
};

type QueuedEvent = { target: EventTarget; event: BridgeEvent };

const DEFAULT_RETRIES = 3;
const DEFAULT_BASE_DELAY_MS = 500;
const DEFAULT_TIMEOUT_MS = 10_000;
const DEFAULT_MAX_QUEUE = 500;

const defaultSleep = (ms: number): Promise<void> =>
  new Promise((resolve) => {
    setTimeout(resolve, ms);
  });

/** 4xx other than "slow down" will not change by retrying (bad signature, unknown account). */
function isRetryableStatus(status: number): boolean {
  return status >= 500 || status === 408 || status === 429;
}

export class HttpEventPublisher implements EventPublisher {
  private readonly queues = new Map<string, QueuedEvent[]>();
  private readonly draining = new Set<string>();
  private readonly idleWaiters: Array<() => void> = [];
  private readonly fetchImpl: typeof fetch;
  private readonly retries: number;
  private readonly baseDelayMs: number;
  private readonly timeoutMs: number;
  private readonly maxQueue: number;
  private readonly sleep: (ms: number) => Promise<void>;
  private readonly nowSeconds: () => number;

  constructor(private readonly options: HttpEventPublisherOptions) {
    this.fetchImpl = options.fetchImpl ?? fetch;
    this.retries = options.retries ?? DEFAULT_RETRIES;
    this.baseDelayMs = options.baseDelayMs ?? DEFAULT_BASE_DELAY_MS;
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.maxQueue = options.maxQueuePerAccount ?? DEFAULT_MAX_QUEUE;
    this.sleep = options.sleep ?? defaultSleep;
    this.nowSeconds = options.nowSeconds ?? (() => Math.floor(Date.now() / 1000));
  }

  publish(target: EventTarget, event: BridgeEvent): void {
    const key = target.accountId;
    const queue = this.queues.get(key) ?? [];
    const kept = queue.length >= this.maxQueue ? queue.slice(1) : queue;
    if (kept.length !== queue.length) {
      log.warn({ accountId: key, maxQueue: this.maxQueue }, "Queue full: dropped the oldest event");
    }
    this.queues.set(key, [...kept, { target, event }]);
    if (this.draining.has(key)) return;
    this.draining.add(key);
    void this.drain(key);
  }

  /** Resolves when every queued event was delivered or given up. For shutdown and tests. */
  async flush(): Promise<void> {
    if (this.draining.size === 0) return;
    await new Promise<void>((resolve) => {
      this.idleWaiters.push(resolve);
    });
  }

  private takeNext(key: string): QueuedEvent | undefined {
    const queue = this.queues.get(key) ?? [];
    const [head, ...rest] = queue;
    this.queues.set(key, rest);
    return head;
  }

  private async drain(key: string): Promise<void> {
    try {
      // No await between the last `takeNext` returning undefined and the cleanup below, so an event
      // published in between cannot be left in a queue nobody drains.
      for (let item = this.takeNext(key); item !== undefined; item = this.takeNext(key)) {
        await this.deliver(item);
      }
    } finally {
      this.draining.delete(key);
      this.queues.delete(key);
      if (this.draining.size === 0) this.idleWaiters.splice(0).forEach((resolve) => resolve());
    }
  }

  private endpoint(target: EventTarget): string {
    const account = encodeURIComponent(target.accountId);
    return `${this.options.apiBaseUrl}/webhooks/zalo-bridge/${account}`;
  }

  private serialize(item: QueuedEvent): string | null {
    try {
      return toJson(item.event);
    } catch (err) {
      log.error({ type: item.event.type, ...errorInfo(err) }, "Event not serialisable: dropped");
      return null;
    }
  }

  /** One attempt. Returns "done" (delivered or not worth retrying) or "retry". */
  private async attempt(item: QueuedEvent, body: string): Promise<"done" | "retry"> {
    try {
      const response = await this.fetchImpl(this.endpoint(item.target), {
        method: "POST",
        headers: {
          "content-type": "application/json",
          ...signedHeaders(this.options.secret, body, this.nowSeconds()),
        },
        body,
        signal: AbortSignal.timeout(this.timeoutMs),
      });
      if (response.ok) return "done";
      if (!isRetryableStatus(response.status)) {
        log.warn(
          { type: item.event.type, status: response.status },
          "API refused the event: dropped",
        );
        return "done";
      }
      log.warn({ type: item.event.type, status: response.status }, "API failed to take the event");
      return "retry";
    } catch (err) {
      log.warn({ type: item.event.type, ...errorInfo(err) }, "Event delivery failed");
      return "retry";
    }
  }

  private async deliver(item: QueuedEvent): Promise<void> {
    const body = this.serialize(item);
    if (body === null) return;
    // `attempt` signs afresh every time (the timestamp must be inside the 300 s window).
    for (let retry = 0; retry <= this.retries; retry += 1) {
      if (retry > 0) await this.sleep(this.baseDelayMs * 2 ** (retry - 1));
      if ((await this.attempt(item, body)) === "done") return;
    }
    log.error({ type: item.event.type, attempts: this.retries + 1 }, "Event dropped after retries");
  }
}
