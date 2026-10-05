// ported from: src/zalo/account-manager.ts (the `attachAccount` / `stopAccount` / running registry part)
// Deviations: there is no account store and no scheduler here: the accounts are driven over HTTP by the
// Python API, a credential arrives in the `start` call and lives only in zca-js' own memory, and what the
// original did in-process (message handling, friend events) is sent to the API as signed events.
import type { BridgeConfig } from "./config.js";
import type { BridgeEvent, EventPublisher, AccountStateEventState } from "./event-publisher.js";
import { normalizeFriendEvent } from "./friends.js";
import { createLogger, errorInfo } from "./logger.js";
import { ON_DINH_MS } from "./reconnect-planner.js";
import { AccountSafety } from "./safety.js";
import { startListener, type ListenerReport } from "./zalo-listener.js";
import type { Credential, Gateway, ZaloApi, ZaloSession } from "./zalo-types.js";

const log = createLogger("account-registry");

export type AccountState =
  | "stopped"
  | "connecting"
  | "connected"
  | "disconnected"
  | "session_dead"
  | "logged_out"
  | "blocked";

type ListenerState = Exclude<AccountState, "blocked">;

/** States in which the session is unusable: sends are refused as `not_running`. */
const UNUSABLE: ReadonlySet<ListenerState> = new Set(["stopped", "session_dead", "logged_out"]);

export class ManagedAccount {
  listenerState: ListenerState = "stopped";
  api: ZaloApi | null = null;
  ownId: string | null = null;
  /** Identifies the current attachment; callbacks of an older one see a different token and stop. */
  token: symbol | null = null;
  stopListener: (() => void) | null = null;
  stableTimer: ReturnType<typeof setTimeout> | null = null;
  /** The last state sent to the API, to send changes only. */
  reportedState: AccountStateEventState | null = null;

  constructor(
    readonly id: string,
    readonly safety: AccountSafety,
  ) {}

  /** `blocked` wins over the listener state while the account is running. */
  get state(): AccountState {
    if (this.listenerState === "stopped") return "stopped";
    return this.safety.blocked ? "blocked" : this.listenerState;
  }

  /** The session can send (the websocket may be down: sends are HTTP calls). */
  get canSend(): boolean {
    return this.api !== null && !UNUSABLE.has(this.listenerState);
  }
}

export type AccountSummary = {
  account_id: string;
  state: AccountState;
  own_id: string | null;
  proactive_sent_today: number;
};

export type AccountManagerDeps = {
  config: BridgeConfig;
  gateway: Gateway;
  publisher: EventPublisher;
  now?: () => number;
  /** A connection counts (and is reported) as connected after this long. Default: the planner's ON_DINH_MS. */
  stableMs?: number;
};

export class AccountManager {
  private readonly accounts = new Map<string, ManagedAccount>();
  private readonly locks = new Map<string, Promise<unknown>>();
  private readonly now: () => number;
  private readonly stableMs: number;

  constructor(private readonly deps: AccountManagerDeps) {
    this.now = deps.now ?? (() => Date.now());
    this.stableMs = deps.stableMs ?? ON_DINH_MS;
  }

  get(accountId: string): ManagedAccount | undefined {
    return this.accounts.get(accountId);
  }

  /** Accounts that are not stopped (the `accounts` count of /health). */
  activeCount(): number {
    return [...this.accounts.values()].filter((account) => account.state !== "stopped").length;
  }

  list(): AccountSummary[] {
    return [...this.accounts.values()].map((account) => ({
      account_id: account.id,
      state: account.state,
      own_id: account.ownId,
      proactive_sent_today: account.safety.proactiveSentToday(),
    }));
  }

  /**
   * Log in with the credential and start the listener. Replaces a running account of the same id (stop
   * first). A start is the operator's decision, so it also clears the breaker (`blocked`). The
   * credential is passed to zca-js and not kept anywhere else.
   */
  start(accountId: string, credential: Credential): Promise<{ ownId: string }> {
    return this.runExclusive(accountId, async () => {
      this.stopNow(accountId);
      const account = this.getOrCreate(accountId);
      account.listenerState = "connecting";
      try {
        const session = await this.deps.gateway.login(credential);
        this.attachSession(account, session, false);
        return { ownId: session.ownId };
      } catch (err) {
        this.stopNow(accountId);
        throw err;
      }
    });
  }

  /** Attach the session of a successful QR login and tell the API the new credential. */
  attachFromQr(accountId: string, session: ZaloSession): Promise<void> {
    return this.runExclusive(accountId, async () => {
      this.stopNow(accountId);
      this.attachSession(this.getOrCreate(accountId), session, true);
    });
  }

  stop(accountId: string): Promise<void> {
    return this.runExclusive(accountId, async () => {
      this.stopNow(accountId);
    });
  }

