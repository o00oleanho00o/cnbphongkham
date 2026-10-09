/**
 * Hand-written fakes for the tests (never imported by the runtime code). Everything is synthetic: ids,
 * names and cookies are made up, nothing here opens a network connection.
 */
import type { Hono } from "hono";
import { FriendEventType, type FriendEvent, type Message } from "zca-js";
import { signedHeaders } from "./auth.js";
import type { BridgeConfig } from "./config.js";
import type { BridgeEvent, EventPublisher, EventTarget } from "./event-publisher.js";
import type { AppEnv } from "./http.js";
import type {
  Credential,
  Gateway,
  ListenerPort,
  QrLoginEvent,
  ZaloApi,
  ZaloSession,
} from "./zalo-types.js";

export const SECRET = "test-secret-0123456789";

export function makeConfig(overrides: Partial<BridgeConfig> = {}): BridgeConfig {
  return {
    enabled: true,
    secret: SECRET,
    host: "127.0.0.1",
    port: 8200,
    apiBaseUrl: "http://api.test/api/v1",
    timezone: "Asia/Ho_Chi_Minh",
    maxProactivePerDayPerAccount: 100,
    maxSendsPerMinutePerAccount: 20,
    blockAfterRejectedSends: 5,
    logLevel: "silent",
    ...overrides,
  };
}

export const TEST_CREDENTIAL: Credential = {
  cookie: [{ name: "zpsid", value: "synthetic-cookie-value", domain: "chat.zalo.me" }],
  imei: "synthetic-imei",
  userAgent: "synthetic-agent",
};

export type FakeListener = ListenerPort & {
  starts: number;
  stops: number;
  /** Make the next `start()` throw (a broken cookie that never opens a socket). */
  failNextStart: boolean;
  emitMessage(message: Message): void;
  emitFriendEvent(event: FriendEvent): void;
  emitConnected(): void;
  emitClosed(code: number, reason?: string): void;
  emitError(error: unknown): void;
};

export function createFakeListener(): FakeListener {
  let messageHandler: ((message: Message) => unknown) | null = null;
  let friendHandler: ((event: FriendEvent) => unknown) | null = null;
  let connectedHandler: (() => unknown) | null = null;
  let closedHandler: ((code: number, reason: string) => unknown) | null = null;
  let errorHandler: ((error: unknown) => unknown) | null = null;

  const listener: FakeListener = {
    starts: 0,
    stops: 0,
    failNextStart: false,
    on(event: "message" | "friend_event", handler: never): unknown {
      if (event === "message") messageHandler = handler;
      else friendHandler = handler;
      return listener;
    },
    onConnected: (cb) => {
      connectedHandler = cb;
    },
    onClosed: (cb) => {
      closedHandler = cb;
    },
    onError: (cb) => {
      errorHandler = cb;
    },
    start: () => {
      listener.starts += 1;
      if (!listener.failNextStart) return;
      listener.failNextStart = false;
      throw new Error("start failed");
    },
    stop: () => {
      listener.stops += 1;
    },
    emitMessage: (message) => void messageHandler?.(message),
    emitFriendEvent: (event) => void friendHandler?.(event),
    emitConnected: () => void connectedHandler?.(),
    emitClosed: (code, reason = "") => void closedHandler?.(code, reason),
    emitError: (error) => void errorHandler?.(error),
  };
  return listener;
}

export type ApiCall = { method: string; args: unknown[] };

export type FakeApi = {
  api: ZaloApi;
  listener: FakeListener;
  calls: ApiCall[];
  callsTo(method: string): ApiCall[];
};

/** A fake zca-js API whose methods record their arguments; any method can be overridden (e.g. to throw). */
export function createFakeApi(overrides: Partial<Omit<ZaloApi, "listener">> = {}): FakeApi {
  const calls: ApiCall[] = [];
  const listener = createFakeListener();
  const record = (method: string, args: unknown[]): void => {
    calls.push({ method, args });
  };
  const api: ZaloApi = {
    listener,
    sendMessage: async (...args) => {
      record("sendMessage", args);
      return { message: { msgId: 111 }, attachment: [] };
    },
    sendVideo: async (...args) => {
      record("sendVideo", args);
      return { msgId: 222 };
    },
    sendTypingEvent: async (...args) => {
      record("sendTypingEvent", args);
      return { status: 0 };
    },
    sendDeliveredEvent: async (...args) => {
      record("sendDeliveredEvent", args);
      return { status: 0 };
    },
    sendSeenEvent: async (...args) => {
      record("sendSeenEvent", args);
      return { status: 0 };
    },
    addReaction: async (...args) => {
      record("addReaction", args);
      return { msgIds: [] };
    },
    getUserInfo: async (...args) => {
      record("getUserInfo", args);
      return { unchanged_profiles: {}, phonebook_version: 0, changed_profiles: {} };
    },
    getAllFriends: async (...args) => {
      record("getAllFriends", args);
      return [];
    },
    acceptFriendRequest: async (...args) => {
      record("acceptFriendRequest", args);
      return "";
    },
    rejectFriendRequest: async (...args) => {
      record("rejectFriendRequest", args);
      return "";
    },
    getGroupInfo: async (...args) => {
      record("getGroupInfo", args);
      return { removedsGroup: [], unchangedsGroup: [], gridInfoMap: {} };
    },
    ...overrides,
  };
  return {
    api,
    listener,
    calls,
    callsTo: (method) => calls.filter((call) => call.method === method),
  };
}

