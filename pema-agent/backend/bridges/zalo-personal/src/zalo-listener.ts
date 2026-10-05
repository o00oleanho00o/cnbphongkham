// ported from: src/zalo/zalo-listener.ts
// Deviations:
// - the handlers receive a `ListenerPort` (the slice of zca-js' listener this file calls) so tests can
//   inject a fake `api.listener`; the logic and constants are the original's;
// - `onReport` is new: the bridge must tell the API when the account connected, disconnected or looks
//   dead. `session_dead` / `logged_out` are reported when the planner raises `nghiNgoPhienChet`
//   (5 consecutive flaps), and the account stops reconnecting only if that suspicion persists for
//   `SO_CHU_KY_CHO_THEM_TRUOC_KHI_BO_CUOC` more cycles; before that the ORIGINAL behaviour holds (log and
//   keep backing off);
// - `now` / `random` / `keHoach` can be injected so the reconnect logic is testable with fake timers;
// - the log line that advises `pnpm zalo-login <id>` now points at the admin UI QR login.
import { CloseReason } from "zca-js";
import type { FriendEvent } from "zca-js";
import { createLogger, errorInfo } from "./logger.js";
import { KeHoachKetNoiLai } from "./reconnect-planner.js";
import type { ListenerPort } from "./zalo-types.js";

export type RawMessageHandler = (rawMessage: unknown) => Promise<void> | void;
export type FriendEventHandler = (event: FriendEvent) => Promise<void> | void;

/** Trần jitter cộng vào backoff để nhiều account không reconnect đồng loạt */
const JITTER_MS = 1_000;
/** Mã giả cho log khi start() ném (không phải close code thật của zca-js) */
const MA_START_NEM = -1;
/**
 * Sau khi đã BÁO nghi phiên chết, phải thấy ngưỡng đó còn nguyên thêm bấy nhiêu chu kỳ đóng liên tiếp
 * thì mới thôi kết nối lại. Bám nguyên tắc của bản gốc: cổng bừa có thể nuốt mất chính cảnh báo cần
 * thiết, nên chỉ bỏ cuộc khi chuỗi chớp-tắt kéo dài mà không một lần nối nào đứng được.
 */
export const SO_CHU_KY_CHO_THEM_TRUOC_KHI_BO_CUOC = 3;

export type ListenerReportState = "connected" | "disconnected" | "session_dead" | "logged_out";

export type ListenerReport = { state: ListenerReportState; reason: string };

export type ListenerOptions = {
  onReport?: (report: ListenerReport) => void;
  keHoach?: KeHoachKetNoiLai;
  now?: () => number;
  /** In [0, 1); jitter = floor(random() * JITTER_MS). */
  random?: () => number;
};

/**
 * Why the session looks dead, from the close code of the flap that crossed the threshold.
 * zca-js has no explicit "logged out" event. Its close codes: 3000 = another connection opened (a Zalo Web
 * session on the same account), 3003 = the server kicked this connection, 1006 = abnormal closure.
 * Kicked again and again without ever staying up = the session was revoked: `logged_out`.
 */
function classifyDeadSession(code: number): {
  state: "session_dead" | "logged_out";
  reason: string;
} {
  if (code === CloseReason.KickConnection) return { state: "logged_out", reason: "kicked_by_zalo" };
  if (code === CloseReason.DuplicateConnection) {
    return { state: "session_dead", reason: "duplicate_connection" };
  }
  return { state: "session_dead", reason: "reconnect_flapping" };
}

/**
 * Start listener cho 1 account, tự reconnect với backoff khi bị đóng.
 * Lưu ý: Zalo chỉ cho 1 web listener/account - mở Zalo Web trên trình duyệt
 * sẽ đá listener này ra (bot sẽ tự reconnect và đá ngược lại phiên web).
 * Trả về hàm stop() để shutdown sạch.
 */