  async stopAll(): Promise<void> {
    await Promise.all([...this.accounts.keys()].map((accountId) => this.stop(accountId)));
  }

  /** The breaker just opened for this account: tell the API (the listener keeps running). */
  reportBlocked(account: ManagedAccount): void {
    this.publishState(account, "blocked", "send_rejected_repeatedly");
  }

  private getOrCreate(accountId: string): ManagedAccount {
    const existing = this.accounts.get(accountId);
    if (existing) return existing;
    const { config } = this.deps;
    const safety = new AccountSafety(
      {
        maxSendsPerMinute: config.maxSendsPerMinutePerAccount,
        maxProactivePerDay: config.maxProactivePerDayPerAccount,
        blockAfterRejectedSends: config.blockAfterRejectedSends,
        timeZone: config.timezone,
      },
      this.now,
    );
    const account = new ManagedAccount(accountId, safety);
    this.accounts.set(accountId, account);
    return account;
  }

  private attachSession(
    account: ManagedAccount,
    session: ZaloSession,
    announceCredential: boolean,
  ): void {
    const token = Symbol(account.id);
    account.safety.clearBlocked();
    account.api = session.api;
    account.ownId = session.ownId;
    account.token = token;
    account.listenerState = "connecting";
    account.reportedState = null;
    const target = { accountId: account.id };
    const current = (): boolean => account.token === token;

    if (announceCredential) {
      this.deps.publisher.publish(target, {
        type: "credential_updated",
        credential: session.exportCredential(),
      });
    }

    try {
      account.stopListener = startListener(
        account.id,
        session.api,
        (message) => {
          if (!current()) return;
          this.deps.publisher.publish(target, {
            type: "message",
            self_id: session.ownId,
            message,
          });
        },
        (event) => {
          if (!current()) return;
          this.deps.publisher.publish(target, {
            type: "friend_event",
            event: normalizeFriendEvent(event),
          });
        },
        {
          onReport: (report) => {
            if (!current()) return;
            this.onListenerReport(account, report);
          },
          now: this.now,
        },
      );
    } catch (err) {
      log.error({ accountId: account.id, ...errorInfo(err) }, "Listener did not start");
      this.stopNow(account.id);
      throw err;
    }
  }

  private onListenerReport(account: ManagedAccount, report: ListenerReport): void {
    if (report.state === "connected") {
      this.onConnected(account);
      return;
    }
    this.clearStableTimer(account);
    if (report.state === "disconnected") {
      // A terminal verdict stays until a stable connection replaces it.
      if (account.listenerState === "session_dead" || account.listenerState === "logged_out")
        return;
      account.listenerState = "disconnected";
      // Only a state the API was told is connected needs a "disconnected": flaps never were connected.
      if (account.reportedState === "connected") {
        this.publishState(account, "disconnected", report.reason);
      }
      return;
    }
    account.listenerState = report.state;
    this.publishState(account, report.state, report.reason);
  }

  private onConnected(account: ManagedAccount): void {
    account.listenerState = "connected";
    this.clearStableTimer(account);
    const token = account.token;
    account.stableTimer = setTimeout(() => {
      account.stableTimer = null;
      if (account.token !== token || account.listenerState !== "connected") return;
      if (account.safety.blocked) return;
      this.publishState(account, "connected", "connected");
    }, this.stableMs);
    account.stableTimer.unref?.();
  }

  private clearStableTimer(account: ManagedAccount): void {
    if (!account.stableTimer) return;
    clearTimeout(account.stableTimer);
    account.stableTimer = null;
  }

  private publishState(
    account: ManagedAccount,
    state: AccountStateEventState,
    reason: string,
  ): void {
    if (account.reportedState === state) return;
    account.reportedState = state;
    const event: BridgeEvent = { type: "account_state", state, reason };
    this.deps.publisher.publish({ accountId: account.id }, event);
  }

  private stopNow(accountId: string): void {
    const account = this.accounts.get(accountId);
    if (!account) return;
    account.token = null;
    this.clearStableTimer(account);
    account.stopListener?.();
    account.stopListener = null;
    account.api = null;
    account.listenerState = "stopped";
    account.reportedState = null;
  }

  /** One operation at a time per account (start while a start is logging in must not interleave). */
  private runExclusive<T>(accountId: string, task: () => Promise<T>): Promise<T> {
    const previous = this.locks.get(accountId) ?? Promise.resolve();
    const run = previous.then(task);
    const tail = run.then(
      () => undefined,
      () => undefined,
    );
    this.locks.set(accountId, tail);
    void tail.then(() => {
      if (this.locks.get(accountId) === tail) this.locks.delete(accountId);
    });
    return run;
  }
}
