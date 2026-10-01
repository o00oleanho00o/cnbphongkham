/**
 * Seams between the bridge and zca-js.
 *
 * New module (no TS original). The original passed zca-js' `API` around directly; the bridge needs to
 * run every behaviour (routes, safety gates, listener, QR login) in tests WITHOUT zca-js and without a
 * network, so the code depends on these small types and only `zalo-client.ts` touches the real library.
 * Types come from zca-js (`import type`), so a fake that satisfies them stays honest to the real API.
 */
import type { API, FriendEvent, Message } from "zca-js";

/** The slice of zca-js' `Listener` the bridge uses (same methods the original `zalo-listener.ts` calls). */
export type ListenerPort = {
  on(event: "message", handler: (message: Message) => unknown): unknown;
  on(event: "friend_event", handler: (event: FriendEvent) => unknown): unknown;
  onConnected(cb: () => unknown): void;
  onError(cb: (error: unknown) => unknown): void;
  onClosed(cb: (code: number, reason: string) => unknown): void;
  start(): void;
  stop(): void;
};

/** The slice of zca-js' `API` the bridge uses. */
export type ZaloApi = Pick<
  API,
  | "sendMessage"
  | "sendVideo"
  | "sendTypingEvent"
  | "sendDeliveredEvent"
  | "sendSeenEvent"
  | "addReaction"
  | "getUserInfo"
  | "getAllFriends"
  | "acceptFriendRequest"
  | "rejectFriendRequest"
  | "getGroupInfo"
> & { listener: ListenerPort };

/** What the API gives `start` and what `credential_updated` carries. Secret: never log, never write to disk. */
export type Credential = {
  /** zca-js cookie jar as exported by `ctx.cookie.toJSON()?.cookies` (or the `{url, cookies}` form). */
  cookie: unknown;
  imei: string;
  userAgent: string;
};

/** A logged-in Zalo account. */
export type ZaloSession = {
  api: ZaloApi;
  ownId: string;
  /** Cookie/imei/userAgent of this session (original: `persistCredentialsFromApi`, minus the disk write). */
  exportCredential(): Credential;
};

/** Event of the QR login (original `QrLoginEvent`). */
export type QrLoginEvent = {
  type: "qr" | "scanned" | "expired" | "declined" | "info";
  /** Base64 PNG (without a `data:` prefix), only on type "qr". */
  qrBase64?: string;
};

/** The only door to Zalo. The real one is `createZcaGateway()`; tests inject a fake. */
export type Gateway = {
  login(credential: Credential): Promise<ZaloSession>;
  /**
   * QR login for the web flow. `signal` aborts the login (superseded or timed out session): without it
   * zca-js would keep generating QR codes for an abandoned session.
   */
  loginQR(onEvent: (event: QrLoginEvent) => void, signal: AbortSignal): Promise<ZaloSession>;
};
