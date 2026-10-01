/**
 * Hard safety backstops of the bridge: kill switch, per-account send ceilings and the account breaker.
 *
 * New module (no TS original). These exist because zca-js is an unofficial client: Zalo can lock the
 * account when it sees too many messages or too many rejected ones. They are INDEPENDENT of the caps in
 * the Python API (those are policy; these are the last line, enforced here even if the API misbehaves).
 * Everything is in memory (nothing is written to disk) and every clock is injected, so tests are exact.
 */

export type KillScope = "proactive" | "all";

export type KillSwitchState = {
  on: boolean;
  scope: KillScope;
  reason?: string;
};

/**
 * Global, in-memory, effective immediately for every account: the instant emergency stop.
 * Scope `all` blocks every send; scope `proactive` blocks only sends flagged `proactive: true`.
 */
export class KillSwitch {
  private state: KillSwitchState = { on: false, scope: "all" };

  get(): KillSwitchState {
    return { ...this.state };
  }

  set(next: { on: boolean; scope?: KillScope; reason?: string | undefined }): KillSwitchState {
    this.state = {
      on: next.on,
      scope: next.scope ?? this.state.scope,
      ...(next.reason === undefined ? {} : { reason: next.reason }),
    };
    return this.get();
  }

  blocks(proactive: boolean): boolean {
    if (!this.state.on) return false;
    return this.state.scope === "all" || proactive;
  }
}

/** Day key `YYYY-MM-DD` of `nowMs` in `timeZone` (the day boundary of the proactive ceiling). */
export function dayKey(nowMs: number, timeZone: string): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(nowMs);
}

export type SafetyLimits = {
  maxSendsPerMinute: number;
  maxProactivePerDay: number;
  blockAfterRejectedSends: number;
  timeZone: string;
};

const MINUTE_MS = 60_000;

export type SendRefusal =
  | { ok: false; kind: "blocked"; message: string }
  | { ok: false; kind: "rate_limited"; message: string };

/** Proof that a send was admitted; hand it back to `succeeded` / `failed`. */
export type SendReservation = {
  readonly proactive: boolean;
  readonly dayKey: string;
};

export type SendAdmission = { ok: true; reservation: SendReservation } | SendRefusal;

export type FailureOutcome = {
  /** True exactly when THIS failure opened the breaker. */
  blockedNow: boolean;
};

/**
 * Per-account ceilings and breaker. One instance outlives stop/start of the account so the daily count
 * cannot be reset by restarting the account (it is still reset by restarting the whole bridge).
 */
export class AccountSafety {
  private sendTimestamps: number[] = [];
  private proactiveDay = "";
  private proactiveCount = 0;
  private consecutiveRejected = 0;
  private blockedFlag = false;

  constructor(
    private readonly limits: SafetyLimits,
    private readonly now: () => number = () => Date.now(),
  ) {}

  get blocked(): boolean {
    return this.blockedFlag;
  }

  /** Blocked clears only when the operator logs in again: `/start` or a new QR login. */
  clearBlocked(): void {
    this.blockedFlag = false;
    this.consecutiveRejected = 0;
  }

  proactiveSentToday(): number {
    return this.currentDay() === this.proactiveDay ? this.proactiveCount : 0;
  }

  /**
   * Gate order (the caller has already checked running and kill switch): breaker, per-minute ceiling
   * (all sends), per-day ceiling (proactive only). A refused request consumes nothing.
   */
  admit(proactive: boolean): SendAdmission {
    if (this.blockedFlag) {
      return { ok: false, kind: "blocked", message: "Account is blocked after repeated rejected sends" };
    }
    const nowMs = this.now();
    const recent = this.sendTimestamps.filter((timestamp) => nowMs - timestamp < MINUTE_MS);
    if (recent.length >= this.limits.maxSendsPerMinute) {
      this.sendTimestamps = recent;
      return { ok: false, kind: "rate_limited", message: "Per-minute send ceiling reached" };
    }
    const today = this.currentDay();
    if (proactive && this.proactiveSentToday() >= this.limits.maxProactivePerDay) {
      this.sendTimestamps = recent;
      return { ok: false, kind: "rate_limited", message: "Per-day proactive ceiling reached" };
    }
    this.sendTimestamps = [...recent, nowMs];
    if (proactive) this.takeProactiveSlot(today);
    return { ok: true, reservation: { proactive, dayKey: today } };
  }

  /** A successful send resets the consecutive-rejection counter. */
  succeeded(): void {
    this.consecutiveRejected = 0;
  }

  /**
   * A failed send refunds the daily proactive slot. A rejection by the Zalo server (numeric code) counts
   * toward the breaker; a transport failure neither counts nor resets (the message may or may not have
   * arrived, and it says nothing about how Zalo sees the account).
   */
  failed(reservation: SendReservation, rejectedByServer: boolean): FailureOutcome {
    this.refundProactiveSlot(reservation);
    if (!rejectedByServer) return { blockedNow: false };
    this.consecutiveRejected += 1;
    if (this.blockedFlag || this.consecutiveRejected < this.limits.blockAfterRejectedSends) {
      return { blockedNow: false };
    }
    this.blockedFlag = true;
    return { blockedNow: true };
  }

  private currentDay(): string {
    return dayKey(this.now(), this.limits.timeZone);
  }

  private takeProactiveSlot(today: string): void {
    this.proactiveCount = this.proactiveDay === today ? this.proactiveCount + 1 : 1;
    this.proactiveDay = today;
  }

  private refundProactiveSlot(reservation: SendReservation): void {
    if (!reservation.proactive) return;
    // A slot taken yesterday must not reduce today's count.
    if (reservation.dayKey !== this.proactiveDay) return;
    this.proactiveCount = Math.max(0, this.proactiveCount - 1);
  }
}