export function createFakeSession(fake: FakeApi = createFakeApi(), ownId = "1000001"): ZaloSession {
  return { api: fake.api, ownId, exportCredential: () => TEST_CREDENTIAL };
}

/** Controls one pending QR login from the test. */
export type QrControl = {
  signal: AbortSignal;
  emit(event: QrLoginEvent): void;
  succeed(session: ZaloSession): void;
  fail(error: Error): void;
};

export class FakeGateway implements Gateway {
  readonly loginCalls: Credential[] = [];
  readonly qrControls: QrControl[] = [];
  /** Sessions handed out by `login`, in order; defaults to a fresh fake. */
  nextSessions: ZaloSession[] = [];
  loginError: unknown = null;
  /** Hold `login` until the test calls `releaseLogin` (to test concurrent starts). */
  private loginGate: Promise<void> | null = null;
  private openLoginGate: (() => void) | null = null;

  holdLogin(): void {
    this.loginGate = new Promise<void>((resolve) => {
      this.openLoginGate = resolve;
    });
  }

  releaseLogin(): void {
    this.openLoginGate?.();
  }

  async login(credential: Credential): Promise<ZaloSession> {
    this.loginCalls.push(credential);
    await this.loginGate;
    if (this.loginError) throw this.loginError;
    return this.nextSessions.shift() ?? createFakeSession();
  }

  loginQR(onEvent: (event: QrLoginEvent) => void, signal: AbortSignal): Promise<ZaloSession> {
    return new Promise<ZaloSession>((resolve, reject) => {
      this.qrControls.push({
        signal,
        emit: onEvent,
        succeed: resolve,
        fail: reject,
      });
    });
  }
}

export class RecordingPublisher implements EventPublisher {
  readonly events: Array<{ target: EventTarget; event: BridgeEvent }> = [];

  publish(target: EventTarget, event: BridgeEvent): void {
    this.events.push({ target, event });
  }

  ofType<T extends BridgeEvent["type"]>(type: T): Array<Extract<BridgeEvent, { type: T }>> {
    return this.events
      .map((entry) => entry.event)
      .filter((event): event is Extract<BridgeEvent, { type: T }> => event.type === type);
  }

  states(): string[] {
    return this.ofType("account_state").map((event) => event.state);
  }
}

/** A listener `Message` as zca-js builds it (a plain object with these four fields). */
export function fakeUserMessage(threadId = "2000001", text = "xin chào"): Message {
  return {
    type: 0,
    threadId,
    isSelf: false,
    data: { msgId: "m1", cliMsgId: "c1", uidFrom: threadId, idTo: "1000001", content: text },
  } as unknown as Message; // synthetic shape; only these fields are read
}

export function fakeFriendEvent(type: FriendEventType, threadId = "2000001"): FriendEvent {
  return { type, data: threadId, threadId, isSelf: false } as unknown as FriendEvent; // synthetic
}

export type Sender = {
  get(path: string): Promise<Response>;
  post(path: string, body: unknown): Promise<Response>;
};

/** Signs every request like the API does. `nowSeconds` can be pinned to test the clock window. */
export function signedSender(
  app: Hono<AppEnv>,
  secret: string = SECRET,
  nowSeconds: () => number = () => Math.floor(Date.now() / 1000),
): Sender {
  return {
    get: async (path) =>
      app.request(path, { method: "GET", headers: signedHeaders(secret, "", nowSeconds()) }),
    post: async (path, body) => {
      const raw = JSON.stringify(body);
      return app.request(path, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          ...signedHeaders(secret, raw, nowSeconds()),
        },
        body: raw,
      });
    },
  };
}

export type Envelope = {
  ok: boolean;
  error?: { kind: string; message: string; code?: number };
  [key: string]: unknown;
};

export async function readEnvelope(response: Response): Promise<Envelope> {
  return (await response.json()) as Envelope;
}
