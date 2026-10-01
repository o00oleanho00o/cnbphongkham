// ported from: src/zalo/qr-login-manager.ts
// Deviations:
// - the SESSION STATE lives here in the bridge (the Python port is only a thin client of it);
// - a class with injected deps instead of module-level state, so tests are independent;
// - `getAccount(...).enabled` is gone: the success handler is `attach(accountId, clinicSlug, session)`,
//   which starts the listener and tells the API the new credential (`credential_updated`);
// - superseded / timed-out sessions are ABORTED (AbortController) so zca-js stops asking Zalo for QR
//   codes for an abandoned session; and a "declined" status is not overwritten by the abort error;
// - the status carries the raw base64 PNG (`qr_png_base64`), not a data URI.
import { createLogger, errorInfo } from "./logger.js";
import type { QrLoginEvent, ZaloSession } from "./zalo-types.js";

const log = createLogger("qr-login-manager");

/**
 * Quản lý phiên login QR từ dashboard: mỗi account tối đa 1 phiên, UI polling
 * trạng thái. QR là chìa khóa đăng nhập tài khoản - KHÔNG log base64, chỉ đi
 * qua API đã auth.
 */

export type QrLoginStatus =
  | "starting"
  | "waiting_scan"
  | "scanned"
  | "success"
  | "declined"
  | "error";

type QrSession = {
  seq: number;
  status: QrLoginStatus;
  clinicSlug: string;
  qrBase64?: string | undefined;
  error?: string | undefined;
  startedAt: number;
  controller: AbortController;
};

export const SESSION_TTL_MS = 3 * 60_000;

const PENDING: ReadonlySet<QrLoginStatus> = new Set(["starting", "waiting_scan", "scanned"]);

export type QrLoginDeps = {
  login: (
    accountId: string,
    onEvent: (event: QrLoginEvent) => void,
    signal: AbortSignal,
  ) => Promise<ZaloSession>;
  attach: (accountId: string, clinicSlug: string, session: ZaloSession) => Promise<void> | void;
  /** Re-login of a running account: kick the old listener first (Zalo allows one). */
  stopAccount: (accountId: string) => Promise<void> | void;
  now?: () => number;
};

export type QrStatusView = {
  state: QrLoginStatus | "idle" | "timeout";
  qr_png_base64?: string;
  error?: string;
};

export class QrLoginManager {
  private readonly sessions = new Map<string, QrSession>();
  private seqCounter = 0;
  private readonly now: () => number;

  constructor(private readonly deps: QrLoginDeps) {
    this.now = deps.now ?? (() => Date.now());
  }

  private isActive(session: QrSession): boolean {
    return PENDING.has(session.status) && this.now() - session.startedAt < SESSION_TTL_MS;
  }

  startQrLogin(accountId: string, clinicSlug: string): { seq: number; status: QrLoginStatus } {
    const existing = this.sessions.get(accountId);
    if (existing && this.isActive(existing)) return existing;
    // A new session supersedes the old one: stop its login and ignore anything it still reports.
    existing?.controller.abort();

    Promise.resolve(this.deps.stopAccount(accountId)).catch((err: unknown) =>
      log.warn({ accountId, ...errorInfo(err) }, "stopAccount before QR login failed"),
    );

    const seq = ++this.seqCounter;
    const session: QrSession = {
      seq,
      status: "starting",
      clinicSlug,
      startedAt: this.now(),
      controller: new AbortController(),
    };
    this.sessions.set(accountId, session);

    // Phiên mới đè phiên cũ: mọi update từ promise cũ bị bỏ qua nhờ check seq
    const stillCurrent = (): boolean => this.sessions.get(accountId)?.seq === seq;

    this.deps
      .login(accountId, (event) => this.onEvent(session, stillCurrent, event), session.controller.signal)
      .then(async (apiSession) => {
        if (!stillCurrent()) return;
        session.status = "success";
        session.qrBase64 = undefined;
        await this.deps.attach(accountId, session.clinicSlug, apiSession);
        log.info({ accountId }, "Login QR từ dashboard thành công");
      })
      .catch((err: unknown) => {
        if (!stillCurrent()) return;
        // Declined settles the login with an abort error; the user-visible reason stays "declined".
        if (session.status === "declined") return;
        session.status = "error";
        session.error = err instanceof Error ? err.message : String(err);
        log.warn({ accountId, ...errorInfo(err) }, "Login QR thất bại");
      });

    return session;
  }

  private onEvent(session: QrSession, stillCurrent: () => boolean, event: QrLoginEvent): void {
    if (!stillCurrent()) return;
    if (event.type === "qr") {
      session.status = "waiting_scan";
      session.qrBase64 = event.qrBase64;
      return;
    }
    if (event.type === "scanned") {
      session.status = "scanned";
      return;
    }
    if (event.type === "declined") {
      session.status = "declined";
    }
    // "expired": the gateway asks zca-js for a new QR and fires "qr" again - nothing to do here.
  }

  getQrLoginStatus(accountId: string): QrStatusView {
    const session = this.sessions.get(accountId);
    if (!session) return { state: "idle" };

    if (PENDING.has(session.status) && this.now() - session.startedAt >= SESSION_TTL_MS) {
      // Quá 3 phút không quét: coi như hết phiên, promise về sau bị bỏ qua theo seq
      session.controller.abort();
      this.sessions.delete(accountId);
      return { state: "timeout" };
    }

    return {
      state: session.status,
      ...(session.qrBase64 ? { qr_png_base64: session.qrBase64 } : {}),
      ...(session.error ? { error: session.error } : {}),
    };
  }
}
