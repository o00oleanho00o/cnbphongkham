// ported from: web/src/pages/qr-login-modal.tsx
//
// Deviations: the raw `fetch` of the original is the typed client (`POST .../login` starts the session,
// `GET .../login/status` is polled). The contract states are `idle | waiting_scan | scanned | success |
// expired | error`: the original `timeout` is `expired` and `declined` has no equivalent (a refusal on
// the phone arrives as `error` with the BE's `detail`). The QR arrives as `qr_png_base64`, the page
// builds the data URI.
"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useChotNen } from "@/lib/admin/shared/backdrop-close-guard";
import { http, unwrap, errorMessage } from "@/lib/api/client";
import type { Account, Schemas } from "@/lib/api";

type QrLoginStatus = Schemas["QrLoginStatus"];

type QrState = {
  status: QrLoginStatus["state"] | "starting";
  qrDataUri?: string;
  error?: string;
};

const STATUS_TEXT: Record<QrState["status"], string> = {
  idle: "Đang chuẩn bị...",
  starting: "Đang tạo mã QR...",
  waiting_scan: "Mở app Zalo trên điện thoại và quét mã này",
  scanned: "Đã quét - xác nhận đăng nhập trên điện thoại",
  success: "Đăng nhập thành công! Bot đang khởi động...",
  error: "Đăng nhập thất bại",
  expired: "Hết thời gian chờ quét (3 phút)",
};

const POLL_MS = 1500;
const TERMINAL: readonly QrState["status"][] = ["success", "expired", "error"];
const FAILED: readonly QrState["status"][] = ["expired", "error"];

function fromStatus(s: QrLoginStatus): QrState {
  return {
    status: s.state,
    qrDataUri: s.qr_png_base64 ? `data:image/png;base64,${s.qr_png_base64}` : undefined,
    error: s.state === "error" ? (s.detail ?? undefined) : undefined,
  };
}

async function callLogin(accountId: string, kind: "login" | "status"): Promise<QrState> {
  const params = { path: { account_id: accountId } };
  try {
    const result =
      kind === "login"
        ? await unwrap(http.POST("/api/v1/admin/accounts/{account_id}/login", { params }))
        : await unwrap(http.GET("/api/v1/admin/accounts/{account_id}/login/status", { params }));
    return fromStatus(result);
  } catch (e) {
    return { status: "error", error: errorMessage(e) };
  }
}

/** Thân khung QR: ảnh khi đang chờ quét, biểu tượng theo trạng thái còn lại */
function QrBody({ state }: { state: QrState }): ReactNode {
  if (state.qrDataUri && state.status === "waiting_scan") {
    // data URI of a one-off PNG: next/image has nothing to optimise
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={state.qrDataUri} alt="Mã QR đăng nhập Zalo" className="h-52 w-52" />;
  }
  if (state.status === "success") return <span className="text-5xl">✅</span>;
  if (FAILED.includes(state.status)) return <span className="text-5xl">⚠️</span>;
  if (state.status === "scanned") return <span className="text-5xl">📱</span>;
  return <span className="animate-pulse text-[13px] text-ink-soft">Đang tải QR...</span>;
}

/** Modal QR login: POST bắt đầu phiên rồi polling status mỗi 1.5s */
export function QrLoginModal({ account, onClose }: { account: Account; onClose: () => void }) {
  const [state, setState] = useState<QrState>({ status: "idle" });
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const poll = async () => {
      if (stopped) return;
      const next = await callLogin(account.id, "status");
      if (stopped) return;
      setState(next);
      const terminal = TERMINAL.includes(next.status);
      if (!terminal) timer = setTimeout(poll, POLL_MS);
    };

    void callLogin(account.id, "login").then((first) => {
      if (stopped) return;
      setState(first);
      if (TERMINAL.includes(first.status)) return;
      timer = setTimeout(poll, POLL_MS);
    });

    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, [account.id, retryKey]);

  const failed = FAILED.includes(state.status);
  const nen = useChotNen(onClose);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/25 p-4 backdrop-blur-[2px]"
      {...nen}
    >
      {/* Trần chiều cao + cuộn nội bộ: cửa sổ thấp (điện thoại nằm ngang,
          laptop zoom cao) làm hộp này tràn khỏi màn mà KHÔNG cuộn được - lớp
          phủ là `fixed inset-0` nên trang cuộn cũng không kéo nó vào. `dvh`
          chứ không `vh` để trên điện thoại còn trừ đúng phần thanh địa chỉ
          đang chiếm chỗ. */}
      <div
        className="gc-card max-h-[85dvh] w-full max-w-sm overflow-y-auto p-6 text-center"
        role="dialog"
        aria-modal="true"
        aria-label={`Login QR - ${account.label}`}
      >
        <div className="mb-1 font-semibold break-words text-ink">Login QR - {account.label}</div>
        <p className="mb-4 text-[13px] text-ink-soft">{STATUS_TEXT[state.status]}</p>

        <div className="mx-auto mb-4 flex h-56 w-56 items-center justify-center rounded-xl border border-line bg-surface">
          <QrBody state={state} />
        </div>

        {state.error && (
          <p className="mb-3 text-[13px] text-red-600 dark:text-red-400">{state.error}</p>
        )}

        <div className="flex justify-center gap-3">
          {failed && (
            <button
              onClick={() => setRetryKey((k) => k + 1)}
              className="min-h-11 rounded-lg bg-brand-500 px-4 py-2 text-[14px] font-medium text-white hover:bg-brand-600 sm:min-h-0"
            >
              Thử lại
            </button>
          )}
          <button
            onClick={onClose}
            className="min-h-11 rounded-lg border border-line px-4 py-2 text-[14px] text-ink hover:bg-tile sm:min-h-0"
          >
            {state.status === "success" ? "Xong" : "Đóng"}
          </button>
        </div>
      </div>
    </div>
  );
}