export function startListener(
  accountId: string,
  api: { listener: ListenerPort },
  onMessage: RawMessageHandler,
  onFriendEvent?: FriendEventHandler,
  options: ListenerOptions = {},
): () => void {
  const log = createLogger(`listener:${accountId}`);
  const now = options.now ?? (() => Date.now());
  const random = options.random ?? Math.random;
  const report = options.onReport ?? (() => undefined);
  let stopped = false;
  const keHoach = options.keHoach ?? new KeHoachKetNoiLai();
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  /** Số chu kỳ đóng LIÊN TIẾP mà planner vẫn nghi phiên chết (0 khi cờ tắt) */
  let soChuKyNghiNgo = 0;

  const lenLichKetNoiLai = (delayMs: number): void => {
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      if (stopped) return;
      try {
        // ws đã null sau onClosed nên stop() ở đây thường là no-op; gọi phòng khi
        // còn ws sót lại, để start() luôn khởi động từ state sạch.
        api.listener.stop();
        api.listener.start();
      } catch (err) {
        // start() ném = KHÔNG có ws mới = SẼ KHÔNG có onClosed kế tiếp để kích
        // reconnect. Phải TỰ đếm lần hỏng này (leo backoff + có cơ hội chạm ngưỡng
        // nghi phiên chết) rồi lên lịch lại, nếu không vòng reconnect chết câm và
        // bot offline tới lúc restart tay - đúng ca cookie hỏng dai.
        log.error(errorInfo(err), "start() ném khi reconnect - đếm là một lần hỏng, tự thử lại");
        xuLyDongVaLenLich(MA_START_NEM, "start() ném khi reconnect");
      }
    }, delayMs);
  };

  // Gộp: tính kế hoạch chờ + log + lên lịch reconnect. Dùng CHUNG cho cả onClosed
  // (đóng bình thường) lẫn nhánh start() ném, để một lần start() hỏng cũng leo
  // backoff và có thể chạm ngưỡng cảnh báo re-login - không đứng yên spam mãi.
  const xuLyDongVaLenLich = (code: number, reason: string): void => {
    const ke = keHoach.danhDauDong(now(), Math.floor(random() * JITTER_MS));
    soChuKyNghiNgo = ke.nghiNgoPhienChet ? soChuKyNghiNgo + 1 : 0;
    report({ state: "disconnected", reason: `closed_${code}` });

    if (!ke.nghiNgoPhienChet) {
      log.warn(
        { code, reason, delayMs: ke.delayMs, onDinh: ke.onDinh },
        "Listener bị đóng - sẽ kết nối lại",
      );
      lenLichKetNoiLai(ke.delayMs);
      return;
    }

    // Nối-rồi-rớt-ngay nhiều lần liên tiếp = dấu hiệu phiên bị thu hồi (đổi mật
    // khẩu, đăng xuất từ xa, hết hạn) HOẶC còn một phiên Zalo Web đang tranh kết
    // nối. Nói THẲNG cách chữa thay vì để người vận hành đoán như ca 2026-08-25.
    log.warn(
      { code, reason, chopTatLienTiep: ke.chopTatLienTiep, delayMs: ke.delayMs },
      `Listener nối rồi rớt ngay ${ke.chopTatLienTiep} lần liên tiếp - phiên Zalo có thể đã hết hạn/bị thu hồi, hoặc còn một phiên Zalo Web đang tranh kết nối. Đóng tab Zalo Web; nếu vẫn lỗi, đăng nhập lại bằng mã QR trên trang quản trị (Accounts > Login).`,
    );
    const dead = classifyDeadSession(code);
    if (soChuKyNghiNgo === 1 || soChuKyNghiNgo > SO_CHU_KY_CHO_THEM_TRUOC_KHI_BO_CUOC) {
      report(dead);
    }
    if (soChuKyNghiNgo > SO_CHU_KY_CHO_THEM_TRUOC_KHI_BO_CUOC) {
      log.error(
        { chopTatLienTiep: ke.chopTatLienTiep },
        "Nghi phiên chết kéo dài - thôi kết nối lại, chờ đăng nhập lại",
      );
      return;
    }
    lenLichKetNoiLai(ke.delayMs);
  };

  api.listener.on("message", (message) => {
    Promise.resolve(onMessage(message)).catch((err: unknown) =>
      log.error(errorInfo(err), "Lỗi xử lý tin nhắn"),
    );
  });

  if (onFriendEvent) {
    api.listener.on("friend_event", (event) => {
      Promise.resolve(onFriendEvent(event)).catch((err: unknown) =>
        log.error(errorInfo(err), "Lỗi xử lý friend_event"),
      );
    });
  }

  api.listener.onConnected(() => {
    keHoach.danhDauKetNoi(now());
    report({ state: "connected", reason: "connected" });
    log.info("Listener đã kết nối");
  });

  api.listener.onError((error: unknown) => {
    log.error(errorInfo(error), "Listener báo lỗi");
  });

  // code/reason của zca-js (CloseReason: 3000/3003 = bị web session đá hợp lệ,
  // 1006 = rớt bất thường). Chỉ LOG để có số đo; CHƯA cổng ngưỡng nghi-phiên-chết
  // theo mã vì chưa biết Zalo gửi mã nào khi THU HỒI phiên (đổi mật khẩu) - cổng
  // bừa có thể nuốt mất chính cảnh báo cần thiết.
  // (Bridge: the code only picks the reported label, `logged_out` vs `session_dead`; it never gates the
  // planner threshold.)
  api.listener.onClosed((code: number, reason: string) => {
    if (stopped) return;
    xuLyDongVaLenLich(code, reason);
  });

  api.listener.start();

  return () => {
    stopped = true;
    if (reconnectTimer) {
      // Đừng để timer reconnect đang chờ (tối đa ~60s) trì hoãn shutdown/toggle.
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    try {
      api.listener.stop();
    } catch {
      /* đã đóng sẵn */
    }
  };
}
