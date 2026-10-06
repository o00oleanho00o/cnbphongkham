"use client";

// "Liên kết Zalo" (frames WM44, WM45): a one-time code the operator sends, as a Zalo message, to the clinic's
// internal account. The page asks the BE whether the link is made every few seconds and closes by itself when it
// is. The code is shown here only: it is never kept in the URL, a log or the browser storage, and it works once
// for ten minutes (`POST /me/notify-zalo/link`).
import { useCallback, useEffect, useRef, useState } from "react";

import { ListSkeleton, Notice } from "@/components/ops/ops-ui";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import { countdownText, secondsLeft } from "@/lib/ops/notify-view";
import { Button } from "@/ui/button";
import { Dialog } from "@/ui/dialog";

type Code = Schemas["NotifyLinkOut"];

const POLL_MS = 3000;
const TICK_MS = 1000;

export function ZaloLinkDialog({
  onClose,
  onLinked,
}: {
  onClose: () => void;
  onLinked: () => void;
}) {
  const [code, setCode] = useState<Code | null>(null);
  const [error, setError] = useState("");
  const [now, setNow] = useState(() => Date.now());
  const alive = useRef(true);

  const create = useCallback(async () => {
    setError("");
    setCode(null);
    try {
      const created = await unwrap(http.POST("/api/v1/me/notify-zalo/link"));
      if (alive.current) setCode(created);
    } catch (e) {
      if (alive.current) setError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    void create();
    return () => {
      alive.current = false;
    };
  }, [create]);

  const expiresAt = code ? Date.parse(code.expires_at) : 0;
  const left = code ? secondsLeft(expiresAt, now) : 0;
  const expired = code !== null && left === 0;

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), TICK_MS);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!code || expired) return;
    const timer = setInterval(() => {
      unwrap(http.GET("/api/v1/me/notify-zalo"))
        .then((status) => {
          if (status.linked && alive.current) onLinked();
        })
        .catch(() => undefined);
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [code, expired, onLinked]);

  const target = code?.internal_label ?? "Pema Nội bộ";
  return (
    <Dialog
      title="Liên kết Zalo"
      subtitle="Mã chỉ dùng được một lần"
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Đóng
          </Button>
          {(expired || error) && <Button onClick={() => void create()}>Tạo mã mới</Button>}
        </>
      }
    >
      {error && <Notice tone="error">{error}</Notice>}
      {!code && !error && <ListSkeleton rows={1} />}
      {code && (
        <>
          <p className="text-body text-ink">
            Gửi mã dưới đây cho tài khoản &quot;{target}&quot; trên Zalo để Pema biết đây là tài
            khoản của bạn.
          </p>
          <p
            aria-label="Mã liên kết"
            className="my-3 rounded-tile border border-line bg-tile px-4 py-3 text-center font-mono text-subtitle font-bold tracking-widest text-ink"
          >
            {code.code}
            {expired && (
              <span className="ml-2 text-body font-normal text-danger">(đã hết hạn)</span>
            )}
          </p>
          <ol className="list-decimal space-y-1 pl-5 text-body text-ink">
            <li>Mở Zalo trên điện thoại.</li>
            <li>Gửi mã này cho tài khoản &quot;{target}&quot;.</li>
            <li>Chờ vài giây: trang này tự cập nhật.</li>
          </ol>
          {expired ? (
            <div className="mt-3">
              <Notice tone="error">Mã đã hết hạn. Tạo mã mới và gửi lại.</Notice>
            </div>
          ) : (
            <p className="mt-3 text-label text-ink-soft">
              Mã dùng một lần, còn hiệu lực {countdownText(left)}.
            </p>
          )}
        </>
      )}
    </Dialog>
  );
}
